"""Protocol 41: explicit demo-only hole navigation, never a completed-hole observation."""
import copy,hashlib,re
from round_state import require,canonical,fact_value

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==41,'unsupported simulation navigation protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{});prior=j.get('simulation_nav_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 adapted=copy.deepcopy(p);adapted['protocol_version']=40
 switched=p.get('type')=='simulation_hole'
 if switched:
  require(j.get('stage')=='active','simulation hole switch requires active round')
  eid=fact_value(s,'context.course_snapshot');e=s.get('evidence',{}).get(eid,{})
  require(e.get('active') and e.get('data',{}).get('reference_simulation') is True,'hole switching is only available in reference simulation')
  target=p.get('hole');require(type(target) is int,'invalid simulation hole')
  hole=next((h for h in e['data'].get('holes',[]) if h['number']==target),None);require(hole is not None,'simulation hole not found')
  position=hole.get('simulation_positions',{}).get('tee');require(position is not None,'simulation tee unavailable')
  s['facts']['context.active_hole']={'value':target,'status':'confirmed','valid':True,'version':seq,'evidence_ids':[eid],'source':'simulation_navigation','event_id':p['event_id']}
  s.setdefault('session',{})['gps_tracker']={}
  for key in ('consultation','response_context','last_pending_prompt','distance_comparison_focus','tee_route_options','pending_green_followup','single_proposal_event'):j.pop(key,None)
  adapted.update(type='gps',data=dict(position,simulation_source='map_click'))
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now)
 if switched:
  require(not result.get('ignored'),'simulation tee rejected')
  result={**result,'text':'','simulation_hole_switched':p['hole'],'speak_allowed':False}
 s['journey'].setdefault('simulation_nav_receipts',{})[p['event_id']]=sha
 return result
