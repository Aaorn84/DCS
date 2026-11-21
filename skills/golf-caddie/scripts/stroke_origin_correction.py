"""Explicit historical tee-origin correction; preserves landing and score facts."""
import copy
from round_state import require,canonical,fact_value
from shot_evidence import haversine
from shot_review_evidence import counted

def apply(state,event,now):
 j=state['journey'];data=event['data'];rid=(j.get('round') or {}).get('id')
 require(data.get('round_id')==rid,'round changed before correction')
 number=data.get('hole');stroke_number=data.get('stroke_number')
 require(type(number) is int and type(stroke_number) is int,'hole and stroke number required')
 eid=fact_value(state,'context.course_snapshot');scope=[rid,eid,number]
 flow=j.get('ball_rules',{}).get(canonical(scope));require(flow is not None,'stroke ledger missing')
 matches=[r for r in counted(flow) if r['stroke_number']==stroke_number and r['id']==data.get('stroke_id')]
 require(len(matches)==1,'target stroke changed or missing')
 shot=next(r for r in flow['sequence'] if r.get('id')==matches[0]['id'])
 course=state['evidence'][eid]['data'];hole=next((h for h in course['holes'] if h['number']==number),{})
 tee=hole.get('simulation_positions',{}).get('tee');require(tee is not None,'mapped tee required')
 require(shot.get('landing') is not None,'confirmed landing required')
 old_origin=copy.deepcopy(shot.get('origin'));old_distance=shot.get('distance_m');old_pair=shot.get('pair_ids')
 new_origin=copy.deepcopy(tee)
 for key in ('observed_at','simulation_source'):
  if old_origin and key in old_origin:new_origin[key]=old_origin[key]
 new_origin['simulation_hole']=number
 distance=haversine(new_origin,shot['landing'])
 new_id=event['event_id']+'-origin:1'
 state['evidence'][new_id]=dict(id=event['event_id']+'-origin',revision=1,source='user_correction',phase='final',active=True,
  observed_at=new_origin.get('observed_at',event['observed_at']),received_at=now,data=copy.deepcopy(new_origin),corrects_stroke=shot['id'])
 new_pair=list(old_pair) if old_pair else None
 if old_pair:
  new_pair[0]=new_id
  matching=[r for r in j.get('confirmed_shot_distances',[]) if r.get('scope')==scope and (r.get('id')==shot.get('confirmation_record_id') or r.get('pair_ids')==old_pair)]
  for record in matching:
   require(len(record.get('endpoints',[]))==2,'invalid distance endpoints')
   start=copy.deepcopy(record['endpoints'][0]);start.update(id=new_id,point=copy.deepcopy(new_origin),evidence_ids=[new_id],origin='user_corrected_replay_tee',relief_position=True,stroke_base=stroke_number-1)
   record['endpoints'][0]=start;record.update(pair_ids=list(new_pair),total_horizontal_m=distance,origin_correction_event_id=event['event_id'])
  candidates=j.get('shot_location_candidates',[]);old_candidate=next((r for r in candidates if r['id']==old_pair[0] and [r['round_id'],r['course'],r['hole']]==scope),None)
  if old_candidate:
   corrected=dict(copy.deepcopy(old_candidate),id=new_id,point=copy.deepcopy(new_origin),evidence_ids=[new_id],origin='user_corrected_replay_tee',relief_position=True,stroke_base=stroke_number-1)
   shared=any(r.get('scope')==scope and r.get('pair_ids')!=new_pair and old_pair[0] in r.get('pair_ids',[]) for r in j.get('confirmed_shot_distances',[]))
   index=candidates.index(old_candidate)
   if shared:candidates.insert(index+1,corrected)
   else:candidates[index]=corrected
  reports=j.get('previous_club_reports',{});old_key=canonical([*scope,*old_pair]);new_key=canonical([*scope,*new_pair])
  if old_key in reports:reports[new_key]=reports.pop(old_key)
  shot['pair_ids']=new_pair
 shot.update(origin=copy.deepcopy(new_origin),distance_m=distance,origin_correction_event_id=event['event_id'])
 # Keep relief bookkeeping in agreement with the user's explicit correction.
 original_index=matches[0]['sequence_index']
 for incident in flow.get('incidents',[]):
  if incident.get('status')=='cancelled' or incident.get('option')!='stroke_distance' or incident.get('promoted'):continue
  if incident.get('completed_sequence_count')==original_index:
   incident['relief_point']=copy.deepcopy(new_origin);incident['origin_correction_event_id']=event['event_id']
 ball=flow.get('balls',{}).get(shot['ball_id'])
 if ball and ball.get('parent'):ball['origin']=copy.deepcopy(new_origin)
 j.setdefault('shot_corrections',[]).append(dict(event_id=event['event_id'],round_scope=scope,stroke_id=shot['id'],stroke_number=stroke_number,old_origin=old_origin,new_origin=copy.deepcopy(new_origin),old_distance_m=old_distance,new_distance_m=distance,reason='user_confirmed_tee_origin'))
 from confirmed_shot_sync import sync_flow
 sync_flow(state,flow)
 require(haversine(shot['origin'],new_origin)<.01 and abs(shot['distance_m']-distance)<.01,'corrected origin overwritten')
 # Refresh only this hole in an already-finished round's historical snapshot.
 if (j.get('round') or {}).get('finished'):
  from hole_history import _archive
  snapshot=_archive(state,rid,eid,course).get(str(number))
  entry=next((r for r in reversed(j.get('history',[])) if r.get('round',{}).get('id')==rid),None)
  if entry is not None and snapshot is not None:
   entry.setdefault('hole_history',{})[str(number)]=snapshot;entry['hole_history_version']=1
 return dict(text=f'已将第{number}洞第{stroke_number}杆起点更正为发球台，并按原落点重算水平总距离。',speak_allowed=False,distance_m=distance)
