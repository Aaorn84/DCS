"""Authenticated companion journey reducer. One question per turn; no unrestricted NLP.
Shares Engine's owner-scoped event transaction, idempotency and deterministic replay.
"""
import copy,re
from round_state import require, initial, reduce, fact_value
VERSION='0.9.0'
QUESTIONS={
 'memory':('你好，我是你的球童小鸟。距离、球场策略，或者闲聊，都可以找我。刚认识，我会先按你告诉我的打法来帮你；多打几场，我们就会越来越熟悉、什么时候该提醒、什么时候安静陪着。你愿意让我记住这些，让下次配合更默契吗？',['可以记住','仅本场']),
 'name':('你希望我怎么称呼你？',['叫我球友','跳过']),
 'proactive':('到下一洞、上一洞还没记分时，我轻问一句，可以吗？',['可以提醒','你叫我再说','跳过']),
 'shot_recording':('你询距时，我补问未知的上一杆用杆来记录，可以吗？',['可以记录','不记录击球','跳过']),
 'driver':('一号木平时的Carry（落地距离）大概多少码？',['不知道','跳过']),
 'seven':('7号铁平时的Carry（落地距离）大概多少码？',['不知道','跳过']),
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
ORDER=['name','proactive','shot_recording','driver','seven','miss','course','tee','start_hole','goal','condition','ready']
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
    stage=j.get('stage','memory')
    if stage=='units':stage='proactive'
    if stage in ('driver_kind','seven_kind'):stage=stage.split('_')[0]
    q,choices=QUESTIONS.get(stage,('',[]))
    if stage=='active' and j.get('consultation'):
        choices={'tee_intent':['稳一点','争取进攻','自己打'],'approach_club':['不知道','跳过','自己打'],'tee_refresh':['自己打'],'tee_club':['不知道','没有这支杆','跳过','自己打'],'tee_commit':['按这个打','再想想','自己打'],'intent':['稳一点','想上果岭','自己打'],'ball':['就在球旁','还在走过去','自己打'],'lie':['球道','长草','沙坑','不清楚','自己打'],'plan':['7铁打向果岭中央','用熟悉的短杆过渡','自己打'],'commit':['按这个打','再想想','自己打']}.get(j['consultation']['phase'],[])
    return {'stage':stage,'profile':j.get('profile',{}),'memory_allowed':j.get('memory_allowed'),
      'round':j.get('round'),'history':j.get('history',[]),'coach':j.get('coach',{'enabled':False}),
      'choices':choices if not j.get('quiet') else ['继续'],'question':q,'version':s['version'],
      'score_summary':summary(s),'quiet':j.get('quiet',False),
      'distance_unit':j.get('profile',{}).get('units',{}).get('value','码')}
def _apply_journey(s,p,seq,now):
    require(p.get('type') in ('message','resume','next_round','course','gps'), 'unsupported journey event')
    require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])), 'invalid event id')
    j=s.setdefault('journey',{'stage':'memory','profile':{},'memory_allowed':None,'quiet':False,'coach':{'enabled':False,'plan':None},'history':[],'round':None,'number':0})
    if j['stage']=='units':j['stage']='proactive'
    if j['stage'] in ('driver_kind','seven_kind'):j['stage']=j['stage'].split('_')[0]
    base=s['version']
    def result(text='',**kw):return dict(text='' if j['quiet'] else text,speak_allowed=not j['quiet'] and bool(text),**kw)
    def ask(stage,prefix=''):
        j['stage']=stage
        return result(prefix+QUESTIONS[stage][0].replace('多少码','多少'+j['profile'].get('units',{}).get('value','码')))
    def delegate(event):
        # Same aggregate and DB transaction; no second score store or HTTP write.
        out=reduce(s,'session_event',event,seq,now);s['version']=base
        return out
    def remember(key,value):
        j['profile'][key]={'value':value,'source':'user_report','event_id':p['event_id']}
    def next_stage():
        return ask(ORDER[ORDER.index(j['stage'])+1])
    def open_plan(c,prefix=''):
        from lie_position import fresh_position
        pos=fresh_position(s,now)
        seven=j['profile'].get('seven',{}).get('value',{})
        if pos and seven.get('distance_type')!='carry' and 'seven' not in c.get('unavailable_clubs',[]):
            c['phase']='approach_club'
            return result('7号铁平常的Carry大概多少'+j['profile'].get('units',{}).get('value','码')+'？',choices=['不知道','跳过','自己打'])
        c['position_version']=pos['version'] if pos else None;c['phase']='plan'
        from approach_strategy import advise
        assessment=advise(s,c,now);c['strategy_assessment']=assessment
        return result(prefix+assessment['text']+'你准备采用什么球杆和目标？',choices=['7铁打向果岭中央','用熟悉的短杆过渡','自己打'])
    def tee_offer(c,a):
        from tee_before_fallback import proposal
        c['analysis']=a
        offer=proposal(a,c.get('player_intent'),j['profile'].get('units',{}).get('value','码'),c.get('unavailable_clubs',[]),c.get('selected_club'))
        continuing=bool(c.get('last_offer'))
        body=offer.get('continuation_text',offer['text']) if continuing else offer['text']
        c['last_offer']=copy.deepcopy(offer)
        if offer.get('missing_club'):
            c['phase']='tee_club';c['requested_club']=offer['missing_club']
            return result(offer['question'],choices=['不知道','没有这支杆','跳过','自己打'])
        if offer['options']:
            c['suggestion']=offer['options'][0];c['phase']='tee_commit'
            return result(body+'就按这个方案打吗？',choices=['按这个打','再想想','自己打'])
        c.pop('suggestion',None);j['last_consultation']=copy.deepcopy(c);j.pop('consultation',None)
        return result(offer['text'])
    def tee_brief(a,manual=False):
        if j.get('quiet') or j.get('tee_briefing_disabled') or fact_value(s,'context.preparing') is True:return ''
        key=str(a['hole'])+':'+str(a['course_evidence'])
        if not manual and key in j.get('tee_announced',[]):return ''
        j.setdefault('tee_announced',[]).append(key)
        from tee_before_fallback import facts_text
        speech=facts_text(a,j['profile'].get('units',{}).get('value','码'))
        old=j.get('consultation')
        if old and not old.get('phase','').startswith('tee_'):
            j['last_consultation']=copy.deepcopy(old);j['last_consultation']['status']='superseded_by_tee_scene'
            j.pop('consultation',None)
        pending=s.get('session',{}).get('draft') or any(q['status']=='pending' for q in s['questions'].values())
        if a['par'] in (4,5) and not pending and not j.get('consultation'):
            j['consultation']={'phase':'tee_intent','analysis':a}
            # Arrival reports facts; strategy questions are handled when requested.
        return speech
    if p['type']=='resume':return ask(j['stage']) if j['stage'] in QUESTIONS else result('我在，想聊或需要帮助时叫我。')
    if p['type']=='next_round':
        require(j['stage'] in ('postgame','idle'), 'finish current round first')
        preserved=j
        fresh=initial();fresh['version']=base;s.clear();s.update(fresh);s['journey']=preserved
        j['round']=None;j['quiet']=False
        for key in ('tee_tracking','tee_announced','consultation'):j.pop(key,None)
        if j['memory_allowed'] is not True:
            j['profile']={};j['coach']={'enabled':False,'plan':None}
            return ask('proactive','新一场开始了，默认使用码；上场未授权跨场保存的个人资料不会沿用。')
        if j['coach']['enabled'] and j['coach'].get('plan'):return ask('practice','继续上次那个重点。')
        return ask('course','欢迎回来，沿用你已确认的相处偏好。')
    if p['type'] in ('course','gps'):
        require(j['stage']=='active','start round before spatial events')
        out=delegate(p)
        if p['type']=='gps':
            from tee_before_fallback import analyze,arrival
            from datetime import datetime
            a=analyze(s,now)
            from navigation_requests import outside_tee
            old=j.get('consultation')
            if old and old.get('phase','').startswith('tee_') and not out.get('ignored') and outside_tee(s,old,now):
                j['last_consultation']=copy.deepcopy(old);j['last_consultation']['status']='superseded_by_location'
                j.pop('consultation',None)
            if a and j.get('consultation',{}).get('phase')=='tee_refresh':
                return tee_offer(j['consultation'],a)
            if a and j.get('consultation',{}).get('phase','').startswith('tee_'):
                j['consultation']['analysis']=a
            if not a:j.pop('tee_tracking',None)
            elif arrival(j,a,datetime.fromisoformat(p['observed_at'].replace('Z','+00:00')).timestamp()):
                extra=tee_brief(a)
                if extra:out['text']=extra+out.get('text','');out['speak_allowed']=bool(out['text'])
        return out
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
    if p.get('legacy_unit_answer') and text in ('码','米'):unit=text
    unit_prefix=''
    if p.get('legacy_unit_answer'):
        if unit:remember('units',unit)
        return ask('proactive','距离'+('改用'+unit if unit else '默认使用码')+'。')
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
        return next_stage()
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
        return next_stage()
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
        j['stage']='active';return result('这场开始了。到发球台先简报距离，你可说“不要发球台简报”。你不叫我也可以自己打；演示定位尚未提交，询距前请先发送位置。')
    if stage=='active':
        from hazard_requests import parse as hazard_query,answer as hazard_answer
        hazard=hazard_query(text)
        if not hazard and j.get('pending_hazard') and text in ('右侧','右边','左侧','左边'):
            hazard=dict(j['pending_hazard'],side='right' if text.startswith('右') else 'left')
        if hazard:
            response=hazard_answer(s,hazard,now)
            if response.startswith('你问的是哪个'):j['pending_hazard']=hazard
            else:j.pop('pending_hazard',None)
            return result(response)
        # Short negative replies apply only to the pending all-penalties question.
        penalty_reply=re.sub(r'[，,。！!？?\s]','',text).lower()
        if (s.get('session',{}).get('draft') or {}).get('awaiting')=='penalties' and penalty_reply in ('没有','无','没有罚杆','没罚杆','无罚杆','没有ob也没下水','没有ob也没有下水','没ob也没下水'):
            return delegate(dict(p,type='voice',text='没有罚杆',original_text=text))
        from navigation_requests import distance_unit,selected_iron
        requested_unit=distance_unit(text,j['profile'].get('units',{}).get('value','码'))
        if requested_unit:
            # Fact requests interrupt consultations without becoming a club, intent or confirmation.
            from lie_position import fresh_position
            if not fresh_position(s,now):return result('当前没有新鲜、准确的设备定位，更新位置后就能询距；刚才的球杆资料和讨论仍保留。')
            from round_state import StateError
            try:return delegate(dict(p,type='voice',text='还有多少'+requested_unit))
            except StateError:return result('当前定位与球洞或果岭目标还无法唯一对应，确认位置后我再报距离。')
        from club_selection_previous import selection,same_label
        picked=selection(text)
        consult=j.get('consultation')
        if picked:
            from tee_before_fallback import analyze
            current=analyze(s,now)
            from lie_position import fresh_position
            last=j.get('last_consultation',{})
            stale_tee=not fresh_position(s,now) and last.get('phase','').startswith('tee_') and last.get('status') not in ('superseded_by_location','superseded_by_tee_scene') and bool(last.get('analysis'))
            if stale_tee and not consult:
                consult={'phase':'tee_refresh','analysis':copy.deepcopy(last['analysis'])};j['consultation']=consult
            if (consult and consult.get('phase','').startswith('tee_')) or (current and current['par'] in (4,5)):
                if not consult or not consult.get('phase','').startswith('tee_'):
                    consult={'phase':'tee_intent','analysis':current};j['consultation']=consult
                consult['selection_report']={'club':picked['label'],'source':'user_report','event_id':p['event_id']}
                if consult.get('phase')=='tee_commit' and same_label(picked['label'],consult.get('suggestion',{}).get('club','')):
                    text='按这个打'
                else:
                    consult['selected_club']=picked
                    consult.pop('suggestion',None)
                    if not current:
                        consult['phase']='tee_refresh'
                        return result('记下你想用'+picked['label']+'，定位更新后按这支杆继续看路线。',choices=['自己打'])
                    return tee_offer(consult,current)
        if consult and consult.get('phase') in ('tee_commit','commit') and agreement(text) is True:
            text='按这个打'
        if text in ('不要发球台简报','开启发球台简报'):
            j['tee_briefing_disabled']=text=='不要发球台简报';return result('发球台简报已'+('关闭。' if j['tee_briefing_disabled'] else '开启。'))
        if text in ('到发球台了','开球策略','发球台距离'):
            from tee_before_fallback import analyze
            a=analyze(s,now)
            if a and j.get('consultation',{}).get('phase','').startswith('tee_'):
                if j['consultation']['phase']=='tee_refresh':return tee_offer(j['consultation'],a)
                return result('发球区位置已确认，继续刚才的讨论。')
            return result(tee_brief(a,True)) if a else result('还没有发球区内的新鲜、准确定位和果岭中心资料，暂不报距离。')
        if text=='结束球局':
            j.pop('consultation',None)
            return ask('finish_confirm')
        if text=='自己打':
            j.pop('consultation',None);return result('好，按你的节奏来，需要时叫我。')
        from approach_strategy import requested,advise
        advice_words=re.sub(r'[\s，,。！!？?]','',text)
        advice_query=bool(re.fullmatch(r'(?:小鸟)?(?:你)?(?:有何建议|有什么(?:好)?建议|有啥建议|建议呢|怎么看|觉得怎么打(?:好)?|建议怎么打)(?:吗|呢)?|(?:给|提)(?:我)?(?:个|点|些)?(?:建议|意见)|推荐一下',advice_words))
        if requested(text) or advice_query:
            if s.get('session',{}).get('draft') or any(q['status']=='pending' for q in s['questions'].values()):
                return result('先完成或跳过当前待答记录，再讨论这杆风险，避免把两段回答混在一起。')
            c=j.get('consultation')
            from tee_before_fallback import analyze
            current_tee=analyze(s,now)
            if current_tee and current_tee['par'] in (4,5):
                if not c or not c.get('phase','').startswith('tee_'):
                    if c:j['last_consultation']=copy.deepcopy(c);j['last_consultation']['status']='superseded_by_tee_scene'
                    c={'phase':'tee_intent','analysis':current_tee};j['consultation']=c
                return tee_offer(c,current_tee)
            if c and c['phase'].startswith('tee_'):
                from tee_before_fallback import proposal,analyze
                fresh=analyze(s,now)
                if not fresh:
                    c['phase']='tee_refresh';return result('球杆资料和讨论都保留了；当前定位需要更新，更新后我会接着比较方案。',choices=['自己打'])
                return tee_offer(c,fresh)
            if not c:c={'phase':'ball'};j['consultation']=c
            elif c['phase']=='intent':c['phase']='ball'
            assessment=advise(s,c,now);c['strategy_assessment']=assessment
            # A risk question is neither a player plan nor consent to execute.
            tail={'intent':'这一杆你想稳稳过渡，还是争取上果岭？','ball':'你现在就在自己的球旁吗？','lie':'现场是球道、长草还是沙坑？','plan':'你更想采用什么球杆和目标？','commit':'你想沿用刚才方案，还是重新选一个？'}.get(c['phase'],'这一杆你想怎么处理？')
            return result(assessment['text']+tail)
        c=j.get('consultation')
        if c:
            if c['phase']=='approach_club':
                if text in ('不知道','跳过','不清楚'):c.setdefault('unavailable_clubs',[]).append('seven')
                else:
                    m=re.fullmatch(r'(?:(?:7号铁|7铁|七铁|七号铁)[，,：: ]*)?(?:Carry|carry|落地)?\s*(\d{2,3})(码|米)?',text)
                    if not m:return result('7号铁平常的Carry大概多少'+j['profile'].get('units',{}).get('value','码')+'？',choices=['不知道','跳过','自己打'])
                    distance=int(m[1]);require(10<=distance<=400,'distance outside prototype range')
                    remember('seven',{'distance':distance,'units':m[2] or j['profile'].get('units',{}).get('value','码'),'distance_type':'carry'})
                return open_plan(c)
            if text in ('球道','长草','沙坑','果岭') and c['phase'] in ('plan','commit'):
                c['lie_report']=text;c['lie_evidence']={'label':text,'source':'user_report','event_id':p['event_id']};c.pop('player_plan',None)
                return open_plan(c,'按你现场更正的球位来。')
            if c['phase'] in ('tee_intent','tee_club','tee_commit','tee_refresh'):
                from tee_before_fallback import analyze,proposal
                a=analyze(s,now)
                if a and c['phase']!='tee_intent' and any(word in text for word in ('稳','保守','进攻','积极')):
                    c['player_intent']=text;return tee_offer(c,a)
                if c['phase']=='tee_club':
                    key=c['requested_club']
                    if text in ('不知道','没有这支杆','跳过','没有','不清楚'):
                        c.setdefault('unavailable_clubs',[]).append(key)
                    else:
                        m=re.fullmatch(r'(?:(一号木|1号木|3号木|三号木|[2-6](?:号铁|铁)|长铁杆)[，,：: ]*)?(?:Carry|carry|落地)?\s*(\d{2,3})(码|米)?',text)
                        if not m:return result('只需告诉我这支杆的Carry，也可以说不知道或跳过。',choices=['不知道','没有这支杆','跳过','自己打'])
                        if (key=='driver' and m[1] not in (None,'一号木','1号木')) or (key=='three_wood' and m[1] not in (None,'3号木','三号木')) or (key=='long_iron' and m[1] in ('一号木','1号木','3号木','三号木')):
                            return result('这个杆号与正在了解的球杆不一致，请确认这支杆的Carry。')
                        distance=int(m[2]);require(10<=distance<=400,'distance outside prototype range')
                        remember(key,{'distance':distance,'units':m[3] or j['profile'].get('units',{}).get('value','码'),'distance_type':'carry','club_name':m[1] or (c.get('selected_club') or {}).get('label')})
                    fresh=analyze(s,now)
                    if not fresh:
                        c['phase']='tee_refresh'
                        return result('记下了。球杆资料已保留；当前定位过期或不在可确认的发球区，更新定位后我会接着比较，不用重报Carry。',choices=['自己打'])
                    return tee_offer(c,fresh)
                if not a:
                    c['phase']='tee_refresh';return result('当前方案需要更新定位后再确认；球杆资料已保留。',choices=['自己打'])
                if c['phase']=='tee_refresh':return tee_offer(c,a)
                if c['phase']=='tee_intent':
                    if any(word in text for word in ('稳','保守','进攻','积极')):c['player_intent']=text
                    return tee_offer(c,a)
                if text!='按这个打':c['phase']='tee_intent';return result('好，这一洞你现在更想怎么处理？')
                checked=proposal(a,c.get('player_intent'),j['profile'].get('units',{}).get('value','码'),c.get('unavailable_clubs',[]),c.get('selected_club'))
                updated=checked['options'][0] if checked['options'] else None
                old=c.get('suggestion',{})
                if not updated or any(updated.get(k)!=old.get(k) for k in ('id','club','target','course_evidence','hole','strategy')):
                    return tee_offer(c,a)
                c['suggestion']=updated
                c['decision']=copy.deepcopy(c['suggestion']);j['last_consultation']=copy.deepcopy(c);j.pop('consultation',None)
                return result('按你确认的'+c['decision']['club']+'、'+c['decision']['target']+'目标来。实际执行等你报告，不自动记作击球。')
            if c['phase']=='intent':
                c['player_intent']=text;c['phase']='ball'
                return result('你现在就在自己的球旁吗？',choices=['就在球旁','还在走过去','自己打'])
            if c['phase']=='ball':
                if text!='就在球旁':return result('到球旁再一起看，这里先不把设备位置当落点。',choices=['就在球旁','自己打'])
                c['ball_position_report']='user_confirmed'
                from lie_position import infer
                inferred=infer(s,now)
                if inferred:
                    c['lie_report']=inferred['label'];c['lie_evidence']=inferred
                    return open_plan(c,'按当前GPS与地图区域，球位判断为'+inferred['label']+'；若现场不同你可以直接更正。')
                c['phase']='lie'
                return result('GPS或地图暂时无法可靠分辨球位，现在是球道、长草还是沙坑？',choices=['球道','长草','沙坑','不清楚','自己打'])
            if c['phase']=='lie':
                if text not in ('球道','长草','沙坑','果岭','不清楚'):return result('这里还无法可靠判断球位，请告诉我现场情况。',choices=['球道','长草','沙坑','不清楚','自己打'])
                c['lie_report']=text;c['lie_evidence']={'label':text,'source':'user_report','event_id':p['event_id']}
                return open_plan(c)
            if c['phase']=='plan':
                if (c.get('position_version') is not None and (__import__('lie_position').fresh_position(s,now) or {}).get('version')!=c['position_version']):
                    c['phase']='ball';return result('位置已变化，我们先重新确认：你现在就在球旁吗？',choices=['就在球旁','自己打'])
                c['player_plan']=text;c['phase']='commit'
                return result('你选的是“'+text[:100]+'”。就按这个方案执行吗？',choices=['按这个打','再想想','自己打'])
            if c['phase']=='commit':
                if text!='按这个打':c['phase']='intent';return result('好，你现在更想怎么处理？',choices=['稳一点','想上果岭','自己打'])
                if (c.get('position_version') is not None and (__import__('lie_position').fresh_position(s,now) or {}).get('version')!=c['position_version']):
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
      {'number':1,'par':4,'bbox':[120.999,30.999,121.0034,31.002],'tee_bbox':[120.99905,30.9998,120.99935,31.0002],'green_bbox':[121.0028,30.9998,121.0032,31.0002],
       'surface_zones':[{'id':'fairway1','surface':'fairway','verified':True,'source':'synthetic-authored','bbox':[121.0005,30.9997,121.0025,31.0003]}],
       'tee_strategy':{'verified':True,'source':'synthetic-authored','landing_zones':[{'id':'driver','start_yards':200,'end_yards':245,'width_yards':38,'preferred_side':'center-left','hazards':[{'side':'right','kind':'bunker','label':'沙坑'}]},{'id':'mid','start_yards':166,'end_yards':199,'width_yards':50,'preferred_side':'center','hazards':[]},{'id':'iron','start_yards':120,'end_yards':165,'width_yards':55,'preferred_side':'center','hazards':[]}]},
       'objects':[{'id':'g1','kind':'green_center','latitude':31,'longitude':121.003}]},
      {'number':2,'par':4,'bbox':[121.0034,30.999,121.008,31.002],'tee_bbox':[121.0034,30.9998,121.0038,31.0002],
       'objects':[{'id':'g2','kind':'green_center','latitude':31,'longitude':121.007}]}]}


