"""Authenticated companion journey reducer. One question per turn; no unrestricted NLP.
Shares Engine's owner-scoped event transaction, idempotency and deterministic replay.
"""
import copy,re
from round_state import require, initial, reduce, fact_value
VERSION='0.1.0'
QUESTIONS={
 'memory':('我会逐渐了解你，可能五场，也可能更多；今天先依据可靠信息服务。你愿意让我跨场记住你确认的偏好和球技资料吗？',['可以记住','仅本场']),
 'name':('你希望我怎么称呼你？',['叫我球友','跳过']),
 'units':('距离你习惯用码还是米？',['码','米','跳过']),
 'proactive':('到下一洞、上一洞还没记分时，我轻问一句，可以吗？',['可以提醒','你叫我再说','跳过']),
 'shot_recording':('你询距时，我补问未知的上一杆用杆来记录，可以吗？',['可以记录','不记录击球','跳过']),
 'driver':('一号木平时大概打多远？',['不知道','跳过']),
 'driver_kind':('刚才的一号木距离是落地距离，还是包含滚动的总距离？',['落地','总距离','不清楚']),
 'seven':('7号铁平时大概打多远？',['不知道','跳过']),
 'seven_kind':('刚才的7铁距离是落地距离，还是包含滚动的总距离？',['落地','总距离','不清楚']),
 'miss':('你最常遇到哪一种偏差？',['偏右','偏左','打短','不固定','跳过']),
 'course':('今天使用哪个球场？',['演示球场（合成）']),
 'tee':('今天选哪套发球台？',['蓝台','白台','红台','跳过']),
 'start_hole':('今天从第几洞开始？',['1','2']),
 'goal':('今天想怎样打？',['轻松打球','争取成绩','练一个重点']),
 'condition':('今天身体和精神状态怎么样？',['状态不错','有些疲劳','只想放松','跳过']),
 'ready':('准备好了，开始这场球吗？',['开始球局','稍后再说']),
 'finish_confirm':('确认结束本场并进入回顾吗？未记的成绩会保留未知。',['确认结束','继续打球']),
 'feeling':('打完了，今天你感觉怎么样？',['挺开心','有些可惜','先不聊']),
 'postgame':('这场先收好了，你想接着聊什么？',['聊聊高光','我想改善','今天到这里','下一场']),
 'coach_consent':('你愿意开启跨场教练跟踪，每阶段只盯一个重点吗？',['愿意跟踪','只聊这一次','不想提升']),
 'focus':('这次你最想先改善哪一个点？',['减少三推','开球稳定','短杆距离感','先不练']),
 'plan_confirm':('这次只练这一项；下场继续观察，证据不足不会判定已经改善。按这个计划跟踪吗？',['接受计划','换个重点','先不练']),
 'practice':('上次约定的那个重点，这期间练过吗？',['练过','没练','暂停教练']),
}
ORDER=['name','units','proactive','shot_recording','driver','driver_kind','seven','seven_kind','miss','course','tee','start_hole','goal','condition','ready']
def summary(s):
    rows=[]
    for i in range(1,19):
        total=fact_value(s,f'holes.{i}.total')
        if total is not None:rows.append({'hole':i,'total':total,'putts':fact_value(s,f'holes.{i}.putts'),'penalties':fact_value(s,f'holes.{i}.penalties')})
    known=[r['putts'] for r in rows if r['putts'] is not None]
    return {'confirmed_holes':len(rows),'confirmed_subtotal':sum(r['total'] for r in rows) if rows else None,
            'putt_opportunities':len(known),'three_putts':sum(n>=3 for n in known),'scores':rows}
def compare(plan,current):
    base=plan['baseline']
    if plan['focus']!='减少三推' or min(base['putt_opportunities'],current['putt_opportunities'])<6:
        return {'decision':'evidence_insufficient','text':'可比较的证据还不够，先保留原重点，不宣称改善。'}
    b=base['three_putts']/base['putt_opportunities'];n=current['three_putts']/current['putt_opportunities']
    return {'decision':'consolidate' if n<b else 'adjust_practice','text':'本场三推比例较低，先巩固；尚不能认定稳定改善。' if n<b else '暂未看到三推比例下降，保留重点，调整练习后继续观察。'}
