"""Protocol 40: optional qualitative pin location, once per round/hole, one question at a time."""
import copy,hashlib,re
from round_state import require,canonical
from dialogue_routing import assent,scope
from journey_tee_options import silent
from lie_position import fresh_position

def present(s,p,result,now,owner=None):
 j=s['journey'];muted=silent(s)
 result={**result,'text':'' if muted else result['text'],'speak_allowed':not muted and bool(result['text'])}
 row={'event_id':p['event_id'],'intent':'fact_request','domain':'pin_location','question_owner':owner if not muted else None,'scope':scope(s),'at':now,'spoken_text':result['text']}
 if j.get('dialogue_audit') and j['dialogue_audit'][-1].get('event_id')==p['event_id']:j['dialogue_audit'][-1]['presentation_status']='superseded_before_delivery'
 j['response_context']=row;j.setdefault('dialogue_audit',[]).append(copy.deepcopy(row))
 return result

def prompt(s,p,row,now):
 if row.get('depth') is None:
  return present(s,p,{'text':'这一洞的旗在果岭前部、中部，还是后部？不清楚可以跳过。','choices':['前旗','中旗','后旗','跳过']},now,'pin.depth')
 return present(s,p,{'text':'旗位偏左、居中，还是偏右？','choices':['偏左','居中','偏右','跳过']},now,'pin.side')

DEPTH_WORDS={'前':'前','前旗':'前','前部':'前','前面':'前',
             '中':'中','中旗':'中','中部':'中','中间':'中',
             '后':'后','后旗':'后','后部':'后','后面':'后'}
SIDE_WORDS={'左':'左','偏左':'左','左边':'左','中':'中','居中':'中','中间':'中',
            '右':'右','偏右':'右','右边':'右'}
def combined_pattern(sides):
 return re.compile(
 '(?P<depth>'+'|'.join(sorted(DEPTH_WORDS,key=len,reverse=True))+')'
 '(?P<side>'+'|'.join(sides)+')'
)

COMBINED_PIN=combined_pattern(SIDE_WORDS)
EXTENDED_SIDES={**SIDE_WORDS,'靠左':'左','靠右':'右','左侧':'左','右侧':'右','靠中':'中'}
EXTENDED_PIN=combined_pattern(EXTENDED_SIDES)

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==40,'unsupported pin-location protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{});prior=j.get('pin_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 adapted=copy.deepcopy(p);adapted['protocol_version']=39
 enhanced=adapted.pop('_pin_reply_v52',False)
 extended=adapted.pop('_pin_reply_v67',False)
 reverse=p.get('_dialogue_v69')
 key=canonical(scope(s));row=j.get('pin_locations',{}).get(key);result=None;text=p.get('text','');answered=False
 from short_pin_distance import estimate,pin_distance_request,pin_distance_wording
 if p.get('type')=='message' and j.get('stage')=='active' and pin_distance_request(text):
  pin=estimate(s,now,short_game_only=False)
  if pin:
   unit='米' if '米' in text else '码' if '码' in text else j.get('profile',{}).get('units',{}).get('value','码')
   result=present(s,p,{'text':pin_distance_wording(pin,unit)+'。这是旗位区域估算。','pin_distance_estimate':pin},now)
  else:
   reason='先更新当前位置，我再估算旗位距离。' if not fresh_position(s,now) else '目前缺少可用的旗位或果岭轮廓，距离可先参考果岭中心。'
   result=present(s,p,{'text':reason},now)
 owner=j.get('response_context',{}).get('question_owner')
 if result is None and p.get('type')=='message' and row and row.get('status')=='pending' and owner in ('pin.depth','pin.side'):
  clean=re.sub(r'[\s，,。！!？?]','',text)
  skip=clean in ('跳过','不知道','不清楚','看不清','不知道旗位')
  depth=DEPTH_WORDS.get(clean)
  sides=EXTENDED_SIDES if extended else SIDE_WORDS
  side=sides.get(clean)
  combined=(EXTENDED_PIN if extended else COMBINED_PIN).fullmatch(clean) if enhanced else None
  reversed_pin=re.fullmatch(r'(左|右|靠左|靠右|偏左|偏右)(前|中|后)(?:部|旗)?',clean) if reverse else None
  if combined or reversed_pin:
   depth,side=(combined['depth'],combined['side']) if combined else (reversed_pin[2],reversed_pin[1])
   row.update(depth=DEPTH_WORDS[depth],side=sides[side],status='complete')
   row['source_events'].append(p['event_id']);answered=True
  elif skip:
   if owner=='pin.depth':row['depth']='unknown'
   row['side']='unknown';row['status']='complete';answered=True
  elif owner=='pin.depth' and depth:row['depth']=depth;row['source_events'].append(p['event_id']);result=prompt(s,p,row,now)
  elif owner=='pin.side' and side:row['side']=side;row['status']='complete';row['source_events'].append(p['event_id']);answered=True
  elif enhanced and (assent(text) is not None or depth or side):
   result=prompt(s,p,row,now)
  if answered:adapted['text']='怎么打'
 if result is None:
  from journey import reduce_journey as previous
  result=previous(s,adapted,seq,now);j=s['journey'];c=j.get('consultation') or {}
  # Only actual approach strategy responses trigger this; distance facts and tee plans do not.
  strategy=c.get('phase')=='plan' and bool(c.get('strategy_assessment')) and result.get('text','').startswith(('到果岭','按你现场更正','按前旗','按中旗','按后旗'))
  if (extended and row and row.get('status')=='pending' and owner in ('pin.depth','pin.side')
      and result.get('text')=='刚才的打法方案先保留，这句话不记成击球决定。'):
   result=prompt(s,p,row,now)
  if strategy and not silent(s):
   row=j.setdefault('pin_locations',{}).get(key)
   if not row:
    row={'scope':scope(s),'status':'pending','depth':None,'side':None,'source':'user_observation','source_events':[],'coordinates':None};j['pin_locations'][key]=row
   if row['status']=='pending':result=prompt(s,p,row,now)
   else:
    parts=[row['depth']+'旗' if row['depth']!='unknown' else '',('偏'+row['side']) if row['side'] in ('左','右') else '居中' if row['side']=='中' else '']
    pin=''.join(parts)
    if pin:
     note=('记下了，' if answered else '这一洞是')+pin+'。'
     if row['side'] in ('左','右') and not c['strategy_assessment'].get('practical_rough'):note+='别为追旗贴近'+row['side']+'侧边缘。'
     pin=c['strategy_assessment'].get('pin_distance_estimate')
     if pin:result={**result,'pin_distance_estimate':pin}
     suffix='' if c['strategy_assessment'].get('practical_rough') else '这是旗位区域估算。' if pin else '目前按果岭参考点估算距离。'
     result=present(s,p,{**result,'text':note+result['text']+suffix,'pin_location':copy.deepcopy(row)},now)
 # Incomplete answers may be resumed on another strategy request; factual interruptions stay intact.
 j.setdefault('pin_receipts',{})[p['event_id']]=sha
 return result
