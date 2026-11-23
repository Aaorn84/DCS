"""Application-only events: onboarding, memory consent and post-round services."""
import re,hashlib
from datetime import datetime
from round_state import require,canonical,initial
from application_questions import QUESTIONS

def next_round(s,p,seq,now):
 j=s['journey'];require(j['stage'] in ('postgame','idle'),'finish current round first')
 fresh=initial();fresh['version']=s['version'];s.clear();s.update(fresh)
 # Preserve account profile/history only; no previous on-course state follows the user.
 keep=('profile','memory_allowed','coach','history','number','finder_onboarding_asked','finder_backfill_asked')
 if j.get('memory_allowed') is True:
  keep+=('tee_dispersion_samples','tee_dispersion_summary')
 j={k:j[k] for k in keep if k in j};j.update(round=None,quiet=False,stage='course');s['journey']=j
 if j.get('memory_allowed') is not True:
  j.update(profile={},coach={'enabled':False,'plan':None},stage='proactive')
 elif j.get('coach',{}).get('enabled') and j['coach'].get('plan'):j['stage']='practice'
 return dict(text=QUESTIONS[j['stage']][0],speak_allowed=True)

def reduce_event(s,p,seq,now):
 require(p.get('type') in ('resume','message','next_round'),'unsupported application event')
 require(not set(p)-{'type','event_id','observed_at','text'},'application event contains control fields')
 require(isinstance(p.get('event_id'),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,90}',p['event_id']),'invalid application event id')
 try:
  at=datetime.fromisoformat(p['observed_at'].replace('Z','+00:00'));require(at.tzinfo is not None and at.timestamp()<=now+300,'invalid application time')
 except (KeyError,ValueError,TypeError,AttributeError):require(False,'invalid application time')
 j=s.setdefault('journey',dict(stage='memory',profile={},memory_allowed=None,quiet=False,coach={'enabled':False,'plan':None},history=[],round=None,number=0))
 digest=hashlib.sha256(canonical(p).encode()).hexdigest();receipts=j.setdefault('application_receipts',{})
 prior=receipts.get(p['event_id'])
 if prior:
  require(prior==digest,'application event id reused with different payload');return dict(text='',speak_allowed=False,duplicate=True)
 require(len(receipts)<5000,'application event limit')
 def result(text='',**kw):return dict(text='' if j.get('quiet') else text,speak_allowed=bool(text) and not j.get('quiet'),**kw)
 def ask(stage,prefix=''):
  j['stage']=stage;return result(prefix+QUESTIONS.get(stage,('',[]))[0])
 require(j['stage'] not in ('active','finish_confirm'),'golf events require the shared core')
 if p['type']=='next_round':out=next_round(s,p,seq,now)
 elif p['type']=='resume':
  eligible=j['stage'] in ('course','tee','start_hole','ready','idle')
  if eligible and not j.get('finder_onboarding_asked') and not j.get('finder_backfill_asked') and not j['profile'].get('fairway_finder'):
   j['finder_backfill_asked']=True;j['finder_pending']=dict(round=(j.get('round') or {}).get('id'),phase='club',optional=True)
   out=result('补充了解一下：哪支杆是你最信任的保底开球杆？也可以跳过，之后不再主动重复询问。',choices=['5号木','铁木杆','4号铁','跳过'])
  else:out=ask(j['stage'])
 else:
  require(isinstance(p.get('text'),str) and 0<len(p['text'].strip())<=2000,'text required')
  text=p['text'].strip()
  if text in ('安静','先安静'):j['quiet']=True;out=result('')
  elif text in ('继续','恢复语音'):j['quiet']=False;out=ask(j['stage'])
  elif j.get('quiet'):out=result('')
  else:
   from fairway_finder import handle as finder
   reply=finder(s,text,p['event_id']) if j.get('finder_pending') or '保底' in text else None
   if reply is not None:out=result(reply)
   elif text in ('关闭教练','不想提升','关闭跨场记忆','不跨场保存','允许跨场记忆','忘记个人备注') or text.startswith('记住：'):
    from onboarding import handle
    out=handle(s,p,seq,now,ask,result)
   elif j['stage'] in ('review_offer','feeling','postgame','coach_consent','focus','plan_confirm','practice','idle'):
    from postgame_service import handle
    out=handle(s,p,seq,now,ask,result,next_round)
   else:
    from onboarding import handle
    out=handle(s,p,seq,now,ask,result)
   if out is None:out=result('这一步没有改变任何记录。')
 # next_round intentionally resets receipts with the prior round state.
 s['journey'].setdefault('application_receipts',{})[p['event_id']]=digest
 return out
