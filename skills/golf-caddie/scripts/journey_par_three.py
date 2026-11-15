"""Protocol 43: recognized par-three tee context feeds approach advice."""
import copy,hashlib,re
from round_state import require,canonical
from tee_strategy import analyze
from approach_dialogue import requested

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==43,'unsupported par-three tee protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{});prior=j.get('par_three_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 a=analyze(s,now) if j.get('stage')=='active' else None
 c=j.get('consultation') or {}
 if p.get('type')=='message' and a and a['par']==3 and (requested(p.get('text','')) or c.get('phase') in ('ball','lie','approach_club')):
  c=j.setdefault('consultation',{'phase':'ball'})
  simulated=a.get('reference_simulation') is True
  c['ball_position_report']='simulation_selected' if simulated else c.get('ball_position_report','user_confirmed')
  c['ball_position_evidence']={'source':'confirmed_tee_area_simulation' if simulated else 'confirmed_tee_area','position_version':a['position_version'],'not_real_shot_evidence':True}
  c['lie_report']='发球台';c['lie_evidence']={'label':'发球台','source':'gps_tee_area','position_version':a['position_version'],'course_evidence':a['course_evidence']}
 adapted=copy.deepcopy(p);adapted['protocol_version']=42
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now)
 s['journey'].setdefault('par_three_receipts',{})[p['event_id']]=sha
 return result
