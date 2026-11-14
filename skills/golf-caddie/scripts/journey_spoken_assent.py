"""Protocol 46: bounded spoken assent aliases, preserving contextual confirmation gates."""
import copy,hashlib,re
from round_state import require,canonical

def spoken_assent(text):
 return isinstance(text,str) and re.fullmatch(r'\s*(?:嗯|嗯嗯|嗯好|嗯好的|嗯可以|嗯没问题)[\s。！!，,]*',re.sub(r'[\s，,]','',text)) is not None

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==46,'unsupported spoken-assent protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();prior=s.get('journey',{}).get('spoken_assent_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 adapted=copy.deepcopy(p);adapted['protocol_version']=45
 if p.get('type')=='message' and s.get('journey',{}).get('stage')=='active' and spoken_assent(p.get('text')):adapted['text']='好'
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now)
 s['journey'].setdefault('spoken_assent_receipts',{})[p['event_id']]=sha
 return result
