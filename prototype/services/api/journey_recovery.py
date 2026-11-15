"""Protocol 51: keep location continuity and previous-club prompts valid on resume."""
import hashlib,re
from round_state import canonical,require
from shot_links import scope,observe
from journey_previous_club import pair_key,blocked
from journey_tee_options import silent

QUESTION='刚才那杆用的什么杆？'

def live_club_prompt(s,now):
 j=s.get('journey',{});pending=j.get('pending_previous_club')
 return bool(pending and j.get('stage')=='active'
             and j.get('profile',{}).get('shot_recording',{}).get('value') is True
             and 0<=now-pending['at']<=300 and pending['key']==pair_key(s,now)
             and not blocked(s))

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==51,'unsupported journey recovery protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{})
 prior=j.get('journey_recovery_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 stage=j.get('stage');text=p.get('text','')
 resume=p.get('type')=='resume' or (p.get('type')=='message' and text.strip() in ('继续刚才的问题','刚才问什么','刚才问的是什么'))
 pending=j.get('pending_previous_club')
 result=None
 if pending:
  if not live_club_prompt(s,now):j.pop('pending_previous_club',None)
  elif resume:
   muted=silent(s)
   result={'text':'' if muted else QUESTION,'speak_allowed':not muted,'choices':['跳过']}
 if result is None:
  from journey import reduce_journey as previous
  result=previous(s,dict(p,protocol_version=50),seq,now)
  j=s['journey']
 if result.get('simulation_hole_switched') is not None and not result.get('duplicate'):
  target_scope=scope(s)
  j['shot_location_candidates']=[r for r in j.get('shot_location_candidates',[])
                                 if (r['round_id'],r['course'],r['hole'])!=target_scope]
  # Keep confirmed records and their evidence; restart only the active candidate sequence.
  observe(s,now,query=True)
  for key in ('pending_previous_club','pending_shot_link'):j.pop(key,None)
 elif j.get('pending_previous_club') and not live_club_prompt(s,now):
  j.pop('pending_previous_club',None)
 if stage=='ready' and j.get('stage')=='active' and text=='开始球局':
  from tee_strategy import analyze
  if analyze(s,now):
   result={**result,'text':result.get('text','').replace('演示定位尚未提交，询距前请先发送位置。','发球台定位已确认，可以直接询距。')}
 j.setdefault('journey_recovery_receipts',{})[p['event_id']]=sha
 return result
