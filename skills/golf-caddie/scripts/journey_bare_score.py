"""Protocol 45: bare total binds to an actual pending score question, not the latest GPS reply."""
import copy,hashlib,re
from round_state import require,canonical,refs_current
from round_session import N,count

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==45,'unsupported bare-score protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{});prior=j.get('bare_score_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 adapted=copy.deepcopy(p);adapted['protocol_version']=44
 session=s.get('session',{});q=s.get('questions',{}).get(session.get('question_id'),{})
 if p.get('type')=='message' and j.get('stage')=='active' and q.get('status')=='pending' and q.get('field')=='total' and refs_current(s,q.get('deps',{})) and not session.get('draft'):
  m=re.fullmatch(r'\s*'+N+r'\s*[。！!]?\s*',p.get('text',''))
  target=re.fullmatch(r'holes\.(\d+)',q.get('target',''))
  if m and target and session.get('score_target')==int(target[1]):
   value=count(m[1]);require(1<=value<=30,'invalid total')
   adapted['text']=f'{target[1]}号洞{value}杆'
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now)
 s['journey'].setdefault('bare_score_receipts',{})[p['event_id']]=sha
 return result
