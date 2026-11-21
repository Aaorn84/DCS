"""Interaction-associated location pairs with explicit single-stroke confirmation.
No GPS swing inference, carry calibration or score increments.
"""
import copy,re
from datetime import datetime
from round_state import fact_value,canonical
from lie_position import fresh_position
from shot_evidence import haversine
from conversation_preferences import agreement
from decision_queries import previous_distance,distance_answer

def scope(s):
 return (s.get('journey',{}).get('round') or {}).get('id'),fact_value(s,'context.course_snapshot'),fact_value(s,'context.active_hole')

def add(s,point,evidence_ids,origin):
 if not evidence_ids:return
 j=s['journey'];round_id,course,hole=scope(s)
 row=dict(round_id=round_id,course=course,hole=hole,point=copy.deepcopy(point),evidence_ids=list(evidence_ids),origin=origin)
 points=j.setdefault('shot_location_candidates',[])
 relevant=[v for v in points if (v['round_id'],v['course'],v['hole'])==(round_id,course,hole)]
 if relevant:
  last=relevant[-1]
  tolerance=max(5,min(15,last['point']['accuracy_m']+point['accuracy_m']))
  if haversine(last['point'],point)<=tolerance:return
 row['id']=evidence_ids[0];points.append(row)

def simulated_tee(s,key,point):
 course=s.get('evidence',{}).get(key[1],{}).get('data',{})
 if course.get('reference_simulation') is not True:return False
 hole=next((h for h in course.get('holes',[]) if h['number']==key[2]),{})
 tee=hole.get('simulation_positions',{}).get('tee')
 return bool(tee and haversine(tee,point)<=5)

def observe(s,now,query=False,*,preserve_played_shots=False):
 pos=fresh_position(s,now)
 if not pos:return
 v=pos['value'];_,course,hole=scope(s)
 data=s.get('evidence',{}).get(course,{}).get('data',{})
 simulated=data.get('reference_simulation') is True and v.get('simulation_hole')==hole
 if preserve_played_shots and simulated_tee(s,scope(s),v) and pair(s):return
 if simulated or query:add(s,v,pos.get('evidence_ids',[]),'simulated_location_candidate' if simulated else 'query_location_candidate')

def correct_simulated_position(s,now):
 pos=fresh_position(s,now)
 key=scope(s)
 course=s.get('evidence',{}).get(key[1],{}).get('data',{})
 if not pos or course.get('reference_simulation') is not True or pos['value'].get('simulation_source')!='map_click':return
 rows=s['journey'].get('shot_location_candidates',[])
 indices=[i for i,row in enumerate(rows) if (row['round_id'],row['course'],row['hole'])==key]
 if len(indices)<2:return
 index=indices[-1]
 old=rows[index]
 previous=rows[indices[-2]]
 old_key=canonical([*key,previous['id'],old['id']])
 new_id=pos['evidence_ids'][0]
 rows[index]=dict(old,id=new_id,point=copy.deepcopy(pos['value']),evidence_ids=list(pos['evidence_ids']))
 j=s['journey']
 reports=j.get('previous_club_reports',{})
 if old_key in reports:reports[canonical([*key,previous['id'],new_id])]=reports.pop(old_key)
 for row in j.get('confirmed_shot_distances',[]):
  if row['scope']==list(key) and old['id'] in row['pair_ids']:row['valid']=False
 for row in j.get('rejected_shot_links',[]):
  if row['scope']==list(key) and row['pair_ids']==[previous['id'],old['id']]:
   row['pair_ids']=[previous['id'],new_id]
 plan=j.get('tee_club_fallback') or {}
 if plan.get('pair_key')==old_key:plan['pair_key']=canonical([*key,previous['id'],new_id])
 j.pop('pending_shot_link',None)
 j.pop('pending_previous_club',None)


