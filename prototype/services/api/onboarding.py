"""First conversation and profile collection, independent of golf state transitions."""
import re
from round_state import require
from application_questions import QUESTIONS
ORDER=['name','proactive','shot_recording','driver','seven','miss','course','tee','start_hole','ready']

def handle(s,p,seq,now,ask,result):
 j=s['journey'];text=p['text'].strip();stage=j['stage']
 def remember(key,value):j['profile'][key]=dict(value=value,source='user_report',event_id=p['event_id'])
 if text in ('先打球，稍后了解','直接开始','先打球') and stage in ('memory',)+tuple(ORDER[:8]):
     j['onboarding_deferred']=stage
     if j['memory_allowed'] is None:j['memory_allowed']=False
     return ask('course','先打球，没了解的资料保留未知，不影响今天的服务。')
 if text in ('关闭教练','不想提升'):
     j['coach']={'enabled':False,'plan':None}
     if stage in ('coach_consent','focus','plan_confirm','practice'):return ask('postgame' if j['round'] and j['round'].get('finished') else 'course','好，关闭教练，不再主动安排或追踪练习。')
     return result('好，关闭教练，球童和陪伴服务照常。')
 if text in ('关闭跨场记忆','不跨场保存'):
     j['memory_allowed']=False;j['coach']={'enabled':False,'plan':None}
     return result('好，个人资料仅用于本场，不再沿用到下一场；跨场教练也已关闭。操作日志仅用于恢复与审计。')
 if text=='允许跨场记忆':
     j['memory_allowed']=True;return result('好，后续跨场使用你明确确认的资料，你随时可以关闭。')
 from conversation_preferences import preferred_unit, agreement, agreement_without_unit
 unit=preferred_unit(text)
 unit_prefix=''
 if unit:
     remember('units',unit);unit_prefix='好，距离改用'+unit+'。'
     choices={'memory':((),('仅本场','跳过')),'proactive':(('可以提醒',),('你叫我再说','跳过')),'shot_recording':(('可以记录',),('不记录击球','跳过'))}
     pos,neg=choices.get(stage,((),()))
     remaining=agreement_without_unit(text,positive=pos,negative=neg)
     if stage not in choices or remaining is None:
         return ask(stage,unit_prefix) if stage in QUESTIONS else result(unit_prefix)
     text='可以' if remaining else '不要'
 if text.startswith('记住：'):
     require(j['memory_allowed'] is True,'cross-round memory not authorized')
     require(len(text[3:])<=500,'memory too long')
     remember('personal_note',text[3:]);return result('记住了，你随时可以说“忘记个人备注”。')
 if text=='忘记个人备注':j['profile'].pop('personal_note',None);return result('个人备注已从当前档案移除；操作审计记录不作为伙伴记忆使用。')
 if stage=='memory':
     accepted=agreement(text,positive=('可以记住',),negative=('仅本场','跳过'))
     if accepted is None:return ask(stage)
     j['memory_allowed']=accepted;return ask('name',unit_prefix)
 if stage=='name':
     if text!='跳过':remember('name',text[:40])
     return ask(ORDER[ORDER.index(stage)+1])
 if stage in ('proactive','shot_recording'):
     pos=('可以提醒',) if stage=='proactive' else ('可以记录',)
     neg=('你叫我再说','跳过') if stage=='proactive' else ('不记录击球','跳过')
     accepted=agreement(text,positive=pos,negative=neg)
     if accepted is None:return ask(stage)
     remember(stage,accepted)
     return ask(ORDER[ORDER.index(stage)+1],unit_prefix)
 if stage in ('driver','seven'):
     total=re.fullmatch(r'总距离\s*(\d{2,3})(码|米)?',text)
     if total:
         remember(stage,{'distance':int(total[1]),'units':total[2] or j['profile'].get('units',{}).get('value','码'),'distance_type':'total'})
         return ask(stage,'总距离单独记下了；这里只了解Carry，也可以跳过。')
     match=re.fullmatch(r'(?:Carry|carry|落地)?\s*(\d{2,3})(码|米)?',text)
     if not match:
         if text in ('不知道','跳过'):return ask('seven' if stage=='driver' else 'miss')
         return ask(stage,'可以回答一个大概数字，也可以跳过。')
     distance=int(match[1]);require(10<=distance<=400,'distance outside prototype range')
     remember(stage,{'distance':distance,'units':match[2] or j['profile'].get('units',{}).get('value','码'),'distance_type':'carry'})
     return ask(ORDER[ORDER.index(stage)+1])
 if p['type']=='message' and j.get('finder_pending') and (j['stage']!='active' or j['finder_pending'].get('optional')):
     from fairway_finder import handle as finder_reply
     reply=finder_reply(s,text,p['event_id'])
     if reply is not None:return result(reply)
 if stage=='miss':
     if text!='跳过':remember('usual_miss',text[:100])
     if not j['profile'].get('fairway_finder') and not j.get('finder_onboarding_asked'):
         j['finder_onboarding_asked']=True;j['finder_onboarding_pending']=True
         j['stage']='course'
         return result('哪支杆是你最信任的保底开球杆？可以说“5号木”或“4号铁”，之后给保守方案时我会结合它比较，不再反复问。也可以跳过，或直接选择今天的球场。',choices=['5号木','铁木杆','4号铁','跳过',*QUESTIONS['course'][1]])
     return ask('course')
 if stage=='course':
     if j.get('finder_onboarding_pending'):
         from club_selection import selection
         combined=re.fullmatch(r'(.+?)(?:Carry|carry|落地)?\s*(\d{2,3})(码|米)?',re.sub(r'[，,。！!\s]','',text))
         chosen=selection(combined[1],hybrid=True,expanded=True) if combined else selection(text,hybrid=True,expanded=True)
         if combined and chosen:
             distance=int(combined[2]);require(10<=distance<=400,'distance outside prototype range')
             remember(chosen['key'],dict(distance=distance,units=combined[3] or j['profile'].get('units',{}).get('value','码'),distance_type='carry',club_name=chosen['label']))
         if chosen:
             remember('fairway_finder',dict(club_key=chosen['key'],club_name=chosen['label']))
             j.pop('finder_onboarding_pending',None)
             return ask('course','记下了，'+chosen['label']+'是你的保底开球杆。')
         if text=='跳过':
             j.pop('finder_onboarding_pending',None)
             return ask('course','好，暂不设置。')
         if text in QUESTIONS['course'][1]:j.pop('finder_onboarding_pending',None)

     if text!='东莞凤凰山（A+B蓝台演示）':return ask(stage)
     j['number']+=1;j['round']={'id':'round-'+str(j['number']),'course':'dongguan-phoenix-ab-blue-demo','synthetic':False,'reference_simulation':True,'finished':False}
     return ask('tee')
 if stage=='tee':
     if j['round']['course']=='dongguan-phoenix-ab-blue-demo' and text!='蓝台':return ask('tee','凤凰山演示先使用A+B蓝台组合。')
     j['round']['tee']=None if text=='跳过' else text[:30]
     return ask('start_hole','暂未通过定位确认发球台。')
 if stage=='start_hole':
     allowed=range(1,19)
     if not text.isdigit() or int(text) not in allowed:return ask(stage)
     j['round']['start_hole']=int(text);j['round']['start_hole_source']='user_report';return ask(ORDER[ORDER.index(stage)+1])
 if stage=='ready':return result('准备好后说“开始球局”。')
 return None