def reduce_journey(s,p,seq,now):
    if p.get('protocol_version',1)==1:
        from journey_legacy import reduce_journey as legacy
        return legacy(s,p,seq,now)
    if p.get('protocol_version')==2:
        from journey_previous import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==3:
        from journey_carry import reduce_journey as carry
        return carry(s,p,seq,now)
    if p.get('protocol_version')==4:
        from journey_lie import reduce_journey as lie
        return lie(s,p,seq,now)
    if p.get('protocol_version')==5:
        from journey_risk import reduce_journey as risk
        return risk(s,p,seq,now)
    if p.get('protocol_version')==6:
        from journey_direct import reduce_journey as direct
        return direct(s,p,seq,now)
    if p.get('protocol_version')==7:
        from journey_bird import reduce_journey as bird
        return bird(s,p,seq,now)
    if p.get('protocol_version')==8:
        from journey_comparison import reduce_journey as comparison
        return comparison(s,p,seq,now)
    if p.get('protocol_version')==9:
        from journey_continuity import reduce_journey as continuity
        return continuity(s,p,seq,now)
    if p.get('protocol_version')==10:
        from journey_navigation import reduce_journey as navigation
        return navigation(s,p,seq,now)
    if p.get('protocol_version')==11:
        from journey_distance import reduce_journey as distance
        return distance(s,p,seq,now)
    if p.get('protocol_version')==12:
        from journey_penalties import reduce_journey as penalties
        return penalties(s,p,seq,now)
    if p.get('protocol_version')==13:
        from journey_advice import reduce_journey as advice
        return advice(s,p,seq,now)
    if p.get('protocol_version')==14:
        from journey_questions import reduce_journey as questions
        return questions(s,p,seq,now)
    if p.get('protocol_version')==15:
        from journey_scene import reduce_journey as scene
        return scene(s,p,seq,now)
    if p.get('protocol_version')==16:
        from journey_choice import reduce_journey as choice
        return choice(s,p,seq,now)
    require(p.get('protocol_version')==17,'unsupported journey protocol')
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
    if s.get('journey',{}).get('stage')=='units':p=dict(p,legacy_unit_answer=True)
    out=_apply_journey(s,p,seq,now)
    s['journey']['turn_choices']=out.get('choices',[])
    if 'choices' in out:out['choices']=list(out['choices'])
    s['journey'].setdefault('receipts',{})[p['event_id']]={'digest':digest,'result':copy.deepcopy(out)}
    return out
