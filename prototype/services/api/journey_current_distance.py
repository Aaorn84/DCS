"""Protocol 39: short '打多少' asks current distance, never hypothetical remainder."""
import copy,hashlib,re
from round_state import require,canonical

def current_distance(text):
 return isinstance(text,str) and re.fullmatch(r'(?:这杆|这一杆|现在)?打(?:多少|多远|几码|几米)(?:码|米)?',re.sub(r'[\s，,。！!？?]','',text)) is not None

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==39,'unsupported current-distance protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();prior=s.get('journey',{}).get('current_distance_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 adapted=copy.deepcopy(p);adapted['protocol_version']=38
 if p.get('type')=='message' and current_distance(p.get('text')):
  unit='米' if '米' in p['text'] else '码' if '码' in p['text'] else s.get('journey',{}).get('profile',{}).get('units',{}).get('value','码')
  adapted['text']='还有多少'+unit
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now)
 s['journey'].setdefault('current_distance_receipts',{})[p['event_id']]=sha
 return result