def view(s):
    j=s.get('journey',{})
    stage=j.get('stage','memory');q,choices=QUESTIONS.get(stage,('',[]))
    if stage=='active' and j.get('consultation'):
        choices={'intent':['稳一点','想上果岭','自己打'],'ball':['就在球旁','还在走过去','自己打'],'lie':['球道','长草','沙坑','不清楚','自己打'],'plan':['7铁打向果岭中央','用熟悉的短杆过渡','自己打'],'commit':['按这个打','再想想','自己打']}.get(j['consultation']['phase'],[])
    return {'stage':stage,'profile':j.get('profile',{}),'memory_allowed':j.get('memory_allowed'),
      'round':j.get('round'),'history':j.get('history',[]),'coach':j.get('coach',{'enabled':False}),
      'choices':choices if not j.get('quiet') else ['继续'],'question':q,'version':s['version'],
      'score_summary':summary(s),'quiet':j.get('quiet',False)}
def _apply_journey(s,p,seq,now):
    require(p.get('type') in ('message','resume','next_round','course','gps'), 'unsupported journey event')
    require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])), 'invalid event id')
    j=s.setdefault('journey',{'stage':'memory','profile':{},'memory_allowed':None,'quiet':False,'coach':{'enabled':False,'plan':None},'history':[],'round':None,'number':0})
    base=s['version']
    def result(text='',**kw):return dict(text='' if j['quiet'] else text,speak_allowed=not j['quiet'] and bool(text),**kw)
    def ask(stage,prefix=''):
        j['stage']=stage
        return result(prefix+QUESTIONS[stage][0])
    def delegate(event):
        # Same aggregate and DB transaction; no second score store or HTTP write.
        out=reduce(s,'session_event',event,seq,now);s['version']=base
        return out
    def remember(key,value):
        j['profile'][key]={'value':value,'source':'user_report','event_id':p['event_id']}
    def next_stage():
        return ask(ORDER[ORDER.index(j['stage'])+1])
    if p['type']=='resume':return ask(j['stage']) if j['stage'] in QUESTIONS else result('我在，想聊或需要帮助时叫我。')
    if p['type']=='next_round':
        require(j['stage'] in ('postgame','idle'), 'finish current round first')
        preserved=j
        fresh=initial();fresh['version']=base;s.clear();s.update(fresh);s['journey']=preserved
        j['round']=None;j['quiet']=False
        if j['memory_allowed'] is not True:
            j['profile']={};j['coach']={'enabled':False,'plan':None}
            return ask('units','新一场开始了，上场未授权跨场保存的资料不会沿用。')
        if j['coach']['enabled'] and j['coach'].get('plan'):return ask('practice','继续上次那个重点。')
        return ask('course','欢迎回来，沿用你已确认的相处偏好。')
    if p['type'] in ('course','gps'):
        require(j['stage']=='active','start round before spatial events')
        return delegate(p)
    text=p.get('text');require(isinstance(text,str) and 0<len(text.strip())<=2000,'text required');text=text.strip()
    stage=j['stage']
    if text in ('安静','先安静'):
        j['quiet']=True
        if stage=='active':delegate(dict(p,type='voice'))
        return result('',pause=True)
    if text in ('继续','恢复语音'):
        j['quiet']=False
        if stage=='active':delegate(dict(p,type='voice'))
        return ask(stage) if stage in QUESTIONS else result('我在，需要时叫我。')
    if j['quiet']:return result('',deferred=True)
    if text in ('先打球，稍后了解','直接开始','先打球') and stage in ('memory',)+tuple(ORDER[:9]):
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
    if text in ('以后用米','以后用码'):
        remember('units',text[-1]);return result('好，按你刚才确认的单位来。')
    if text.startswith('记住：'):
        require(j['memory_allowed'] is True,'cross-round memory not authorized')
        require(len(text[3:])<=500,'memory too long')
        remember('personal_note',text[3:]);return result('记住了，你随时可以说“忘记个人备注”。')
    if text=='忘记个人备注':j['profile'].pop('personal_note',None);return result('个人备注已从当前档案移除；操作审计记录不作为伙伴记忆使用。')
    if stage=='memory':
        if text not in ('可以记住','仅本场','跳过'):return ask(stage)
        j['memory_allowed']=text=='可以记住';return ask('name')
    if stage=='name':
        if text!='跳过':remember('name',text[:40])
        return next_stage()
    if stage=='units':
        if text not in ('码','米','跳过'):return ask(stage)
        remember('units','码' if text=='跳过' else text);return next_stage()
    if stage in ('proactive','shot_recording'):
        allowed=('可以提醒','你叫我再说','跳过') if stage=='proactive' else ('可以记录','不记录击球','跳过')
        if text not in allowed:return ask(stage)
        remember(stage,text==('可以提醒' if stage=='proactive' else '可以记录'));return next_stage()
    if stage in ('driver','seven'):
        match=re.fullmatch(r'(\d{2,3})(码|米)?',text)
        if not match:
            if text in ('不知道','跳过'):return ask('seven' if stage=='driver' else 'miss')
            return ask(stage,'可以回答一个大概数字，也可以跳过。')
        distance=int(match[1]);require(10<=distance<=400,'distance outside prototype range')
        remember(stage,{'distance':distance,'units':match[2] or j['profile'].get('units',{}).get('value','码'),'distance_type':'unknown'})
        return next_stage()
    if stage in ('driver_kind','seven_kind'):
        if text not in ('落地','总距离','不清楚','跳过'):return ask(stage)
        club='driver' if stage=='driver_kind' else 'seven'
        j['profile'][club]['value']['distance_type']={'落地':'carry','总距离':'total'}.get(text,'unknown');return next_stage()
    if stage=='miss':
        if text!='跳过':remember('usual_miss',text[:100])
        return ask('course')
    if stage=='course':
        if text!='演示球场（合成）':return ask(stage,'当前可运行体验仅接好合成球场，不能把它当凤凰山实测地图。')
        j['number']+=1;j['round']={'id':'round-'+str(j['number']),'course':'synthetic-journey','synthetic':True,'finished':False}
        return ask('tee')
    if stage=='tee':j['round']['tee']=None if text=='跳过' else text[:30];return next_stage()
    if stage=='start_hole':
        if text not in ('1','2'):return ask(stage)
        j['round']['start_hole']=int(text);return next_stage()
    if stage=='goal':j['round']['goal']=text[:100];return next_stage()
    if stage=='condition':j['round']['condition']=None if text=='跳过' else text[:100];return next_stage()
    if stage=='ready':
        if text!='开始球局':return result('好，准备好了再说“开始球局”。')
        delegate(dict(type='course',event_id=p['event_id']+'-map',observed_at=p['observed_at'],data=demo_course()))
        # Explicit player-selected starting hole, not an invented GPS observation.
        hole=j['round']['start_hole']
        s['facts']['context.active_hole']={'value':hole,'status':'confirmed','valid':True,'version':seq,'evidence_ids':[]}
        delegate(dict(type='voice',event_id=p['event_id']+'-pref',observed_at=p['observed_at'],text='换洞时提醒记分' if j['profile'].get('proactive',{}).get('value') else '不要主动提醒'))
        j['stage']='active';return result('这场开始了。你不叫我也可以自己打；演示定位尚未提交，询距前请先发送位置。')
    if stage=='active':
        if text=='结束球局':
            j.pop('consultation',None)
            return ask('finish_confirm')
        if text=='自己打':
            j.pop('consultation',None);return result('好，按你的节奏来，需要时叫我。')
        if text in ('这杆怎么打','怎么打'):
            if s.get('session',{}).get('draft') or any(q['status']=='pending' for q in s['questions'].values()):
                return result('还有上一条待答记录，先确认或跳过它，再讨论这一杆。')
            j['consultation']={'phase':'intent'}
            return result('这一杆你想怎么处理？',choices=['稳一点','想上果岭','自己打'])
        c=j.get('consultation')
        if c:
            if c['phase']=='intent':
                c['player_intent']=text;c['phase']='ball'
                return result('你现在就在自己的球旁吗？',choices=['就在球旁','还在走过去','自己打'])
            if c['phase']=='ball':
                if text!='就在球旁':return result('到球旁再一起看，这里先不把设备位置当落点。',choices=['就在球旁','自己打'])
                c['ball_position_report']='user_confirmed';c['phase']='lie'
                return result('现在是什么球位？',choices=['球道','长草','沙坑','不清楚','自己打'])
            if c['phase']=='lie':
                c['lie_report']=text
                if text not in ('球道','长草','沙坑','不清楚'):return result('先确认球位，信息不够时不硬给杆号。',choices=['球道','长草','沙坑','不清楚','自己打'])
                pos=s['facts'].get('context.device_position',{})
                if not pos.get('valid'):
                    return result('还没有可用定位。先提交当前位置，再确认球位；不编造距离或杆号。',choices=['球道','长草','沙坑','不清楚','自己打'])
                from shot_evidence import haversine
                from datetime import datetime
                age=now-datetime.fromisoformat(pos['value']['observed_at'].replace('Z','+00:00')).timestamp()
                if not -5<=age<=60:return result('当前位置已过期，更新定位后再讨论。',choices=['球道','长草','沙坑','不清楚','自己打'])
                c['position_version']=pos['version'];c['phase']='plan'
                return result('结合你想稳一点还是进攻的意图，先用自己熟悉的打法。演示地图不足以判断障碍与旗位，不硬选杆。你准备采用什么球杆和目标？',choices=['7铁打向果岭中央','用熟悉的短杆过渡','自己打'])
            if c['phase']=='plan':
                if s['facts'].get('context.device_position',{}).get('version')!=c.get('position_version'):
                    c['phase']='ball';return result('位置已变化，我们先重新确认：你现在就在球旁吗？',choices=['就在球旁','自己打'])
                c['player_plan']=text;c['phase']='commit'
                return result('你选的是“'+text[:100]+'”。就按这个方案执行吗？',choices=['按这个打','再想想','自己打'])
            if c['phase']=='commit':
                if text!='按这个打':c['phase']='intent';return result('好，你现在更想怎么处理？',choices=['稳一点','想上果岭','自己打'])
                if s['facts'].get('context.device_position',{}).get('version')!=c.get('position_version'):
                    c['phase']='ball';return result('位置已变化，先确认你是否仍在球旁？',choices=['就在球旁','自己打'])
                c['decision']=c['player_plan'];j['last_consultation']=copy.deepcopy(c);j.pop('consultation',None)
                return result('按你确认的“'+c['decision'][:100]+'”来，专注一个目标，按熟悉节奏挥杆。实际用了什么杆，等你报告再记录。')
        query=text+(j['profile'].get('units',{}).get('value','码')) if text=='还有多少' else text
        r=delegate(dict(p,type='voice',text=query))
        if r.get('unsupported'):
            return result('我听到了。这版先保留你的表达，不把普通聊天写成击球事实。你可以继续聊，或询距、报成绩。',unsupported=True)
        return r
    if stage=='finish_confirm':
        if text=='继续打球':j['stage']='active';return result('继续打，需要时叫我。')
        if text!='确认结束':return ask(stage)
        require(not s.get('session',{}).get('draft'),'尚有未确认成绩，请继续打球后确认或跳过该记录')
        current=summary(s);j['round']['finished']=True;j['history'].append({'round':copy.deepcopy(j['round']),**current})
        plan=j['coach'].get('plan')
        note=''
        if j['coach']['enabled'] and plan and j['coach'].get('paused_round')!=j['round']['id']:
            evaluation=compare(plan,current);plan.setdefault('checks',[]).append({'round_id':j['round']['id'],**evaluation});note=evaluation['text']
        return ask('feeling',f"已收好{current['confirmed_holes']}洞确认成绩；未记的洞保持未知。"+note)
    if stage=='feeling':
        j['round']['feeling']=text[:200]
        if text=='先不聊':j['stage']='idle';return result('好，今天到这里。下次准备好再叫我。')
        return ask('postgame','开心的球也值得记住。' if text=='挺开心' else '听到了，咱们按你的节奏来。')
    if stage=='postgame':
        if text=='下一场':return _apply_journey(s,dict(p,type='next_round'),seq,now)
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
        if text=='下一场':return _apply_journey(s,dict(p,type='next_round'),seq,now)
        return result('我在，想聊天就聊；准备打球时说“下一场”。',choices=['下一场'])
    return result('这一步没有改变任何记录。')