def bootstrap(s):
 """Recover only GPS fixes demonstrably accepted by earlier journey receipts."""
 j=s['journey'];round_id,course,hole=scope(s)
 if any(v['round_id']==round_id and v['course']==course and v['hole']==hole for v in j.get('shot_location_candidates',[])):return
 ce=s.get('evidence',{}).get(course,{})
 def timestamp(value):return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
 if ce.get('data',{}).get('reference_simulation') is not True:return
 candidates=[]
 for key,e in s.get('evidence',{}).items():
  p=e.get('data',{});receipt=j.get('receipts',{}).get(e.get('id'),{}).get('result',{})
  accepted=receipt.get('transition',{}).get('accepted_position') is True and not receipt.get('ignored')
  if e.get('active') and e.get('phase')=='final' and e.get('source')=='gps' and accepted and p.get('simulation_hole')==hole and p.get('accuracy_m',999)<=15 and timestamp(e['observed_at'])>=timestamp(ce['observed_at']):
   candidates.append((timestamp(e['observed_at']),e.get('received_at',0),key,e))
 for _,__,key,e in sorted(candidates):
  point=dict(e['data'],observed_at=e['observed_at']);add(s,point,[key],'historical_accepted_simulation_location')

def pair(s):
 key=scope(s)
 rows=[v for v in s['journey'].get('shot_location_candidates',[]) if (v['round_id'],v['course'],v['hole'])==key]
 return rows[-2:] if len(rows)>=2 else []

def live(s,row):
 return all(s.get('evidence',{}).get(k,{}).get('active') and s['evidence'][k].get('phase')=='final' for k in row['evidence_ids'])

def unit(s,text):return '米' if '米' in text else '码' if '码' in text else s['journey'].get('profile',{}).get('units',{}).get('value','码')
def amount(meters,u):return str(round((meters/(1 if u=='米' else .9144))/5)*5)+u

def current_score_record(s,record):
 if not record.get('inferred_from_score'):return True
 patch=s.get('patches',{}).get(record.get('score_patch_id'),{})
 return patch.get('status')=='committed' and bool(patch.get('operations')) and all(
  s.get('facts',{}).get(op['path'],{}).get('version')==patch.get('committed_version')
  for op in patch['operations'])


def valid_record(s,record):
 return (not record.get('inferred_from_score') or s.get('patches',{}).get(record.get('score_patch_id'),{}).get('status')=='committed') and record.get('valid') is True and tuple(record['scope'])==scope(s) and all(live(s,row) for row in record['endpoints'])

def handle(s,p,now):
 text=p.get('text','');j=s['journey']
 if text in ('撤销上一杆距离','撤销刚才的距离记录'):
  records=[v for v in j.get('confirmed_shot_distances',[]) if valid_record(s,v)]
  if not records:return '目前没有可撤销的上一杆距离记录。'
  r=records[-1];r['valid']=False;r['revoked_by']=p['event_id'];j.pop('pending_shot_link',None)
  return '已撤销这条单杆距离记录，两个位置仍保留为位移证据。'
 pending=j.get('pending_shot_link')
 if pending and not previous_distance(text):
  accepted=agreement(text,positive=('是','是的','对','对的','只有一杆','一杆','就一杆'),negative=('不是','不是一杆','不止一杆','两杆','有抛球','有重打','跳过','不清楚','不知道'))
  if re.fullmatch(r'(?:是的|对|只有一杆)[，, ]*(?:没有|没)(?:抛球|重打)(?:或|和|也没|也没有)?(?:重打)?[。！!]*',text.strip()):accepted=True
  if re.search(r'(?:打了|打过)(?:两|三|2|3)杆|(?:中间)?有抛球|(?:中间)?有重打',text) and not re.search(r'没有抛球|没有重打|没抛球|没重打',text):accepted=False
  if accepted is not None:
   current=pair(s)
   if tuple(pending['scope'])!=scope(s) or now-pending['asked_at']>300 or not current or [r['id'] for r in current]!=pending['pair_ids'] or not all(live(s,r) for r in current):
    j.pop('pending_shot_link',None);return '位置、球洞或证据已变化，请重新问上一杆距离，我再核对这两个位置。'
   j.pop('pending_shot_link',None)
   if accepted is False:
    j.setdefault('rejected_shot_links',[]).append(dict(pending,answer_event=p['event_id']))
    return '明白，这两点只保留为位移，不记成单杆距离。'
   record=dict(id=p['event_id'],scope=list(scope(s)),pair_ids=pending['pair_ids'],endpoints=copy.deepcopy(current),total_horizontal_m=pending['meters'],distance_type='total_horizontal',carry=False,club=None,learning_eligible=False,confirmation_event_id=p['event_id'],valid=True)
   j.setdefault('confirmed_shot_distances',[]).append(record)
   return '记下了，上一杆水平总距离约'+amount(record['total_horizontal_m'],pending['unit'])+'，包含滚动，不是Carry。'
 if not previous_distance(text):
  if pending:j.setdefault('deferred_shot_links',[]).append(j.pop('pending_shot_link'))
  return None
 bootstrap(s);observe(s,now,query=True,preserve_played_shots=p.get('_simulation_shot_v93',False));points=pair(s);u=unit(s,text)
 if len(points)!=2 or not all(live(s,r) for r in points):return distance_answer(s,text)
 ids=[r['id'] for r in points]
 records=[r for r in j.get('confirmed_shot_distances',[]) if valid_record(s,r) and r['pair_ids']==ids and (not p.get('_audit_v87') or current_score_record(s,r))]
 if records:return '上一杆水平总距离约'+amount(records[-1]['total_horizontal_m'],u)+'，包含滚动，不是Carry。'
 meters=haversine(points[0]['point'],points[1]['point'])
 if any(r['scope']==list(scope(s)) and r['pair_ids']==ids for r in j.get('rejected_shot_links',[])):
  return '这两个位置相距约'+amount(meters,u)+'，之前已保留为位移，不能算作单杆距离。'
 if s.get('session',{}).get('draft') or any(q.get('status')=='pending' for q in s.get('questions',{}).values()):
  return '这两个位置相距约'+amount(meters,u)+'。先完成当前记分，再确认是否是一杆距离。'
 j['pending_shot_link']=dict(scope=list(scope(s)),pair_ids=ids,meters=meters,unit=u,asked_at=now,query_event_id=p['event_id'])
 return '这两个球位相距约'+amount(meters,u)+'。中间只打了一杆，没有抛球或重打，对吗？'

