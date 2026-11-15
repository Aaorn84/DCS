"""Protocol 38: simulation reposition and contextual tee assent, with provisional displacement."""
import copy,hashlib,re
from round_state import require,canonical,fact_value
from dialogue_routing import assent,scope
from club_selection import selection

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==38,'unsupported round-flow protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{})
 prior=j.get('round_flow_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 adapted=copy.deepcopy(p);adapted['protocol_version']=37
 text=p.get('text','');c=j.get('consultation') or {}
 # An explicit simulated map placement is a teleport, not a physical GPS trajectory.
 course=s.get('evidence',{}).get(fact_value(s,'context.course_snapshot'),{}).get('data',{})
 simulated=p.get('type')=='gps' and p.get('data',{}).get('simulation_source')=='map_click' and course.get('reference_simulation') is True
 if simulated:
  tracker=s.get('session',{}).get('gps_tracker',{})
  saved=copy.deepcopy(tracker)
  tracker.pop('last',None);tracker['pending']=None
 # Scope generic assent to a single existing tee proposal; never choose between alternatives.
 confirming=p.get('type')=='message' and c.get('phase')=='tee_commit' and bool(c.get('suggestion')) and assent(text) is True and not j.get('pending_score') and (j.get('response_context',{}).get('question_owner')=='plan.confirm' or j.get('single_proposal_event')==j.get('response_context',{}).get('event_id'))
 if confirming:adapted['text']='按这个打'
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now);j=s['journey']
 if p.get('type')=='message' and selection(text) and (j.get('consultation') or {}).get('phase')=='tee_commit':j['single_proposal_event']=p['event_id']
 if simulated and result.get('ignored'):s['session']['gps_tracker']=saved
 elif simulated:result={**result,'simulation_reposition':True}
 j.setdefault('round_flow_receipts',{})[p['event_id']]=sha
 return result
