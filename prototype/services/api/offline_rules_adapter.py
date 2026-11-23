"""Project validated local commands into the existing journey facts/shot ledger."""
import copy
from round_state import fact_value,canonical,require
from shared_core import create_local_round,apply_local_command,totals

def reduce_event(state,payload,seq,now):
 j=state['journey'];command=payload['command'];rid=(j.get('round') or {}).get('id');eid=fact_value(state,'context.course_snapshot')
 from offline_course import selected_course
 seed=payload.get('seed')
 if seed:require(seed.get('round',{}).get('id')==rid and seed['round'].get('tee')==j['round'].get('tee'),'pinned round metadata mismatch')
 course=seed['course'] if seed else selected_course(state) or {}
 if seed or not eid or state.get('evidence',{}).get(eid,{}).get('data',{}).get('course_id')!=course.get('course_id'):
  from course_install import install
  eid=install(state,course,command['id'],command['at'],seq)
 old=j.get('offline_local_round')
 if old is None or old.get('round_id')!=rid:
  require(j.get('stage')=='ready','local rules must start from ready stage')
  old=create_local_round(seed or dict(schema=1,round=j['round'],course=course))
 model=apply_local_command(old,command);j['offline_local_round']=model;j['profile']=copy.deepcopy(model['profile'])
 return project_model(state,model,command,seq,now)

def project_model(state,model,command,seq,now):
 j=state['journey'];rid=j['round']['id'];eid=fact_value(state,'context.course_snapshot')
 j['offline_local_round']=model;j['profile']=copy.deepcopy(model['profile'])
 # This projection is the normal score/shot source, not a second /records score store.
 for key in list(state['facts']):
  if key.startswith('holes.'):state['facts'].pop(key)
 for number,h in sorted(model['holes'].items(),key=lambda item:int(item[0])):
  score=h['score']
  if score:
   for key in ('total','putts','penalties'):state['facts'][f'holes.{number}.{key}']=dict(value=score[key],valid=True,status='confirmed',version=seq,evidence_ids=[],source='offline_user_confirmed')
  scope=[rid,eid,int(number)];sequence=[]
  for r in h['rows']:
   item=copy.deepcopy(r);item['ball_id']='original'
   if item['kind']=='penalty':item['incident_id']=next((i['id'] for i in h['incidents'] if i['stroke_id']==item.get('stroke_id')),None)
   if item['kind']=='stroke':
    from shot_evidence import haversine
    item['distance_m']=haversine(item['origin'],item['landing']) if item.get('origin') and item.get('landing') else None
    if item.get('confirmed_target'):item['confirmed_target']=dict(point=item['confirmed_target'],source='user_confirmed_plan',scope=scope)
    if item.get('lie') not in (None,'unknown') or item.get('area'):
     item['landing_location']=dict(lie_type=item['lie'],area=item.get('area'),source='user_report',confirmation='confirmed' if item['lie']!='unknown' else 'pending',green_status='on' if item['lie']=='green' else 'unknown' if item['lie']=='unknown' else 'off')
     item['landing_report']=dict(item['landing_location'],scope=canonical(scope),stroke_id=item['id'])
   sequence.append(item)
  incidents=[]
  for incident in h['incidents']:
   original=next((r for r in h['rows'] if r['id']==incident['stroke_id']),{})
   incidents.append(dict(incident,id=incident['id'],shot_id=incident['stroke_id'],phase='closed',status='active',confirmation='user_confirmed',origin=original.get('origin')))
  pending=model['pending'] if int(number)==model['hole'] else None
  j.setdefault('round_ledger',{})[canonical(scope)]=dict(scope=scope,sequence=sequence,incidents=incidents,balls={'original':dict(id='original',status='in_play',parent=None)},active_ball='original',pending=copy.deepcopy(pending),projection_version=1)
 state['facts']['context.active_hole']=dict(value=model['hole'],valid=True,status='confirmed',version=seq,evidence_ids=[])
 if model['position'] is not None:
  previous=state['facts'].get('context.device_position',{}).get('value') or {}
  previous_point={k:previous.get(k) for k in ('latitude','longitude','accuracy_m')}
  if previous_point!=model['position'] or command['command']=='set_position':
   state['facts']['context.device_position']=dict(value=dict(model['position'],observed_at=command['at']),valid=True,status='confirmed',version=seq,evidence_ids=[],source='offline_user_position')
 else:state['facts'].pop('context.device_position',None)
 j.pop('round_review_cache',None)
 j['shot_audio']=dict(j.get('shot_audio') or {},phase='idle')
 j['stage']='postgame' if model['finished'] else 'finish_confirm' if model['stage']=='finish_confirm' else 'ready' if model['stage']=='ready' else 'active'
 j['round']['finished']=model['finished']
 if command['command']=='start':j['round'].setdefault('started_at',command['at'])
 if model['finished']:j['round'].setdefault('finished_at',command['at'])
 else:j['round'].pop('finished_at',None)
 # Sync only after a complete, explicit end confirmation. Undo may retract it.
 history=j.setdefault('history',[]);entry=next((r for r in history if r.get('round',{}).get('id')==rid),None)
 if model['finished']:
  total=totals(model);scores=[dict(hole=int(number),**h['score']) for number,h in sorted(model['holes'].items(),key=lambda item:int(item[0])) if h['score']]
  from course_history_comparison import basis
  archive=dict(round=copy.deepcopy(j['round']),scores=scores,confirmed_holes=total['holes'],confirmed_subtotal=total['total'],course_basis=[basis(state)])
  if entry:entry.update(archive)
  else:history.append(archive)
  from hole_history import archive_current
  archive_current(state)
 elif entry:history[:]=[r for r in history if r.get('round',{}).get('id')!=rid]
 from tee_dispersion import sync as sync_dispersion
 sync_dispersion(state)
 return dict(text='',speak_allowed=False,local_revision=model['revision'],local_totals=totals(model),saved=True)
