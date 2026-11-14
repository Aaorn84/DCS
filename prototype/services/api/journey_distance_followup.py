"""Protocol 35: resolve next-shot distance against a live tee proposal."""
import copy,hashlib,re
from round_state import require,canonical,fact_value

def followup_query(text):
 if not isinstance(text,str):return None
 t=re.sub(r'[\s，,。！!？?]','',text)
 if re.fullmatch(r'(?:那|那么)?下一杆(?:大概|预计)?(?:到果岭(?:参考点|中心)?)?(?:还(?:有|剩)?|剩下|剩余)?(?:多少|多远|距离多少|距离多远)(?:码|米)?',t):
  return '米' if t.endswith('米') else '码' if t.endswith('码') else ''
 return None

def live_club(s):
 j=s.get('journey',{});c=j.get('consultation') or {};o=c.get('suggestion') or {}
 if not c.get('phase','').startswith('tee_') or not o:return None
 if o.get('hole')!=fact_value(s,'context.active_hole') or o.get('course_evidence')!=fact_value(s,'context.course_snapshot'):return None
 return o.get('club')

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==35,'unsupported distance follow-up protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{});prior=j.get('distance_followup_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 require(p['event_id'] not in j.get('projection_receipts',{}),'event id already used by another journey protocol')
 adapted=copy.deepcopy(p);adapted['protocol_version']=34
 text=p.get('text','');unit=followup_query(text) if p.get('type')=='message' else None
 force_club=False
 from dialogue_routing import scope
 pending=j.get('distance_followup_question');owner=j.get('response_context',{}).get('question_owner')
 if p.get('type')=='message' and pending and owner=='followup.distance' and pending['scope']==scope(s) and 0<=now-pending['at']<=300:
  clean=re.sub(r'[\s，,。！!？?]','',text)
  if clean in ('现在','当前','现在的距离','当前距离','现在到果岭的距离'):
   adapted['text']='还有多少'+pending['unit'];j.pop('distance_followup_question',None)
  elif clean in ('预计','预计距离','方案','按刚才方案','打完后','预计剩余距离'):
   unit=pending['unit'];force_club=True
  elif re.fullmatch(r'(?:用)?(一号木|1号木|三号木|3号木|长铁(?:杆)?|[2-9](?:号铁|铁))',clean):
   adapted['text']=re.sub(r'^用','',clean)+'开球之后还剩多少'+pending['unit'];j.pop('distance_followup_question',None)
 if unit is not None and j.get('stage')=='active':
  label=live_club(s)
  if label:adapted['text']=label+'开球之后还剩多少'+unit
  else:
   from datetime import datetime
   require(isinstance(p.get('observed_at'),str),'observation time required');stamp=datetime.fromisoformat(p['observed_at'].replace('Z','+00:00'));require(stamp.tzinfo is not None,'timezone required')
   silent=j.get('quiet') or any(fact_value(s,k) is True for k in ('context.quiet','context.preparing'))
   result={'text':'' if silent else ('你想按哪支杆的方案估算下一杆距离？' if force_club else '你是问现在到果岭的距离，还是想按某支杆估算打完后的剩余距离？'),'speak_allowed':not silent,'status':'clarify'}
   j['distance_followup_question']={'scope':scope(s),'unit':unit or j.get('profile',{}).get('units',{}).get('value','码'),'at':now}
   j['response_context']={'question_owner':None if silent else 'followup.distance','intent':'fact_request','domain':'distance_scope','scope':scope(s),'at':now,'event_id':p['event_id'],'spoken_text':result['text']};j['turn_choices']=[]
   j.setdefault('distance_followup_receipts',{})[p['event_id']]=sha
   return result
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now)
 s['journey'].setdefault('distance_followup_receipts',{})[p['event_id']]=sha
 return result
