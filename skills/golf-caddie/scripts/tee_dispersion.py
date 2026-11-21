"""Final-rest tee dispersion, never Carry or penalty probability. No guessed targets."""
import math,copy
from round_state import canonical,fact_value
from shot_evidence import haversine

def capture(state,flow):
 j=state['journey'];last=j.get('last_consultation') or {};decision=last.get('decision') or {}
 opening=flow.get('open_shot') or {};point=decision.get('aim_point')
 if not point or decision.get('club')!=opening.get('club'):return
 if decision.get('hole')!=flow['scope'][2]:return
 # A stale discussion must not lend its target to a later shot.
 plans=[p for p in j.get('player_decisions',[]) if p.get('round_scope')==flow['scope']]
 if not plans or plans[-1].get('club')!=decision.get('club'):return
 origin=opening.get('origin')
 version=decision.get('position_version');position=state.get('facts',{}).get('context.device_position',{})
 if version is None or version!=position.get('version') or not origin:return
 opening['confirmed_target']=dict(point=copy.deepcopy(point),source='user_confirmed_plan',decision_event=plans[-1]['event_id'],scope=list(flow['scope']))

def sync(state):
 from ball_rules import current
 j=state.get('journey',{});flow=current(state)
 if not flow:return
 opening=flow.get('open_shot') or {};target=opening.get('confirmed_target')
 if target and opening.get('stroke_id'):
  stroke=next((v for v in flow['sequence'] if v['id']==opening['stroke_id']),None)
  if stroke is not None and 'confirmed_target' not in stroke:stroke['confirmed_target']=copy.deepcopy(target)
 # Only revisit the current hole's small ledger; fingerprint skips unchanged state.
 token=canonical([flow['scope'],[(v.get('id'),v.get('active'),v.get('club'),v.get('origin'),v.get('landing'),v.get('confirmed_target')) for v in flow.get('sequence',[]) if v.get('kind')=='stroke']])
 if j.get('tee_dispersion_token')==token:return
 j['tee_dispersion_token']=token
 scope=canonical(flow['scope']);samples=j.setdefault('tee_dispersion_samples',[])
 samples[:]=[v for v in samples if v['scope']!=scope and (j.get('memory_allowed') is True or __import__('json').loads(v['scope'])[0]==flow['scope'][0])]
 course=state.get('evidence',{}).get(flow['scope'][1],{}).get('data',{})
 hole=next((h for h in course.get('holes',[]) if h['number']==flow['scope'][2]),{})
 tee=hole.get('simulation_positions',{}).get('tee');box=hole.get('tee_bbox')
 strokes=[v for v in flow.get('sequence',[]) if v.get('kind')=='stroke' and v.get('active',True) and v.get('source')!='score_placeholder']
 if strokes:
  shot=strokes[0];origin=shot.get('origin');end=shot.get('landing');aim=(shot.get('confirmed_target') or {}).get('point')
  on_tee=bool(origin and ((box and box[0]<=origin['longitude']<=box[2] and box[1]<=origin['latitude']<=box[3]) or (tee and haversine(origin,tee)<=15)))
  if on_tee and aim and end and shot.get('club') and all(type(p.get('accuracy_m')) in (int,float) and 0<=p['accuracy_m']<=15 for p in (origin,end)):
   c=math.cos(math.radians(origin['latitude']))
   def xy(p):return ((p['longitude']-origin['longitude'])*111195*c,(p['latitude']-origin['latitude'])*111195)
   x,y=xy(aim);u,v=xy(end);length=math.hypot(x,y)
   if length>1:
    samples.append(dict(scope=scope,stroke_id=shot['id'],club=shot['club'],lateral_m=(u*y-v*x)/length,longitudinal_m=(u*x+v*y)/length-length,position_accuracy_m=max(origin['accuracy_m'],end['accuracy_m']),simulation=course.get('reference_simulation') is True or course.get('synthetic') is True))
 del samples[:-200]
 summaries={}
 for club in {v['club'] for v in samples}:
  # Simulation is useful for testing, but never calibrates personal ability.
  rows=[v for v in samples if v['club']==club and not v['simulation']]
  if not rows:continue
  def percentile(values,q):
   values=sorted(values);return values[round((len(values)-1)*q)]
  summaries[club]=dict(samples=len(rows),status='provisional' if len(rows)<30 else 'descriptive_only',distance_kind='final_rest_includes_roll_not_carry',lateral_median_m=percentile([v['lateral_m'] for v in rows],.5),lateral_p10_m=percentile([v['lateral_m'] for v in rows],.1),lateral_p90_m=percentile([v['lateral_m'] for v in rows],.9),longitudinal_median_m=percentile([v['longitudinal_m'] for v in rows],.5),usable_for_safety_probability=False)
 j['tee_dispersion_summary']=summaries