def record_simulated_landing(s,p,now,*,preserve_played_shots=False):
 """Save a manually submitted simulation landing as horizontal distance."""
 data=p.get('data',{})
 if p.get('protocol_version',0)>=111 and data.get('simulation_refresh'):return
 if data.get('simulation_source')!='map_click' or data.get('simulation_position_action') in ('correct','move'):return
 key=scope(s)
 course=s.get('evidence',{}).get(key[1],{}).get('data',{})
 if course.get('reference_simulation') is not True:return
 rows=pair(s)
 pos=fresh_position(s,now)
 if len(rows)!=2 or not pos or rows[-1]['id'] not in pos.get('evidence_ids',[]):return
 if not all(live(s,row) for row in rows):return
 if preserve_played_shots and simulated_tee(s,key,rows[-1]['point']):return
 if not any(s['evidence'][eid].get('observed_at')==p['observed_at'] for eid in rows[-1]['evidence_ids']):return
 hole=next((h for h in course.get('holes',[]) if h['number']==key[2]),{})
 from journey_simulation_score import simulated_green_point
 if all(simulated_green_point(hole,row['point']) for row in rows):return
 j=s['journey']
 ids=[row['id'] for row in rows]
 records=j.setdefault('confirmed_shot_distances',[])
 if rows[-1].get('relief_position'):return
 if any(row['scope']==list(key) and row['pair_ids']==ids and row.get('valid') for row in records):return
 if any(row['scope']==list(key) and row['pair_ids']==ids for row in j.get('rejected_shot_links',[])):return
 report=j.get('previous_club_reports',{}).get(canonical([*key,*ids]),{})
 choice=j.get('simulated_club_choice',{}) if preserve_played_shots else {}
 if (choice and choice['scope']==list(key) and 0<=now-choice['at']<=900
     and haversine(choice['point'],rows[0]['point'])<=5):
  report=report or dict(club=choice['club'],source='confirmed_simulation_plan',event_id=choice['event_id'])
  j.pop('simulated_club_choice',None)
 records.append(dict(id=p['event_id'],scope=list(key),pair_ids=ids,endpoints=copy.deepcopy(rows),
                     total_horizontal_m=haversine(rows[0]['point'],rows[1]['point']),
                     distance_type='total_horizontal',carry=False,learning_eligible=False,
                     club=report.get('club'),club_source=report.get('source'),club_event_id=report.get('event_id'),
                     valid=True,simulated_landing=True))
 return True
