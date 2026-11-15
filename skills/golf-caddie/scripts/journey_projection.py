"""Protocol 34: hypothetical tee-shot remaining distance, never actual execution."""
import copy,hashlib,math,re
from round_state import require,canonical,fact_value

def projection_query(text):
 if not isinstance(text,str):return None
 t=re.sub(r'[\s，,。！!？?]','',text)
 # Explicit past execution is a different event; do not reinterpret it as a plan.
 if re.search(r'刚才|已经|打过|开过|实际|上一杆',t):return None
 m=re.fullmatch(r'(?:如果|假如|要是|那)?(?:用)?(?P<club>一号木|1号木|三号木|3号木|长铁(?:杆)?|[2-9](?:号铁|铁))?(?:开球|打出去|打完|打出|打)(?:以后|之后|后)?(?:到果岭(?:参考点|中心)?)?(?:还(?:有|剩)?|剩下|剩余)?(?:多少|多远|几码|几米)(?:码|米)?',t)
 if not m:return None
 label=m['club']
 key='driver' if label in ('一号木','1号木') else 'three_wood' if label in ('三号木','3号木') else 'long_iron' if label and label.startswith('长铁') else None
 if label and key is None:key=label[0]+'i'
 return {'club_key':key,'label':label,'unit':'米' if t.endswith(('米','几米')) else '码' if t.endswith(('码','几码')) else None}

def point(p):
 return isinstance(p,dict) and all(type(p.get(k)) in (int,float) and math.isfinite(p[k]) and lo<=p[k]<=hi for k,lo,hi in [('latitude',-90,90),('longitude',-180,180)])

def answer(s,q,now):
 j=s.get('journey',{});unit=q['unit'] or j.get('profile',{}).get('units',{}).get('value','码');scale=.9144 if unit=='米' else 1
 from tee_strategy import analyze
 a=analyze(s,now)
 if not a:return {'text':'先确认当前发球台位置，我再按开球方案估算剩余距离。','status':'unavailable','projection':None}
 c=j.get('consultation') or {};suggestion=c.get('suggestion',{})
 key=q['club_key']
 if key is None:
  key=next((key for key,club in a['clubs'].items() if club['label']==suggestion.get('club')),None)
  if key is None:return {'text':'你想估算用哪支杆开球后的剩余距离？','status':'clarify','projection':None}
 elif key.endswith('i'):
  key=next((k for k,club in a['clubs'].items() if club['label'] in (key[0]+'铁',key[0]+'号铁') or (key=='7i' and k=='seven')),None)
  if key is None:
   requested=q['club_key'];stored=j.get('profile',{}).get('projection_carries',{}).get(requested)
   if stored:
    key=requested;a['clubs'][key]=stored
   else:return {'text':q['label']+'平常的Carry大概多少'+unit+'？','status':'clarify','projection':None,'missing_club':requested}
 club=a['clubs'].get(key)
 if not club:return {'text':(q['label'] or '这支杆')+'平常的Carry大概多少'+unit+'？','status':'clarify','projection':None,'missing_club':key}
 carry=club['carry_yards']
 if carry>=a['distance_yards']:return {'text':'这支杆的Carry已达到或超过当前到果岭的距离，需要重新比较落区。','status':'unavailable','projection':None}
 candidate=next((x for x in a['candidates'] if x['club_key']==key),None)
 target=candidate['zone'].get('target_reference') if candidate else None
 green=None
 if point(target):
  course=s['evidence'][a['course_evidence']]['data'];hole=next(h for h in course['holes'] if h['number']==a['hole'])
  green=next((o for o in hole['objects'] if o['kind']=='green_center'),None)
 if point(target) and point(green):
  from shot_evidence import haversine
  yards=haversine(target,green)/.9144;basis='mapped_landing_reference';prefix='按刚才那段落区估算' if suggestion.get('club')==club['label'] else '按对应地图落区估算'
 else:
  yards=a['distance_yards']-carry;basis='straight_line_subtraction';prefix='沿果岭方向直线粗估'
 amount=int(round(yards*scale/5)*5);carry_amount=round(carry*scale)
 return {'text':f"{club['label']}按{carry_amount} {unit}的Carry开球，{prefix}，到果岭参考点预计还剩约{amount}{unit}；以实际落点为准。".replace(' '+unit,unit),
         'status':'projection','projection':{'club_key':key,'club':club['label'],'carry_yards':carry,'remaining_yards':yards,'basis':basis,'hole':a['hole'],
          'position_version':a['position_version'],'course_evidence':a['course_evidence'],'hypothetical':True,'actual_shot_created':False,'carry_learning_allowed':False}}

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==34,'unsupported projection protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{});prior=j.get('projection_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 require(p['event_id'] not in j.get('navigation_query_receipts',{}) and p['event_id'] not in j.get('receipts',{}),'event id already used by another journey protocol')
 q=projection_query(p.get('text')) if p.get('type')=='message' else None
 from dialogue_routing import scope
 pending=j.get('projection_question');response=j.get('response_context',{})
 numeric=re.fullmatch(r'([0-9]{1,3})(码|米)?',str(p.get('text','')).strip()) if p.get('type')=='message' else None
 if q is None and pending and numeric and response.get('question_owner')=='projection.carry' and pending['scope']==scope(s) and 0<=now-pending['at']<=300:
  value=int(numeric[1]);require(0<value<=400,'invalid carry')
  unit=numeric[2] or pending['unit'];q=pending['query'];key=pending['club_key']
  if key in ('driver','three_wood','long_iron'):
   j.setdefault('profile',{})[key]={'value':{'distance':value,'units':unit,'distance_type':'carry'},'source':'user_report','event_id':p['event_id']}
  else:
   j.setdefault('profile',{}).setdefault('projection_carries',{})[key]={'label':q['label'],'carry_yards':value/(.9144 if unit=='米' else 1),'source':'user_report','event_id':p['event_id']}
  j.pop('projection_question',None)
 if q and j.get('stage')=='active':
  from datetime import datetime
  require(isinstance(p.get('observed_at'),str),'observation time required')
  stamp=datetime.fromisoformat(p['observed_at'].replace('Z','+00:00'));require(stamp.tzinfo is not None,'timezone required')
  result=answer(s,q,now)
  silent=j.get('quiet') or any(fact_value(s,k) is True for k in ('context.quiet','context.preparing'))
  result.update(speak_allowed=not silent)
  if silent:result['text']=''
  # A fact answer owns no old plan confirmation. Keep the consultation for explicit resumption.
  owner='projection.carry' if result.get('missing_club') and not silent else None
  j['response_context']={'question_owner':owner,'intent':'fact_request','domain':'projected_remaining','at':now,'scope':scope(s),'event_id':p['event_id'],'spoken_text':result['text']}
  if owner:j['projection_question']={'club_key':result['missing_club'],'query':q,'scope':scope(s),'unit':q['unit'] or j.get('profile',{}).get('units',{}).get('value','码'),'at':now}

  j['turn_choices']=[]
  j.setdefault('projection_audit',[]).append({'event_id':p['event_id'],'observed_at':p['observed_at'],'query':p['text'],'projection':copy.deepcopy(result['projection'])})
 else:
  from journey import reduce_journey as previous
  adapted=copy.deepcopy(p);adapted['protocol_version']=33;result=previous(s,adapted,seq,now)
 s['journey'].setdefault('projection_receipts',{})[p['event_id']]=sha
 return result
