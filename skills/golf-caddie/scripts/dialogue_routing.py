"""Bounded dialogue classification and question ownership; not unrestricted NLU.
Facts and score reports bypass consultations. Generic assent owns only the last
spoken question, while explicit record/plan confirmations retain existing gates.
"""
import re,copy
from round_state import fact_value
from conversation_preferences import agreement
from round_session import N,count
from hazard_requests import parse as hazard_query
from navigation_requests import distance_unit
from decision_queries import previous_distance,approach_selection
from short_game import comparison,question
from green_context import resolve as green_resolve

CONTROLS={'确认','确认记录','确认保存','先不记','取消记录','跳过这洞','撤销上一条记分','撤销刚才的记分'}

def scope(s):return [(s.get('journey',{}).get('round') or {}).get('id'),fact_value(s,'context.course_snapshot'),fact_value(s,'context.active_hole')]
def assent(text):return agreement(text,positive=('是','是的','对','对的','当然没问题','确认'),negative=('不是','不是的'))

def score_text(s,text):
 clean=re.sub(r'[\s。！!]+','',text).replace('，',',')
 clean=re.sub(r'^第('+N+r')洞',lambda m:m[1]+'号洞',clean)
 clean=re.sub(r',(?:没有罚杆|没罚杆|无罚杆|没有)$',',0罚杆',clean)
 # Preserve the kernel's explicit grammar. No inference from a bare number.
 if re.fullmatch(r'(?:(?:'+N+r')号洞|这洞|本洞)?'+N+r'杆(?:,'+N+r'推)?(?:,'+N+r'罚(?:杆)?)?',clean):return clean
 m=re.fullmatch(r'(?:这洞|本洞|这一洞)?(?:加|\+)'+N+r'(?:,'+N+r'推)?(?:,(没有罚杆|没有|没罚杆|无罚杆|'+N+r'罚(?:杆)?))?',clean)
 if not m:return None
 hole=fact_value(s,'context.active_hole');eid=fact_value(s,'context.course_snapshot');e=s.get('evidence',{}).get(eid,{})
 h=next((h for h in e.get('data',{}).get('holes',[]) if h['number']==hole),None) if e.get('active') and e.get('phase')=='final' else None
 if not h or not isinstance(h.get('par'),int):return None
 groups=m.groups();total=h['par']+count(groups[0]);putts=groups[1];penalty=groups[2]
 if not 1<=total<=30:return None
 normalized=str(total)+'杆'
 if putts is not None:normalized+=','+str(count(putts))+'推'
 if penalty is not None:
  if putts is None:return None # Do not change meaning by moving a missing field.
  normalized+=',0罚杆' if penalty in ('没有罚杆','没有','没罚杆','无罚杆') else ','+penalty
 return normalized

def actual_question(text):
 if re.search(r'[？?]|怎么|如何|哪[支只种个边侧]|什么|多少|多远|是否|有没有|吗|呢',text):return True
 if '还是' in text and not re.search(r'还是(?:用了|用的是|打了|选择了)',text):return True
 return False

def classify(s,text,now):
 if text in ('继续刚才的问题','刚才问什么','刚才问的是什么'):return {'type':'interaction_override','domain':'resume_question'}
 if text=='确认' and pending_owner(s)=='plan.confirm':return {'type':'pending_answer','domain':'assent'}
 if text in CONTROLS:return {'type':'score_report','domain':'score_control'}
 normalized=score_text(s,text)
 if normalized:return {'type':'score_report','domain':'score','normalized_text':normalized}
 if previous_distance(text):return {'type':'fact_request','domain':'previous_distance'}
 if hazard_query(text):return {'type':'fact_request','domain':'hazard_distance'}
 if green_resolve(s,text,now) is not None:return {'type':'fact_request','domain':'green_map'}
 if distance_unit(text,s.get('journey',{}).get('profile',{}).get('units',{}).get('value','码')):return {'type':'fact_request','domain':'current_distance'}
 if comparison(text):return {'type':'fact_request','domain':'strategy_comparison'}
 if re.search(r'怎么打|如何打|用哪|选哪|有何建议|有什么建议|给点建议|什么风险',text):return {'type':'fact_request','domain':'strategy'}
 if not actual_question(text) and (execution_club(text) or (re.search(r'刚才|上一杆',text) and re.search(r'用了|打了|打厚|打薄|偏左|偏右|打短|打长',text))):return {'type':'execution_report','domain':'reported_execution'}
 if approach_selection(text):return {'type':'decision_commitment','domain':'player_decision'}
 if assent(text) is not None:return {'type':'pending_answer','domain':'assent'}
 if actual_question(text):return {'type':'fact_request','domain':'unresolved_question'}
 return {'type':'companion_dialogue','domain':'other_or_pending_answer'}

