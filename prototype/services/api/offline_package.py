"""Versioned account-local downloads; no tokens, receipts, or unrelated history."""
import hashlib,json,copy
from round_state import fact_value
from shared_core import CORE_VERSION,CORE_DATASET
from report_geometry import planning_geometry_cache

@planning_geometry_cache
def build(state):
 j=state.get('journey',{});eid=fact_value(state,'context.course_snapshot')
 from offline_course import selected_course
 course=selected_course(state)
 from state_components import materialize
 payload=materialize(dict(schema=1,core_version=CORE_VERSION,dataset=CORE_DATASET,local_rules_version=1,local_command_semantics=2,round=copy.deepcopy(j.get('round')),course=copy.deepcopy(course),profile=copy.deepcopy(j.get('profile',{})),dispersion=copy.deepcopy(j.get('tee_dispersion_summary',{})),capabilities=dict(local_round_engine=True,local_strategy_engine=True,full_round_offline=False)))
 payload['course']=prepare_course(payload['course'])
 # Bounded same-course/tee history, already filtered by map signature and consent.
 from hole_history import records
 history_state=dict(state,facts=dict(state.get('facts',{})),evidence={'offline-package-map':{'data':payload['course']}})
 history_state['facts']['context.course_snapshot']={'value':'offline-package-map','valid':True,'evidence_ids':[]}
 payload['history_by_hole']={str(h['number']):records(history_state,h['number'])[:500] for h in (course or {}).get('holes',[])}
 raw=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()
 return dict(package=payload,payload_json=raw.decode(),sha256=hashlib.sha256(raw).hexdigest(),source_version=state['version'])


def prepare_course(course):
 mapped=copy.deepcopy(course)
 # Map adapter: preserve explicit finite demo stake segments as input data, not core hole exceptions.
 from phoenix_demo import ID,preview
 if mapped.get('course_id')==ID and mapped.get('reference_simulation') is True:
  for h in mapped['holes']:
   segments=[]
   for group in preview(h['number'],mapped).get('test_stakes',[]):
    if group['kind']=='white':segments.append(dict(kind='ob',a=dict(group['points'][0],accuracy_m=0),b=dict(group['points'][-1],accuracy_m=0),inside_reference=dict(h['simulation_positions']['green'],accuracy_m=0),simulation_only=True,source='explicit-demo-white-stakes'))
   if segments:h['boundary_segments']=segments
 return mapped
