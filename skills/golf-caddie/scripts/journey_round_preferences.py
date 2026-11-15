"""Protocol 47: round communication preferences do not govern coaching."""
import copy,hashlib,re
from round_state import require,canonical

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==47,'unsupported round-preference protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();prior=s.get('journey',{}).get('round_preference_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 def unlink():
  policy=((s.get('journey',{}).get('round') or {}).get('service_policy') or {})
  policy.pop('training_prompts',None)
 # Normalize legacy rounds too; the previous reducer can still assign the old field.
 unlink()
 adapted=copy.deepcopy(p);adapted['protocol_version']=46
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now)
 unlink()
 s['journey'].setdefault('round_preference_receipts',{})[p['event_id']]=sha
 return result
