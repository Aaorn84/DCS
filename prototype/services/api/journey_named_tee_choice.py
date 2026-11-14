"""Protocol 49: naming an offered club explicitly selects that tee route."""
import copy,hashlib,re
from round_state import require,canonical

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==49,'unsupported tee-choice protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();prior=s.get('journey',{}).get('named_tee_choice_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 from dialogue_routing import scope
 from club_selection import selection,same_label
 from journey_tee_options import response
 j=s.get('journey',{});offer=j.get('tee_route_options') or {}
 text=p.get('text','');picked=None;route=None
 if (p.get('type')=='message' and j.get('stage')=='active'
     and (j.get('consultation') or {}).get('phase')=='tee_options'
     and offer.get('status')=='awaiting_choice' and offer.get('scope')==scope(s)
     and not s.get('session',{}).get('draft')
     and not any(q.get('status')=='pending' for q in s.get('questions',{}).values())):
  driver_alias=re.fullmatch(r'(?:用|选)?\s*(?:[1一]号码|driver|diver)\s*(?:吧)?[。！! ]*',text.strip(),re.IGNORECASE)
  alias='一号木' if driver_alias else text
  picked=selection(alias)
  matches=[r for r in offer['routes'] if picked and r['club_key']==picked['key'] and same_label(r['club'],picked['label'])]
  if len(matches)==1:route=matches[0]
 adapted=copy.deepcopy(p);adapted['protocol_version']=47
 if route:adapted['text']='保守方案' if route['kind']=='conservative' else '进取方案'
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now)
 j=s['journey'];c=j.get('consultation') or {}
 # The previous reducer validates the saved offer against the current tee and map.
 if route and c.get('phase')=='tee_commit' and (c.get('selection_report') or {}).get('event_id')==p['event_id']:
  c['decision']=copy.deepcopy(c['suggestion']);j['last_consultation']=copy.deepcopy(c);j.pop('consultation')
  j.pop('last_pending_prompt',None);j.get('question_prompts',{}).pop('plan.confirm',None)
  kind='进取' if route['kind']=='aggressive' else '保守'
  result=response(s,p,{'text':f"好，走{kind}路线，用{route['club']}打向落区{route['target']}。按自己的节奏打。"},now)
 s['journey'].setdefault('named_tee_choice_receipts',{})[p['event_id']]=sha
 return result
