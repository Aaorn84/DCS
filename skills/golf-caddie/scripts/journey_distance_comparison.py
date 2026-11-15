"""Protocol 36: explicit club comparison questions plus normalized follow-up context."""
import copy,hashlib,re,unicodedata
from round_state import require,canonical
from dialogue_routing import scope
from journey_distance_followup import followup_query,live_club

CLUB=r'一号木|1号木|三号木|3号木|长铁(?:杆)?|[2-9二两三四五六七八九](?:号铁|铁)'
def clean(text):
 if not isinstance(text,str):return text
 t=''.join(c for c in unicodedata.normalize('NFKC',text) if unicodedata.category(c)!='Cf')
 return re.sub(r'[\s，,。！!？?；;：:]','',t)

def comparison_query(text):
 t=clean(text)
 if not isinstance(t,str):return None
 m=re.fullmatch(r'(?:如果|假如|要是)?(?:用|换|换成)?(?P<club>'+CLUB+r')(?:开球)?(?P<follow>(?:那|那么)?下一杆.*)',t)
 if not m:return None
 unit=followup_query(m['follow'])
 if unit is None:return None
 label=m['club'].translate(str.maketrans('二两三四五六七八九','223456789'))
 return {'club':label,'unit':unit}

def context_signature(s):
 j=s.get('journey',{});c=j.get('consultation') or {}
 return [scope(s),(c.get('suggestion') or {}).get('id'),len(j.get('execution_reports',[]))]

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==36,'unsupported distance comparison protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{});prior=j.get('distance_comparison_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 require(p['event_id'] not in j.get('distance_followup_receipts',{}),'event id already used by another journey protocol')
 adapted=copy.deepcopy(p);adapted['protocol_version']=35
 compared=None
 if p.get('type')=='message':
  text=clean(p.get('text'));query=comparison_query(text)
  if query:
   compared=query['club'];adapted['text']=compared+'开球之后还剩多少'+query['unit']
  elif followup_query(text) is not None:
   focus=j.get('distance_comparison_focus')
   if focus and focus['signature']==context_signature(s) and 0<=now-focus['at']<=300:
    compared=focus['club'];adapted['text']=compared+'开球之后还剩多少'+followup_query(text)
   else:adapted['text']=text
  elif isinstance(text,str):
   # Normalize only recognized distance questions, never course names or score grammar.
   from journey_navigation_queries import distance_query
   from journey_projection import projection_query
   if distance_query(text) is not None or projection_query(text) is not None:adapted['text']=text
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now)
 j=s['journey']
 projection=result.get('projection')
 if projection:
  j['distance_comparison_focus']={'club':compared or projection['club'],'signature':context_signature(s),'at':now}
 elif p.get('type')=='message' and not compared:
  from dialogue_routing import classify
  if classify(s,adapted.get('text',''),now)['type'] in ('decision_commitment','execution_report','score_report','state_transition'):
   j.pop('distance_comparison_focus',None)
 j.setdefault('distance_comparison_receipts',{})[p['event_id']]=sha
 return result
