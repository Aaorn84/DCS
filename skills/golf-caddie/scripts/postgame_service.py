"""Post-round analysis and opt-in coaching; no golf command execution."""
import re
from application_questions import QUESTIONS
from round_view import summary

def handle(s,p,seq,now,ask,result,next_round):
 j=s['journey'];text=p['text'].strip();stage=j['stage']
 from postgame_delivery import handle as deliver
 reply=deliver(s,text,p['event_id'])
 if reply:return result(reply['text'],choices=reply['choices'])
 if stage=='review_offer':
     answer=re.sub(r'[，,。！!？?\s]','',text)
     if answer in ('需要','要','好的','好','可以','是','分析','总结','来一个','需要总结'):
         from postgame_summary import review
         j['stage']='postgame'
         return result(review(s),choices=QUESTIONS['postgame'][1])
     if answer in ('先不总结','不用','不需要','不要','不总结','暂时不用','跳过'):
         return ask('postgame','好，先不总结。')
     if answer=='今天到这里':j['stage']='idle';return result('好，今天到这里，下次见。')
     return ask('review_offer')
 if stage=='feeling':
     j['round']['feeling']=text[:200]
     if text=='先不聊':j['stage']='idle';return result('好，今天到这里。下次准备好再叫我。')
     return ask('postgame','开心的球也值得记住。' if text=='挺开心' else '听到了，咱们按你的节奏来。')
 if stage=='postgame':
     if text=='下一场':return next_round(s,p,seq,now)
     if text=='我想改善':return ask('coach_consent')
     if text=='今天到这里':j['stage']='idle';return result('好，好好休息，下次见。')
     if text=='聊聊高光':return result('今天有没有哪一球，让你特别开心？',choices=['今天到这里','我想改善'])
     return result('我在听。你愿意继续聊，我们就聊；今天到这里也可以。')
 if stage=='coach_consent':
     if text=='愿意跟踪':
         if j['memory_allowed'] is not True:return ask('postgame','你目前选择仅本场，不会开启跨场跟踪；可以先在档案中明确授权记忆。')
         j['coach']['enabled']=True;return ask('focus')
     if text=='只聊这一次':
         j['coach']['one_off']=True;return ask('focus','只聊本次，不开启跨场跟踪。')
     if text not in ('不想提升','不愿意','不开启','不用','不需要','拒绝'):
         return ask('coach_consent','还没有改变教练设置；也可以先说“分析总结本场”。')
     return ask('postgame','好，不开启跨场教练。')
 if stage=='focus':
     if text=='先不练':return ask('postgame')
     if text not in ('减少三推','开球稳定','短杆距离感'):return ask(stage)
     j['coach']['candidate']={'focus':text,'baseline':summary(s),'source':'player_selected','checks':[],'practice':None}
     practice={'减少三推':'每次10分钟，练长推停球范围，记录尝试次数和三推次数。','开球稳定':'每次10分钟，选熟悉的开球杆和目标走廊，记录尝试与落在走廊内次数。','短杆距离感':'每次10分钟，固定一种熟悉打法练两个距离，记录目标区命中次数。'}[text]
     return ask('plan_confirm','唯一重点：'+text+'。'+practice)
 if stage=='plan_confirm':
     if text=='换个重点':return ask('focus')
     if text!='接受计划':j['coach'].pop('candidate',None);return ask('postgame')
     if j['coach'].pop('one_off',False):
         j['coach']['one_off_advice']=j['coach'].pop('candidate')
         return ask('postgame','这次只保留这一项建议，不作跨场追踪。')
     j['coach']['plan']=j['coach'].pop('candidate');return ask('postgame','计划记下了。下场先看证据，再决定巩固还是调整，不自动换重点。')
 if stage=='practice':
     if text=='暂停教练':j['coach']['paused_round']='round-'+str(j['number']+1)
     elif j['coach'].get('plan'):j['coach']['plan']['practice']=text
     return ask('course')
 if stage=='idle':
     if text=='下一场':return next_round(s,p,seq,now)
     return result('我在，想聊天就聊；准备打球时说“下一场”。',choices=['下一场'])
 return None