def demo_course():
    return {'course_id':'synthetic-journey','map_version':'1','crs':'WGS84','synthetic':True,'holes':[
      {'number':1,'par':4,'bbox':[120.999,30.999,121.0034,31.002],'green_bbox':[121.0028,30.9998,121.0032,31.0002],
       'objects':[{'id':'g1','kind':'green_center','latitude':31,'longitude':121.003}]},
      {'number':2,'par':4,'bbox':[121.0034,30.999,121.008,31.002],'tee_bbox':[121.0034,30.9998,121.0038,31.0002],
       'objects':[{'id':'g2','kind':'green_center','latitude':31,'longitude':121.007}]}]}


def reduce_journey(s,p,seq,now):
    import hashlib
    from datetime import datetime
    from round_state import canonical
    require(isinstance(p.get('observed_at'),str),'observation time required')
    try:
        observed=datetime.fromisoformat(p['observed_at'].replace('Z','+00:00'))
        require(observed.tzinfo is not None,'timezone required')
    except (ValueError,TypeError):raise ValueError('invalid observation time')
    digest=hashlib.sha256(canonical(p).encode()).hexdigest()
    prior=s.get('journey',{}).get('receipts',{}).get(p.get('event_id'))
    if prior:
        require(prior['digest']==digest,'event id reused with different payload')
        return {'text':'','speak_allowed':False,'duplicate':True}
    out=_apply_journey(s,p,seq,now)
    s['journey']['turn_choices']=out.get('choices',[])
    if 'choices' in out:out['choices']=list(out['choices'])
    s['journey'].setdefault('receipts',{})[p['event_id']]={'digest':digest,'result':copy.deepcopy(out)}
    return out
