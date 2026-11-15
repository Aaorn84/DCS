"""Protocol 44: explicit seven-iron carry reports update profile, never shot execution."""
import copy,hashlib,re
from round_state import require,canonical

def carry_report(text):
 if not isinstance(text,str):return None
 m=re.fullmatch(r'(?:更正(?:一下)?[，,：:]?|改成|改为)?(?:7号铁|7铁|七号铁|七铁)[\s，,：:]*(?:Carry|carry|落地距离|落地)?[\s]*(?:是|为)?[\s]*(\d{2,3})(码|米)?[。！! ]*',text.strip())
 return (int(m[1]),m[2]) if m else None

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==44,'unsupported carry-report protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{});prior=j.get('carry_report_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 report=carry_report(p.get('text')) if p.get('type')=='message' and j.get('stage')=='active' else None
 c=j.get('consultation') or {}
 answering_seven=c.get('phase')=='approach_club' or (c.get('phase')=='tee_club' and c.get('requested_club')=='seven')
 if report and not answering_seven:
  distance,unit=report;require(10<=distance<=400,'distance outside prototype range');unit=unit or j.get('profile',{}).get('units',{}).get('value','码')
  old=copy.deepcopy(j.get('profile',{}).get('seven'))
  j.setdefault('profile_updates',[]).append({'field':'seven','previous':old,'event_id':p['event_id'],'at':now,'source':'user_report','not_shot_execution':True})
  j.setdefault('profile',{})['seven']={'value':{'distance':distance,'units':unit,'distance_type':'carry','club_name':'7号铁'},'source':'user_report','event_id':p['event_id']}
  # Retain the active question/route choice; this is a profile correction, not its answer.
  from journey_tee_options import silent
  muted=silent(s);result={'text':'' if muted else f'7号铁Carry已更新为{distance}{unit}，后续按这个距离选杆。','speak_allowed':not muted,'profile_updated':'seven'}
  j.setdefault('dialogue_audit',[]).append({'event_id':p['event_id'],'intent':'correction','domain':'club_profile','at':now,'spoken_text':result['text']})
 else:
  adapted=copy.deepcopy(p);adapted['protocol_version']=43
  from journey import reduce_journey as previous
  result=previous(s,adapted,seq,now)
 s['journey'].setdefault('carry_report_receipts',{})[p['event_id']]=sha
 return result