def pending_owner(s):
 j=s.get('journey',{});draft=s.get('session',{}).get('draft')
 if draft:return 'score.'+draft['awaiting']
 if j.get('short_game_question'):return 'short_game.route'
 if j.get('pending_shot_link'):return 'distance.single_stroke'
 if j.get('pending_green_followup'):return 'green.subject'
 if j.get('pending_hazard'):return 'hazard.identity'
 c=j.get('consultation',{});phase=c.get('phase')
 return {'tee_commit':'plan.confirm','commit':'plan.confirm','tee_club':'club.carry','approach_club':'club.carry','ball':'ball.position','lie':'ball.lie','intent':'player.intent','tee_intent':'player.intent'}.get(phase)

def owner_live(s,owner):
 j=s.get('journey',{});draft=s.get('session',{}).get('draft') or {};c=j.get('consultation',{})
 if owner and owner.startswith('score.'):return owner=='score.'+str(draft.get('awaiting'))
 if owner=='short_game.route':return bool(j.get('short_game_question'))
 if owner=='distance.single_stroke':return bool(j.get('pending_shot_link'))
 if owner=='green.subject':return bool(j.get('pending_green_followup'))
 if owner=='hazard.identity':return bool(j.get('pending_hazard'))
 return owner is not None and pending_owner({'journey':{'consultation':c}})==owner

def response_owner(s,route):
 domain=route['domain'];j=s.get('journey',{})
 if domain=='green_map':return 'green.subject' if j.get('pending_green_followup') else None
 if domain=='hazard_distance':return 'hazard.identity' if j.get('pending_hazard') else None
 if domain=='previous_distance':return 'distance.single_stroke' if j.get('pending_shot_link') else None
 if domain=='strategy_comparison':return 'short_game.route' if j.get('short_game_question') else None
 if route['type']=='pending_answer' or domain=='resume_question':
  old=j.get('response_context',{}).get('question_owner')
  return old if owner_live(s,old) else pending_owner(s)
 return pending_owner(s)

def record_response(s,p,out,now):
 if p.get('type')!='message' or s.get('journey',{}).get('stage')!='active':return
 j=s['journey'];route=classify(s,p['text'],now)
 from speech_presentation import spoken_text
 spoken=spoken_text(out.get('text',''),reference_course=bool((j.get('round') or {}).get('reference_simulation')))
 owner=response_owner(s,route) if ('？' in spoken or '?' in spoken) and not j.get('quiet') else None
 response={'ordinal':len(j.get('dialogue_audit',[]))+1,'event_id':p['event_id'],'intent':route['type'],'domain':route['domain'],'question_owner':owner,'scope':scope(s),'at':now,'spoken_text':spoken}
 j['response_context']=response
 j.setdefault('dialogue_audit',[]).append(copy.deepcopy(response))
 if owner:
  j['last_pending_prompt']=copy.deepcopy(response)
  j.setdefault('question_prompts',{})[owner]=copy.deepcopy(response)

def resume(s,now):
 j=s.get('journey',{});prompts=list(j.get('question_prompts',{}).values())
 prompts=[p for p in prompts if p['scope']==scope(s) and 0<=now-p['at']<=300 and owner_live(s,p['question_owner'])]
 if not prompts:return '目前没有可恢复的待答问题，需要时直接叫我。'
 saved=max(prompts,key=lambda p:p['ordinal'])
 j['response_context']=copy.deepcopy(saved)
 return saved['spoken_text']

def guard_assent(s,text,now):
 j=s.get('journey',{});last=j.get('response_context')
 if not last or assent(text) is None:return None
 # Never let a yes/no following a factual answer commit an older plan.
 owner=last.get('question_owner')
 if not owner_live(s,owner) or last['scope']!=scope(s) or now-last['at']>300:
  return '收到，刚才的方案仍待确认。' if owner_live(s,'plan.confirm') else '收到，成绩仍待确认。' if owner_live(s,'score.confirm') else '好的。'
 return None


def execution_club(text):
 if actual_question(text) or re.search(r'没用|没有用|不是|想用|准备用|可能',text):return None
 m=re.search(r'(?:用了|用的是|用的)(一号木|1号木|三号木|3号木|[2-9二两三四五六七八九](?:号铁|铁))',text)
 if not m:return None
 label=m[1].translate(str.maketrans('一二两三四五六七八九','1223456789'))
 return label.replace('铁','号铁') if '号' not in label else label

def save_execution(s,p):
 club=execution_club(p['text'])
 if not club:return None
 row={'event_id':p['event_id'],'hole':None,'context_hole':fact_value(s,'context.active_hole'),'club':club,'source':'user_report','type':'execution_report','attribution':'unattributed','shot_id':None,'long_term_learning':False,'text':p['text']}
 s['journey'].setdefault('execution_reports',[]).append(row)
 return '记下了，实际用了'+club+'。'


def companion_reply(text):
 clean=re.sub(r'[，,。！!？?\s]','',text)
 if clean in ('谢谢','谢谢你','谢了','多谢','谢谢小鸟'):return '不客气，需要时叫我。'
 if clean in ('今天很开心','今天真开心','打得很开心'):return '开心就好，今天按你的节奏来。'
 if clean in ('今天风景真好','这球场风景真好'):return '那就好好享受这一段，球的事需要时再叫我。'
 return None
