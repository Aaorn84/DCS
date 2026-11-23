"""Web event adapter. Golf decisions and mutations execute only in shared TypeScript.
Pre-game onboarding and post-game conversation remain application services.
"""
import copy,re,hashlib
from datetime import datetime
from round_state import require,fact_value,canonical
from state_components import materialize
from shared_core import web_turn,CORE_VERSION,SUPPORTED_CORES

def has_model(state):
 j=state.get('journey',{});model=j.get('offline_local_round')
 return bool(model and model.get('round_id')==(j.get('round') or {}).get('id'))

def is_active(state):return bool(state.get('journey',{}).get('shared_web_core') and has_model(state))

def should_handle(state,event):
 j=state.get('journey',{})
 if has_model(state):
  model=j['offline_local_round']
  if model.get('finished'):
   # Reporting/coach services may read the projected, archived core ledger.
   if event.get('type')=='next_round':return False
   if event.get('type')=='message':
    text=event.get('text','')
    golf_mutation=re.search(r'更正|撤销|罚杆|出界|下水|已击球|[0-9一二两三四五六七八九十]+杆',text)
    if not golf_mutation:return False
  return True
 return j.get('stage')=='ready' and event.get('type')=='message' and re.sub(r'[\s，,。]','',event.get('text',''))=='开始球局'

def reduce_event(state,payload,seq,now):
 event=payload['event'];j=state['journey'];rid=j['round']['id']
 require(isinstance(event.get('event_id'),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,90}',event['event_id']),'invalid shared web event id')
 require(event.get('type') in ('message','gps','simulation_hole','resume'),'unsupported shared web event')
 try:
  stamp=datetime.fromisoformat(event['observed_at'].replace('Z','+00:00'));require(stamp.tzinfo is not None and stamp.timestamp()<=now+300,'invalid shared web time')
 except (ValueError,TypeError,KeyError,AttributeError):require(False,'invalid shared web time')
 if event['type']=='message':require(isinstance(event.get('text'),str) and 0<len(event['text'])<=4000,'invalid shared web message')
 seed=payload.get('seed')
 if seed:
  require(j.get('stage')=='ready' and seed.get('round',{}).get('id')==rid and seed.get('core_version') in SUPPORTED_CORES,'invalid shared web seed')
  from course_install import install
  install(state,seed['course'],event['event_id'],event['observed_at'],seq)
  j['shared_web_package']={'items':[seed],'sha256':payload['sha256']};j['shared_web_context']={};j['shared_web_receipts']={}
 adoption=payload.get('adopt_package')
 if adoption:
  require(not seed and has_model(state) and adoption['package']['round']['id']==rid and adoption['package'].get('core_version')==j['offline_local_round'].get('core_version') and adoption['package'].get('core_version') in SUPPORTED_CORES,'invalid shared web adoption')
  j['shared_web_package']={'items':[adoption['package']],'sha256':adoption['sha256']};j['shared_web_context']={};j['shared_web_receipts']={}
 digest=hashlib.sha256(canonical(event).encode()).hexdigest();receipts=j.setdefault('shared_web_receipts',{});prior=receipts.get(event['event_id'])
 if prior:
  require(prior==digest,'shared web event id reused with different payload')
  return dict(text='',speak_allowed=False,shared_core=True,core_version=j['offline_local_round']['core_version'],duplicate=True)
 require(len(receipts)<5000,'shared web event limit')
 old=j.get('offline_local_round');old=materialize(old) if old and old.get('round_id')==rid else None
 require(seed or old is not None,'start shared round first')
 pinned=j['shared_web_package'];scope=payload['core_scope']+'|'+rid+'|'+pinned['sha256']
 result=web_turn(scope,lambda:materialize(pinned['items'][0]),old,event,materialize(j.get('shared_web_context',{})))
 model=result['model'];require(model and model['round_id']==rid,'shared web model missing')
 if old is None or model['revision']!=old['revision']:
  from offline_rules_adapter import project_model
  project_model(state,model,{'command':'shared_web_event','at':event['observed_at']},seq,now)
 j['shared_web_view_version']=seq;j['shared_web_core']=True;j['shared_web_context']=result['context'];j['shared_web_choices']=result['choices'];j['shared_web_carry']=result['carry'];j['quiet']=bool(result['context'].get('quiet'));j['shot_audio']=result['context'].get('audio') or {'enabled':False,'phase':'idle'}
 receipts[event['event_id']]=digest
 text=result.get('text','')
 return dict(text=text,speak_allowed=bool(text) and not j['quiet'],shared_core=True,core_version=model['core_version'],local_revision=model['revision'],strategy=result.get('strategy'),**result.get('flags',{}))

def augment_view(state,view):
 if not is_active(state):return view
 j=state['journey'];choices=j.get('shared_web_choices',[]) if not j['offline_local_round'].get('finished') or j.get('shared_web_view_version')==state['version'] else view.get('choices',[])
 if j.get('quiet'):choices=['继续']
 out=dict(view,core_runtime='shared',shared_core_version=j['offline_local_round']['core_version'],choices=materialize(choices),core_carry=materialize(j.get('shared_web_carry',[])),shot_audio=materialize(j.get('shot_audio',{})))
 partial=j.get('shared_web_context',{}).get('partialScore')
 if partial:out['round_records']=dict(view.get('round_records',{}),score_draft=dict(partial,putts=None,penalties=None,awaiting='putts'))
 return out
