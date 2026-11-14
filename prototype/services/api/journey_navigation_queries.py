"""Protocol 33: normalize current-distance wording; preserve protocol 32 replay."""
import copy,hashlib,re
from round_state import require,canonical

def distance_query(text,default='码'):
 if not isinstance(text,str):return None
 clean=re.sub(r'[\s，,。！!？?]','',text)
 short=r'(?:还有|还剩|还|剩下|剩余)?(?:多少|多远)(?:码|米)?'
 target=r'(?:距|距离|到|离)?果岭(?:参考点|中心)?(?:还有|还剩|还|剩下|剩余|有|距离)?(?:多少|多远)(?:码|米)?'
 if re.fullmatch(short,clean) or re.fullmatch(target,clean) or clean in ('距离','距离多少','距离多远'):
  return '米' if clean.endswith('米') else '码' if clean.endswith('码') else default
 return None

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==33,'unsupported navigation query protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest()
 j=s.get('journey',{});prior=j.get('navigation_query_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload')
  return {'text':'','speak_allowed':False,'duplicate':True}
 require(p['event_id'] not in j.get('receipts',{}),'event id already used by another journey protocol')
 adapted=copy.deepcopy(p);adapted['protocol_version']=32
 unit=distance_query(p.get('text'),j.get('profile',{}).get('units',{}).get('value','码')) if p.get('type')=='message' else None
 if unit:adapted['text']='还有多少'+unit
 # Only an explicit simulation map-click can retain its prior accepted simulated fix.
 # Real GPS jumps still invalidate the device position under the existing policy.
 from lie_position import fresh_position
 from round_state import fact_value,invalidate
 last_fix=copy.deepcopy(fresh_position(s,now))
 previous_gps=s.get('session',{}).get('gps_evidence')
 course=s.get('evidence',{}).get(fact_value(s,'context.course_snapshot'),{}).get('data',{})
 simulated_click=p.get('type')=='gps' and p.get('data',{}).get('simulation_source')=='map_click' and course.get('reference_simulation') is True
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now)
 if simulated_click and result.get('ignored') and result.get('reason')=='implausible_jump' and last_fix:
  s['facts']['context.device_position']=last_fix
  s['session']['gps_evidence']=previous_gps
  s['journey']['rejected_simulation_position']={'retained_version':last_fix['version'],'event_id':p['event_id']}
  invalidate(s)
  result={**result,'previous_position_retained':True}
 elif p.get('type')=='gps' and not result.get('ignored'):
  s['journey'].pop('rejected_simulation_position',None)
 notice=s['journey'].get('rejected_simulation_position')
 current=fresh_position(s,now)
 if unit and notice and current and current['version']==notice['retained_version'] and result.get('text'):
  result={**result,'text':'新选点未采用，'+result['text'].replace('从当前设备位置','从上一处有效位置',1)}
 s['journey'].setdefault('navigation_query_receipts',{})[p['event_id']]=sha
 return result
