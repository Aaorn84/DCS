"""Scoped prior shot evidence: archived compact inputs for the shared strategy core."""
import copy,hashlib
from round_state import canonical,fact_value
from report_geometry import mapped_polygons,_geometry_cache

STRATEGY_HISTORY_ROUNDS=5

def _tee(value):
 return value.replace('Tee','台').replace('tee','台') if isinstance(value,str) else None

def _signature(hole):
 fields=('number','source_hole_id','par','published_yardage','display_paths','surface_zones','objects','tee_bbox','green_bbox','simulation_positions','boundary_segments')
 return hashlib.sha256(canonical({k:hole.get(k) for k in fields}).encode()).hexdigest()

def _course(state):
 return state.get('evidence',{}).get(fact_value({'facts':state.get('facts',{})},'context.course_snapshot'),{}).get('data',{})

def _archive(state,rid,eid,course,only_hole=None):
 from projected_ledger import ball_counts
 j=state.get('journey',{});out={}
 for hole in course.get('holes',[]):
  if only_hole is not None and hole['number']!=only_hole:continue
  number=hole['number'];flow=j.get('round_ledger',{}).get(canonical([rid,eid,number]))
  if not flow or flow.get('pending'):continue
  from shot_review_evidence import replay_origin_conflicts,counted
  stroke_numbers={r['id']:r['stroke_number'] for r in counted(flow)}
  conflicts=replay_origin_conflicts(flow)
  rows=[];polygons=None
  for item in flow.get('sequence',[]):
   if item.get('kind')!='stroke' or not item.get('active',True) or item.get('ball_id') not in flow.get('balls',{}) or not ball_counts(flow,item['ball_id']):continue
   if item.get('source')=='score_placeholder':continue
   origin=item.get('origin');landing=item.get('landing');hazards=[]
   for incident in flow.get('incidents',[]):
    if incident.get('shot_id')!=item['id'] or incident.get('status')=='cancelled' or incident.get('phase')!='closed' or incident.get('cause') not in ('ob','water'):continue
    penalties=any(v.get('kind')=='penalty' and v.get('active',True) and v.get('incident_id')==incident['id'] for v in flow['sequence'])
    ball=flow['balls'][item['ball_id']]
    confirmed=incident.get('confirmation')=='user_confirmed' or penalties or ball.get('status') in ('ob','water') or (incident['cause']=='water' and ball.get('inside_penalty_area'))
    if confirmed:hazards.append(incident['cause'])
   surface=None;surface_evidence=None
   if landing or item.get('landing_report'):
    if polygons is None:polygons=mapped_polygons(hole,course.get('reference_simulation') is True)
    from shot_landing_evidence import classify
    surface_evidence=classify(state,hole,item,scope=[rid,eid,number],polygons=polygons)
    surface=surface_evidence['kind'] if surface_evidence and (surface_evidence['source']=='map_geometry' or surface_evidence.get('confirmation','confirmed')=='confirmed') else None
   rows.append(dict(id=item['id'],stroke_number=stroke_numbers[item['id']],club=item.get('club'),origin=copy.deepcopy(origin),landing=copy.deepcopy(landing),hazards=sorted(set(hazards)),landing_surface=surface,distance_m=item.get('distance_m'),distance_kind='total_horizontal_not_carry'))
   if surface_evidence:
    rows[-1]['landing_source']=surface_evidence['source']
    rows[-1]['landing_location']=dict(lie_type=surface_evidence['kind'],area=surface_evidence.get('area'),source=surface_evidence['source'],confirmation=surface_evidence.get('confirmation','pending'),green_status=surface_evidence.get('green_status','unknown'))
   if item['id'] in conflicts:rows[-1].update(distance_valid=False,distance_issue=conflicts[item['id']]['reason'])
  if rows:out[str(number)]=dict(signature=_signature(hole),shots=rows)
 return out

def archive_current(state):
 j=state.get('journey',{});r=j.get('round') or {}
 if j.get('memory_allowed') is not True or not r.get('finished'):return
 entry=next((v for v in reversed(j.get('history',[])) if v.get('round',{}).get('id')==r.get('id')),None)
 if entry is None:return
 entry['hole_history']=_archive(state,r['id'],fact_value(state,'context.course_snapshot'),_course(state))
 entry['hole_history_version']=1

def records(state,number):
 j=state.get('journey',{});current=j.get('round') or {};course=_course(state)
 if j.get('memory_allowed') is not True:return []
 hole=next((h for h in course.get('holes',[]) if h['number']==number),None)
 if not hole or not _tee(current.get('tee')):return []
 cache=_geometry_cache.get();key=('hole_history',id(j),current.get('id'),fact_value(state,'context.course_snapshot'),number)
 if cache is not None and key in cache:return cache[key]
 signature=_signature(hole);result=[];seen=set()
 # Old finished rounds still in the retained ledger can be read without inventing data.
 index_key=('history_course_index',id(j),len(j.get('history',[])))
 index=cache.get(index_key) if cache is not None else None
 if index is None:
  index={}
  for entry in reversed(j.get('history',[])):
   old=entry.get('round',{})
   index.setdefault((old.get('course'),_tee(old.get('tee'))),[]).append(entry)
  if cache is not None:cache[index_key]=index
 for entry in index.get((current.get('course'),_tee(current.get('tee'))),[]):
  old=entry.get('round',{});rid=old.get('id')
  if not rid or rid in seen or rid==current.get('id') or not old.get('finished') or old.get('course')!=current.get('course') or _tee(old.get('tee'))!=_tee(current.get('tee')):continue
  # Count completed rounds before looking up this hole: missing/changed maps
  # must not pull older rounds back into the recent-five window.
  if len(seen)>=STRATEGY_HISTORY_ROUNDS:break
  seen.add(rid)
  data=entry.get('hole_history',{}).get(str(number))
  if data is None:
   eid=fact_value(state,'context.course_snapshot')
   data=_archive(state,rid,eid,course,only_hole=number).get(str(number))
  if not data or data.get('signature')!=signature:continue
  for shot in data.get('shots',[]):result.append(dict(shot,round_id=rid))
 if cache is not None:cache[key]=result
 return result
