"""Optional previous-club follow-up. A reported club is not a confirmed stroke link."""
import copy,hashlib,re
from round_state import require,canonical
from shot_links import scope,pair,live,valid_record
from shot_evidence import haversine
from lie_position import fresh_position
from dialogue_routing import pending_owner
from journey_tee_options import silent

def pair_key(s,now):
 rows=pair(s);pos=fresh_position(s,now)
 if len(rows)!=2 or not pos or not all(live(s,r) for r in rows):return None
 endpoint=rows[-1]['point'];fix=pos['value']
 if haversine(endpoint,fix)>max(5,min(15,endpoint['accuracy_m']+fix['accuracy_m'])):return None
 ids=[r['id'] for r in rows];key=[*scope(s),*ids]
 if any(r['scope']==list(scope(s)) and r['pair_ids']==ids for r in s['journey'].get('rejected_shot_links',[])):return None
 return canonical(key)

def reported_club(text):
 clean=re.sub(r'[\s，,。！!]','',text)
 m=re.fullmatch(r'(?:(?:刚才(?:那杆)?|上一杆)?(?:实际)?(?:用的是|用了|用的))?(一号木|1号木|[2-9二两三四五六七八九](?:号)?(?:铁木杆|混合杆|铁|木)|[pPgGaAsSlL][wW]|[2-9]\d度(?:杆)?)',clean)
 if not m:return None
 return m[1].translate(str.maketrans('一二两三四五六七八九','1223456789')).upper()

def blocked(s):
 j=s.get('journey',{});c=j.get('consultation') or {}
 return (pending_owner(s) or c.get('phase')=='tee_options' or
         any(q.get('status')=='pending' for q in s.get('questions',{}).values()) or
         j.get('response_context',{}).get('question_owner') in ('pin.depth','pin.side'))

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==50,'unsupported previous-club protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{})
 prior=j.get('previous_club_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 message=p.get('type')=='message';text=p.get('text','')
 allowed=j.get('stage')=='active' and j.get('profile',{}).get('shot_recording',{}).get('value') is True
 pending=j.pop('pending_previous_club',None) if message else None
 key=pair_key(s,now) if allowed and pending else None
 result=None
 if message and pending and key and pending['key']==key and 0<=now-pending['at']<=300 and not blocked(s):
  club=reported_club(text)
  if club:
   j.setdefault('previous_club_reports',{})[key]={'club':club,'event_id':p['event_id'],'source':'user_report'}
   result={'text':f'记下了，刚才用的是{club}。'}
  elif text.strip() in ('跳过','不知道','不清楚','不记','先不记'):
   result={'text':'好，这杆的用杆先留空。'}
  if result:
   result['speak_allowed']=not silent(s)
   if not result['speak_allowed']:result['text']=''
 if result is None:
  from journey import reduce_journey as previous
  result=previous(s,dict(p,protocol_version=49),seq,now);j=s['journey']
 # A location pair becomes a distance record only through existing single-stroke confirmation.
 for row in j.get('confirmed_shot_distances',[]):
  if row.get('club') is not None or not valid_record(s,row):continue
  report=j.get('previous_club_reports',{}).get(canonical([*row['scope'],*row['pair_ids']]))
  if report:row.update(club=report['club'],club_source=report['source'],club_event_id=report['event_id'])
 if allowed and message and result.get('distance',{}).get('target')=='green_center' and result.get('text') and not silent(s) and not blocked(s):
  key=pair_key(s,now)
  known=any(row.get('club') and valid_record(s,row) and canonical([*row['scope'],*row['pair_ids']])==key for row in j.get('confirmed_shot_distances',[]))
  if key and not known and key not in j.get('previous_club_reports',{}) and key not in j.get('previous_club_asked',{}):
   j.setdefault('previous_club_asked',{})[key]=p['event_id']
   j['pending_previous_club']={'key':key,'at':now}
   result={**result,'text':result['text']+'刚才那杆用的什么杆？'}
 j.setdefault('previous_club_receipts',{})[p['event_id']]=sha
 return result
