"""Protocol 48: skip the optional shot-recording onboarding prompt."""
import copy,hashlib,re
from round_state import require,canonical

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==48,'unsupported onboarding protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();prior=s.get('journey',{}).get('onboarding_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 j=s.get('journey',{})
 # Resume previously saved onboarding without interpreting assent as recording consent.
 if j.get('stage')=='shot_recording':j['stage']='driver'
 adapted=copy.deepcopy(p);adapted['protocol_version']=47
 from journey import QUESTIONS,reduce_journey as previous
 result=previous(s,adapted,seq,now)
 j=s['journey']
 if j['stage']=='shot_recording':
  j['stage']='driver'
  unit=j.get('profile',{}).get('units',{}).get('value','码')
  old=QUESTIONS['shot_recording'][0].replace('多少码','多少'+unit)
  new=QUESTIONS['driver'][0].replace('多少码','多少'+unit)
  result={**result,'text':result.get('text','').replace(old,new),'choices':QUESTIONS['driver'][1]}
 s['journey'].setdefault('onboarding_receipts',{})[p['event_id']]=sha
 return result
