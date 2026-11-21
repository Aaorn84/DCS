"""Authenticated companion journey reducer. One question per turn; no unrestricted NLP.
Shares Engine's owner-scoped event transaction, idempotency and deterministic replay.
"""
from tee_geometry import planning_geometry_cache
import copy,json,re
from round_state import require, initial, reduce, fact_value, canonical
VERSION='0.25.0'
QUESTIONS={
 'memory':('你好，我是你的球童小鸟。距离、球场策略，或者闲聊，都可以找我。刚认识，我会先按你告诉我的打法来帮你；多打几场，我们就会越来越熟悉、什么时候该提醒、什么时候安静陪着。你愿意让我记住这些，让下次配合更默契吗？',['可以记住','仅本场']),
 'name':('你希望我怎么称呼你？',['叫我球友','跳过']),
 'proactive':('到下一洞、上一洞还没记分时，我轻问一句，可以吗？',['可以提醒','你叫我再说','跳过']),
 'shot_recording':('你询距时，我补问未知的上一杆用杆来记录，可以吗？',['可以记录','不记录击球','跳过']),
 'driver':('一号木平时的Carry（落地距离）大概多少码？',['不知道','跳过']),
 'seven':('7号铁平时的Carry（落地距离）大概多少码？',['不知道','跳过']),
 'miss':('你最常遇到哪一种偏差？',['偏右','偏左','打短','不固定','跳过']),
 'course':('今天使用哪个球场？',['东莞凤凰山（A+B蓝台演示）','演示球场（合成）']),
 'tee':('今天选哪套发球台？',['蓝台','白台','红台','跳过']),
 'start_hole':('今天从第几洞开始？',['1','2']),
 'goal':('今天想怎样打？',['轻松打球','争取成绩','练一个重点']),
 'condition':('今天身体和精神状态怎么样？',['状态不错','有些疲劳','只想放松','跳过']),
 'ready':('准备好了，开始这场球吗？',['开始球局','稍后再说']),
 'finish_confirm':('确认结束本场并进入回顾吗？未记的成绩会保留未知。',['确认结束','继续打球']),
 'feeling':('打完了，今天你感觉怎么样？',['挺开心','有些可惜','先不聊']),
 'review_offer':('需要对本场做个分析总结吗？',['分析总结本场','先不总结']),
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
def round_records(s):
    from shot_links import live,current_score_record,simulated_tee
    from round_state import canonical
    j=s.get('journey',{});round_id=(j.get('round') or {}).get('id')
    if not round_id:return {'clubs':[],'score_draft':None}
    clubs={}
    from datetime import datetime
    def visible_record(record):
        since=j.get('simulation_attempts',{}).get(canonical(record['scope']))
        if not since:return True
        endpoint=record['endpoints'][-1]
        stamps=[s.get('evidence',{}).get(eid,{}).get('observed_at') for eid in endpoint.get('evidence_ids',[])]
        return any(stamp and datetime.fromisoformat(stamp.replace('Z','+00:00'))>=datetime.fromisoformat(since.replace('Z','+00:00')) for stamp in stamps)
    by_hole={}
    for point in j.get('shot_location_candidates',[]):
        if point['round_id']==round_id:
            by_hole.setdefault((point['course'],point['hole']),[]).append(point['id'])
    order={}
    for (course,hole),points in by_hole.items():
        stroke=0
        candidates={p['id']:p for p in j.get('shot_location_candidates',[])}
        for a,b in zip(points,points[1:]):
            if candidates[b].get('relief_position'):continue
            stroke=max(stroke,candidates[a].get('stroke_base',0))
            stroke+=1
            penalties=0
            incidents={r['incident_id']:r for r in j.get('ball_outcome_history',[])
                       if r['scope']==[round_id,course,hole] and r.get('phase')=='placement'}
            for incident in incidents.values():
                relief=next((i for i,pid in enumerate(points) if candidates[pid].get('relief_position')
                             and pid==incident.get('relief_point_id')),None)
                if relief is not None and points.index(a)>=relief:penalties+=incident.get('penalty') or 0
            order[(course,hole,a,b)]=stroke+penalties
    # Navigation restarts active location candidates. Historical records retain
    # their endpoints, so derive missing ordinals from those archived trails.
    archived={}
    for record in j.get('confirmed_shot_distances',[]):
        if record.get('valid') and record['scope'][0]==round_id and visible_record(record):
            archived.setdefault(tuple(record['scope'][1:]),[]).append(record)
    for (course,hole),records in archived.items():
        stroke=0
        previous_end=None
        for record in records:
            start,end=record['endpoints']
            if previous_end is None or (start['id']!=previous_end and simulated_tee(s,record['scope'],start['point'])):
                stroke=0
            stroke+=1
            key=(course,hole,*record['pair_ids'])
            order.setdefault(key,record.get('stroke_number') or stroke)
            previous_end=end['id']
    for key,report in j.get('previous_club_reports',{}).items():
        recorded_round,course,hole,*pair_ids=json.loads(key)
        if recorded_round==round_id and (course,hole,*pair_ids) in order:
            clubs[canonical([recorded_round,course,hole,*pair_ids])]={'hole':hole,'club':report['club'],'source':'previous_club_report','stroke_number':order.get((course,hole,*pair_ids))}
    for record in j.get('confirmed_shot_distances',[]):
        if not visible_record(record) or not current_score_record(s,record):
            continue
        if record['scope'][0]!=round_id or not record.get('valid') or not all(live(s,p) for p in record['endpoints']):
            continue
        if record.get('simulated_landing') and simulated_tee(s,record['scope'],record['endpoints'][-1]['point']):
            continue
        match=j.get('previous_club_reports',{}).get(canonical([*record['scope'],*record['pair_ids']]), {})
        club=match.get('club') or record.get('club')
        if club or record.get('inferred_from_score') or record.get('simulated_landing'):
            key=canonical([*record['scope'],*record['pair_ids']])
            clubs[key]={'hole':record['scope'][2],'club':club,'source':'confirmed_distance',
                        'total_horizontal_m':record['total_horizontal_m'],
                        'stroke_number':order.get((*record['scope'][1:],*record['pair_ids'])),
                        **({'inferred_from_score':True} if record.get('inferred_from_score') else {})}
    for index,row in enumerate(j.get('provisional_strokes',[])):
        if row['scope'][0]!=round_id:continue
        since=j.get('simulation_attempts',{}).get(canonical(row['scope']))
        if since and row.get('observed_at','')<since:continue
        clubs['provisional-'+str(index)]={'hole':row['scope'][2], 'club':row['club'],
            'stroke_number':row['stroke_number'],'total_horizontal_m':row['total_horizontal_m'],
            'source':'provisional_ball'}
    for report in j.get('execution_reports',[]):
        clubs.setdefault(report['event_id'],{'hole':report.get('hole'),'context_hole':report.get('context_hole'),
                         'club':report['club'],'source':'execution_report'})
    from ball_rules import rows as rule_rows
    for flow in j.get('ball_rules',{}).values():
        if flow['scope'][0]!=round_id:continue
        hole=flow['scope'][2]
        if flow.get('revision',0)>=111:
            from confirmed_shot_sync import sync_flow
            flow=copy.deepcopy(flow)
            sync_flow(s,flow)
        clubs={key:row for key,row in clubs.items() if row.get('hole')!=hole}
        for index,row in enumerate(rule_rows(flow)):
            clubs[f"rules-{hole}-{index}"]=row
    # Older provisional flows may have stored the live ball while dropping
    # the original club-only row when restarting location candidates.
    for row in list(clubs.values()):
        if row.get('source')!='provisional_ball' or (row.get('stroke_number') or 0)<3:continue
        original=row['stroke_number']-2
        if not any(r.get('hole')==row['hole'] and r.get('stroke_number')==original for r in clubs.values()):
            clubs[f"ob-original-{row['hole']}-{original}"]={
                'hole':row['hole'],'stroke_number':original,'club':row['club'],
                'total_horizontal_m':None,'source':'original_ball_ob'}
    draft=s.get('session',{}).get('draft')
    for hole in range(1,19):
        pending=draft if draft and draft['hole']==hole else None
        total=pending.get('total') if pending else fact_value(s,f'holes.{hole}.total')
        putts=pending.get('putts') if pending else fact_value(s,f'holes.{hole}.putts')
        if type(total) is not int or type(putts) is not int or not 0<=putts<=total:continue
        for stroke in range(total-putts+1,total+1):
            if any(r.get('hole')==hole and r.get('stroke_number')==stroke for r in clubs.values()):continue
            clubs[f"putt-{hole}-{stroke}"]={
                'hole':hole,'stroke_number':stroke,'club':'推杆',
                'total_horizontal_m':None,'source':'reported_putt_count',
                'score_pending':bool(pending)}
    # Score totals can establish missing stroke counts, but never a club or GPS.
    # Keep these as presentation-only placeholders, excluded from ledger import.
    from ball_rules import ball_counts
    for hole in range(1,19):
        pending=draft if draft and draft['hole']==hole else None
        total=pending.get('total') if pending else fact_value(s,f'holes.{hole}.total')
        putts=pending.get('putts') if pending else fact_value(s,f'holes.{hole}.putts')
        penalty=pending.get('penalties') if pending else fact_value(s,f'holes.{hole}.penalties')
        flows=[flow for flow in j.get('ball_rules',{}).values() if flow['scope'][0]==round_id and flow['scope'][2]==hole]
        penalty_slots=set();number=0
        for flow in flows:
            number=0
            for item in flow['sequence']:
                if not item.get('active',True) or not ball_counts(flow,item['ball_id']):continue
                if item['kind']=='penalty':
                    penalty_slots.update(range(number+1,number+item['amount']+1));number+=item['amount']
                else:number+=1
        if type(penalty) is not int and flows:penalty=len(penalty_slots)
        if not all(type(value) is int for value in (total,putts,penalty)) or not 0<=putts+penalty<=total:continue
        actual=[row for row in clubs.values() if row.get('hole')==hole and row.get('club')!='推杆']
        missing=max(0,total-putts-penalty-len(actual))
        occupied={row.get('stroke_number') for row in clubs.values() if row.get('hole')==hole}
        slots=[n for n in range(1,total-putts+1) if n not in occupied and n not in penalty_slots]
        known_order=penalty==len(penalty_slots)
        for index in range(missing):
            stroke=slots[index] if known_order and index<len(slots) else None
            clubs[f'score-gap-{hole}-{index}']=dict(hole=hole,stroke_number=stroke,club=None,
                total_horizontal_m=None,source='score_placeholder',inferred_from_score=True,score_pending=bool(pending))
    return {'clubs':sorted(clubs.values(),key=lambda row:(row.get('hole') or 99,row.get('stroke_number') or 99)),
            'hole_pars':{h['number']:h['par'] for h in s.get('evidence',{}).get(fact_value(s,'context.course_snapshot'),{}).get('data',{}).get('holes',[])},
            'score_draft':{key:draft.get(key) for key in ('hole','total','putts','penalties','awaiting')} if draft else None}

def view(s):
    j=s.get('journey',{})
    from iron_estimates import iron_table,pitching_wedge
    irons=iron_table(j.get('profile',{}))
    carry_estimates=[dict(club=str(n)+'号铁',**v) for n,v in irons.items() if n>=3 and v['source']!='user_report']
    pw=pitching_wedge(j.get('profile',{}),irons)
    if pw and pw['source']!='user_report':carry_estimates.append(dict(club='P杆',**pw))
    stage=j.get('stage','memory')
    if stage=='units':stage='proactive'
    if stage in ('driver_kind','seven_kind'):stage=stage.split('_')[0]
    q,choices=QUESTIONS.get(stage,('',[]))
    real=j.get('round',{}).get('course')=='dongguan-phoenix-ab-blue-demo' if j.get('round') else False
    if real and stage=='tee':choices=['蓝台']
    if real and stage=='start_hole':choices=[str(n) for n in range(1,19)]
    navigation={}
    if real:
        from phoenix_demo import preview
        navigation={'course_name':'东莞凤凰山 A+B蓝台（来源坐标演示）','simulation':preview(fact_value(s,'context.active_hole') or j['round'].get('start_hole',1),s.get('evidence',{}).get(fact_value(s,'context.course_snapshot'),{}).get('data'))}
    if real:
        position=s['facts'].get('context.device_position',{})
        navigation['simulation']['device_position']=position.get('value') if position.get('valid') else None
        navigation['simulation']['attempt']=j.get('simulation_attempts',{}).get(canonical([(j.get('round') or {}).get('id'),fact_value(s,'context.course_snapshot'),fact_value(s,'context.active_hole')]))
    if stage=='active' and j.get('consultation'):
        choices={'tee_intent':['稳一点','争取进攻','自己打'],'approach_club':['不知道','跳过','自己打'],'tee_refresh':['自己打'],'tee_club':['不知道','没有这支杆','跳过','自己打'],'tee_commit':['按这个打','再想想','自己打'],'intent':['稳一点','想上果岭','自己打'],'ball':['就在球旁','还在走过去','自己打'],'lie':['球道','长草','沙坑','不清楚','自己打'],'plan':['7铁打向果岭中央','用熟悉的短杆过渡','自己打'],'commit':['按这个打','再想想','自己打']}.get(j['consultation']['phase'],[])
        if j['consultation']['phase']=='tee_commit' and len((j['consultation'].get('last_offer') or {}).get('options',[]))>1:
            choices=[option['club'] for option in j['consultation']['last_offer']['options']]+['自己打'] if (j['consultation'].get('last_offer') or {}).get('tee_club_comparison') else ['两上方案','三上方案','自己打']
    if stage=='active' and j.get('response_context',{}).get('question_owner') in ('pin.depth','pin.side'):
        choices=['前部','中部','后部','跳过'] if j['response_context']['question_owner']=='pin.depth' else ['偏左','居中','偏右','跳过']
    if stage=='active' and j.get('short_game_question'):choices=['没有障碍','有沙坑','有长草','不清楚']
    response=j.get('response_context',{})
    if stage=='active' and response:
        owner=response.get('question_owner')
        if owner=='score.putts':choices=['一推','两推','三推','不清楚']
        elif owner=='score.penalties':choices=['没有','1罚杆','2罚杆','不清楚']
        elif owner=='score.confirm':choices=['确认记录','先不记']
        elif owner=='distance.single_stroke':choices=['是的','不是一杆','不清楚']
        elif owner is None:
            from dialogue_routing import pending_owner
            choices=['继续刚才的问题'] if j.get('last_pending_prompt',{}).get('question_owner')==pending_owner(s) and pending_owner(s) else []
    if stage=='active' and j.get('consultation',{}).get('phase')=='tee_options' and response.get('question_owner') in (None,'tee.choice'):choices=['保守方案','进取方案','自己打']
    if stage=='active' and j.get('consultation',{}).get('phase')=='lie_detail':
        choices=j['consultation'].get('lie_detail_choices',[])
    if stage=='active' and not (s.get('session',{}).get('draft') or {}).get('awaiting'):
        from ball_rules import current as rule_current, choices as rule_choices
        if rule_current(s):
            choices=rule_choices(s) or choices
        else:
            from ball_outcome import choices as outcome_choices
            choices=outcome_choices(s) or choices
    from postgame_delivery import present as review_present,CHOICES as review_choices
    round_review=review_present(s)
    if round_review and stage in ('postgame','coach_consent','focus','plan_confirm','feeling','idle'):
        if j.get('postgame_followup')=='hole':
            known=summary(s)['scores']
            choices=[f'第{row["hole"]}洞' for row in sorted(known,key=lambda r:r['total'],reverse=True)[:3]]+['看详细数据']
        else:choices=list(review_choices) if stage=='postgame' else list(dict.fromkeys(review_choices+choices))
    from history_access import page as history_page
    history_metadata=history_page(s)
    return {**navigation,'stage':stage,'profile':j.get('profile',{}),'memory_allowed':j.get('memory_allowed'),
      'shot_audio':j.get('shot_audio',{}),'round':j.get('round'),'history':history_metadata['rounds'],'history_count':history_metadata['total'],'history_has_more':history_metadata['has_more'],'coach':j.get('coach',{'enabled':False}),
      'choices':choices if not j.get('quiet') else ['继续'],'question':q,'version':s['version'],
      'round_review':round_review,'score_summary':summary(s),'round_records':round_records(s),'quiet':j.get('quiet',False),
      'tee_dispersion':j.get('tee_dispersion_summary',{}),
      'current_hole':fact_value(s,'context.active_hole'),'carry_estimates':carry_estimates,
      'distance_unit':j.get('profile',{}).get('units',{}).get('value','码')}
def _apply_journey(s,p,seq,now):
    require(p.get('type') in ('message','resume','next_round','course','gps'), 'unsupported journey event')
    require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])), 'invalid event id')
    j=s.setdefault('journey',{'stage':'memory','profile':{},'memory_allowed':None,'quiet':False,'coach':{'enabled':False,'plan':None},'history':[],'round':None,'number':0})
    if j['stage']=='goal':j['stage']='ready'
    if j['stage']=='units':j['stage']='proactive'
    if j['stage'] in ('driver_kind','seven_kind'):j['stage']=j['stage'].split('_')[0]
    if p['type']=='message' and j['stage'] in ('active','course','tee','start_hole','goal','ready','idle') and (j.get('finder_pending') or re.search(r'保底(?:开球杆|球杆)',p.get('text',''))):
        from fairway_finder import handle as explicit_finder
        reply=explicit_finder(s,p['text'],p['event_id'])
        if reply is not None:return dict(text='' if j.get('quiet') else reply,speak_allowed=not j.get('quiet') and bool(reply))
    base=s['version']
    def result(text='',**kw):return dict(text='' if j['quiet'] else text,speak_allowed=not j['quiet'] and bool(text),**kw)
    def ask(stage,prefix=''):
        if stage=='goal':stage='ready'
        j['stage']=stage
        return result(prefix+QUESTIONS[stage][0].replace('多少码','多少'+j['profile'].get('units',{}).get('value','码')))
    def delegate(event):
        # Same aggregate and DB transaction; no second score store or HTTP write.
        out=reduce(s,'session_event',event,seq,now);s['version']=base
        return out
    def remember(key,value):
        j['profile'][key]={'value':value,'source':'user_report','event_id':p['event_id']}
    def next_stage():
        target=ORDER[ORDER.index(j['stage'])+1]
        if target in ('goal','condition'):target='ready'
        return ask(target)
    def open_plan(c,prefix=''):
        from lie_position import fresh_position
        from approach_dialogue import prepare
        pos=prepare(s,c,now)
        seven=j['profile'].get('seven',{}).get('value',{})
        if pos and seven.get('distance_type')!='carry' and 'seven' not in c.get('unavailable_clubs',[]):
            c['phase']='approach_club'
            return result('7号铁平常的Carry大概多少'+j['profile'].get('units',{}).get('value','码')+'？',choices=['不知道','跳过','自己打'])
        if pos and c.get('ball_position_report') not in ('user_confirmed','simulation_selected'):
            c['phase']='ball';return result('你现在就在自己的球旁吗？',choices=['就在球旁','还在走过去','自己打'])
        if pos and not c.get('lie_report'):
            c['phase']='lie';return result('现场是球道、长草还是沙坑？',choices=['球道','长草','沙坑','不清楚','自己打'])
        c['position_version']=pos['version'] if pos else None;c['position_point']=copy.deepcopy(pos['value']) if pos else None;c['phase']='plan'
        from approach_dialogue import advise
        assessment=advise(s,c,now,practical_rough=p.get('_practical_rough_v83',False),confirm_landing=p.get('_followups_v84',False),use_landing_depth=p.get('_landing_depth_v85',False),verified_lines=p.get('_aim_lines_v86',False),carry_crossing=p.get('_carry_crossing_v96',False),verify_playability=p.get('_carry_playability_v99',False),allow_roll_in=p.get('_par_five_roll_v102',False),compare_safety=p.get('_approach_risk_v104',False),middle_pin=p.get('_middle_pin_v108',False),assess_lie=p.get('_approach_lie_v109',False));c['strategy_assessment']=assessment
        if assessment.get('lie_question'):
            c['phase']='lie_detail'
            c['lie_detail_choices']=assessment['lie_question']['choices']
            return result(prefix+assessment['text'],choices=c['lie_detail_choices'])
        if assessment.get('missing_attack_carry'):
            inventory=j['profile'].get('lofted_wedge_inventory',{}).get('value')
            ranges=j['profile'].get('lofted_wedge_ranges',{}).get('value',{})
            skipped=j['profile'].get('wedge_question_skips',{}).get('value',[])
            uses=j['profile'].get('lofted_wedge_uses',{}).get('value',{})
            loft=next((n for n in (inventory or []) if str(n) not in ranges and str(n) not in uses and f'wedge_{n}' not in skipped),None)
            if loft is not None or (inventory is None and 'wedge_inventory' not in skipped):
                key=f'wedge_{loft}' if loft is not None else 'wedge_inventory'
                c.update(phase='approach_club',requested_approach_club=key)
                question=f'{loft}度杆常用Carry范围是多少？' if loft is not None else '你有哪支挖起杆或短铁能打这个Carry？可报“52度杆110–120码”。'
                return result(assessment['text']+question,choices=['不知道','跳过','自己打'])
        from iron_estimates import iron_table,pitching_wedge,lofted_wedge_option
        pin=assessment.get('pin_distance_estimate')
        pw=pitching_wedge(j['profile'],iron_table(j['profile']))
        distance=assessment.get('distance_m',0)/.9144
        if pin and not assessment.get('mapped_crossing') and c.get('lie_report') in ('球道','发球台') and pw and 50<distance<pw['carry_yards']-5 and (c.get('collecting_wedge_ranges') or not lofted_wedge_option(j['profile'],distance)):
            inventory=j['profile'].get('lofted_wedge_inventory',{}).get('value')
            ranges=j['profile'].get('lofted_wedge_ranges',{}).get('value',{})
            skipped=j['profile'].get('wedge_question_skips',{}).get('value',[])
            uses=j['profile'].get('lofted_wedge_uses',{}).get('value',{}) if p.get('_wedge_bag_v68') else {}
            loft=next((n for n in (inventory or []) if str(n) not in uses and str(n) not in ranges and f'wedge_{n}' not in skipped),None)
            if (inventory is None and 'wedge_inventory' not in skipped) or loft is not None:
                from short_pin_distance import pin_distance_wording
                c.update(phase='approach_club',requested_approach_club='wedge_inventory' if loft is None else f'wedge_{loft}',collecting_wedge_ranges=True)
                unit=j['profile'].get('units',{}).get('value','码')
                question='除了P杆，你球包里还有哪些角度杆？知道Carry范围的话，可以一起报。' if loft is None else f'{loft}度杆平时的Carry大概是几到几{unit}？'
                return result(pin_distance_wording(pin,unit)+'。'+question,choices=['不知道','跳过','自己打'],pin_distance_estimate=pin)
        c.pop('collecting_wedge_ranges',None)
        if j.get('round',{}).get('service_policy',{}).get('fatigued'):assessment['text']+='今天有些疲劳，优先熟悉的正常发力打法；够不到就分段过渡。'
        if assessment.get('mapped_crossing'):
            return result(prefix+assessment['text']+'你准备采用什么球杆和目标？',
                          mapped_crossing=True,choices=['用熟悉的短杆过渡','自己打'])
        return result(prefix+assessment['text']+'你准备采用什么球杆和目标？',choices=['7铁打向果岭中央','用熟悉的短杆过渡','自己打'])
    def tee_proposal(c,a,selected):
        from tee_strategy import suggest
        return suggest(s,a,c.get('player_intent'),j['profile'].get('units',{}).get('value','码'),
                       c.get('unavailable_clubs',[]),selected,mapped_fallback=p.get('_tee_geometry_v94',False),
                       par_five_plan=p.get('_par_five_v95',False),carry_crossing=p.get('_carry_crossing_v96',False),
                       compare_par_five=p.get('_par_five_compare_v97',False),
                       ask_fairway_carry=p.get('_ask_fairway_carry_v98',False) and not c.get('collect_par_five_bag'),
                       allow_roll_in=p.get('_par_five_roll_v102',False),
                       compare_safety=p.get('_approach_risk_v104',False),compare_next_shot=p.get('_stroke_consistency_v111',False))
    def tee_offer(c,a):
        brief=tee_brief(a) if p.get('_tee_brief_order_v100') else ''
        def tee_reply(text,**kwargs):
            if brief:
                return result(brief+'\n'+text,tee_brief_prefix=brief,**kwargs)
            return result(text,**kwargs)
        c['analysis']=a
        if c.get('collect_par_five_bag') and a['par']==5:
            from tee_strategy import PAR_FIVE_BAG
            from club_selection import same_label
            skipped=c.get('bag_skips',[])
            absent=j['profile'].get('absent_fairway_clubs',{}).get('value',[])
            known=a['clubs']
            missing=next(((key,label) for key,label in PAR_FIVE_BAG
                          if key not in known and key not in skipped and key not in absent
                          and not any(same_label(label,club['label']) for club in known.values())),None)
            if missing:
                key,label=missing
                c.update(phase='tee_club',requested_club='par_five_bag',bag_club=key)
                choices=['没有','不知道','跳过','自己打']
                if key in ('iron3','iron4'):
                    return tee_reply(f'你有{label}吗？如果有，常用Carry大概多少？',choices=choices)
                return tee_reply(f'{label}在球道上的Carry大概多少？',choices=choices)
        offer=tee_proposal(c,a,c.get('selected_club'))
        continuing=bool(c.get('last_offer'))
        body=offer.get('continuation_text',offer['text']) if continuing else offer['text']
        if j.get('round',{}).get('service_policy',{}).get('fatigued') and not offer.get('missing_club'):
            body+='今天有些疲劳，按平常节奏打，不额外发力；若这支杆拿不准就重新比较。'
            offer['condition_policy']='familiar_normal_effort_no_carry_recalibration'
        c['last_offer']=copy.deepcopy(offer)
        if offer.get('missing_club'):
            c['phase']='tee_club';c['requested_club']=offer['missing_club']
            if offer['missing_club']=='par_five_fairway':
                return tee_reply(body+' '+offer['question'],choices=['不知道','跳过','自己打'])
            return tee_reply(offer['question'],choices=['不知道','没有这支杆','跳过','自己打'])
        if len(offer['options'])>1:
            c['phase']='tee_commit'
            c.pop('suggestion',None)
            if offer.get('tee_club_comparison'):
                labels=[option['club'] for option in offer['options']]
                return tee_reply(body+'你想用'+'还是'.join(labels)+'？',choices=labels+['自己打'])
            return tee_reply(body+'你想走两上还是三上？',choices=['两上方案','三上方案','自己打'])
        if offer['options']:
            c['suggestion']=offer['options'][0];c['phase']='tee_commit'
            if j.get('round',{}).get('service_policy',{}).get('relaxed'):
                return tee_reply(body,choices=['按这个打','再想想','自己打'])
            return tee_reply(body+'就按这个方案打吗？',choices=['按这个打','再想想','自己打'])
        c.pop('suggestion',None);j['last_consultation']=copy.deepcopy(c);j.pop('consultation',None)
        if p.get('_dialogue_v70') and offer['text'].startswith('目前没有可确认的保守落区'):
            return tee_reply('地图还不能确认这洞的开球落区。你看得到球道中间哪一段宽、能避开障碍？可以说“球道中间约200码可用”，我按你的Carry帮你选杆。')
        return tee_reply(offer['text'])
    def tee_brief(a,manual=False):
        if p.get('_stroke_consistency_v111') and not manual:
            pending_score=bool((s.get('session') or {}).get('draft')) or any(q.get('status')=='pending' and str(q.get('target','')).startswith('holes.') and q.get('field') in ('total','putts','penalties') for q in s.get('questions',{}).values())
            if pending_score:return ''
        if j.get('quiet') or j.get('tee_briefing_disabled') or fact_value(s,'context.preparing') is True:return ''
        key=str(a['hole'])+':'+str(a['course_evidence'])
        if not manual and key in j.get('tee_announced',[]):return ''
        j.setdefault('tee_announced',[]).append(key)
        from tee_strategy import facts_text
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
    if p['type']=='resume':
        eligible=j['stage'] in ('course','tee','start_hole','goal','ready','active','idle')
        busy=bool(j.get('consultation') or j.get('score_draft') or j.get('finder_pending'))
        if j['stage']=='active':
            from ball_rules import blocking
            busy=busy or blocking(s) or j.get('shot_audio',{}).get('phase') not in (None,'idle','disabled')
        if eligible and not busy and not j.get('quiet') and not j.get('finder_onboarding_asked') and not j.get('finder_backfill_asked') and not j.get('profile',{}).get('fairway_finder'):
            j['finder_backfill_asked']=True
            j['finder_pending']=dict(round=(j.get('round') or {}).get('id'),phase='club',optional=True)
            return result('补充了解一下：哪支杆是你最信任的保底开球杆？可以报杆名，后续保守方案会结合使用。也可以跳过，之后不再主动重复询问。',choices=['5号木','铁木杆','4号铁','跳过'])
        return ask(j['stage']) if j['stage'] in QUESTIONS else result('我在，想聊或需要帮助时叫我。')
    if p['type']=='next_round':
        require(j['stage'] in ('postgame','idle'), 'finish current round first')
        if p.get('_stroke_consistency_v111'):
            from hole_history import archive_current
            archive_current(s)
        preserved=j
        fresh=initial();fresh['version']=base;s.clear();s.update(fresh);s['journey']=preserved
        j['round']=None;j['quiet']=False
        for key in ('tee_tracking','tee_announced','consultation','response_context','last_pending_prompt','dialogue_audit','question_prompts','execution_reports','round_review_requested','round_review_expand_event','round_review_cache','postgame_followup'):j.pop(key,None)
        if j['memory_allowed'] is not True:
            j['profile']={};j['coach']={'enabled':False,'plan':None}
            return ask('proactive','新一场开始了，默认使用码；上场未授权跨场保存的个人资料不会沿用。')
        if j['coach']['enabled'] and j['coach'].get('plan'):return ask('practice','继续上次那个重点。')
        return ask('course','欢迎回来，沿用你已确认的相处偏好。')
    if p['type'] in ('course','gps'):
        if p['type']=='gps' and j['stage'] in ('tee','start_hole','goal','ready'):
            if not fact_value(s,'context.course_snapshot'):
                data=p.get('demo_course_snapshot') if j['round']['course']=='dongguan-phoenix-ab-blue-demo' else demo_course()
                delegate(dict(type='course',event_id=p['event_id']+'-map',observed_at=p['observed_at'],data=data))
            out=delegate(p)
            from tee_strategy import analyze,arrival
            from datetime import datetime
            a=None if out.get('ignored') else analyze(s,now)
            if a and arrival(j.setdefault('pre_round_tracking',{}),a,datetime.fromisoformat(p['observed_at'].replace('Z','+00:00')).timestamp()):
                j['round']['start_hole']=a['hole'];j['round']['start_hole_source']='gps_tee_dwell'
                j['round']['start_hole_evidence']=s['facts']['context.device_position']['evidence_ids']
                if j['stage']=='start_hole':return ask('ready',f"已定位到第{a['hole']}洞发球台。")
            return result('',**{k:v for k,v in out.items() if k not in ('text','speak_allowed')})
        require(j['stage']=='active','start round before spatial events')
        correcting=p.get('_correction_v88') and p['type']=='gps' and p.get('data',{}).get('simulation_position_action')=='correct'
        if correcting:
            from shot_links import pair,scope
            course=s.get('evidence',{}).get(scope(s)[1],{}).get('data',{})
            if not pair(s) or not course.get('reference_simulation') or p['data'].get('simulation_source')!='map_click':
                return result('本洞还没有可修正的落点，当前位置已保留。',ignored=True,reason='no_correctable_landing')
        out=delegate(p)
        if p['type']=='gps':
            if not out.get('ignored'):
                from shot_links import bootstrap,observe
                bootstrap(s)
                if p.get('_audit_v87') and p.get('data',{}).get('simulation_position_action')=='correct':
                    from shot_links import correct_simulated_position
                    correct_simulated_position(s,now)
                    if correcting:
                        from shot_links import handle as shot_query
                        question=shot_query(s,dict(p,text='上一杆打了多少'),now)
                        if j.get('pending_shot_link'):
                            from dialogue_routing import record_response
                            reply=result('落点已更正。'+question,choices=['是的','不是'])
                            record_response(s,dict(p,type='message',text='上一杆打了多少'),reply,now)
                            return reply
                        return result('落点已更正。'+(question or ''))
                else:
                    observe(s,now,preserve_played_shots=p.get('_simulation_shot_v93',False))
            from tee_strategy import analyze,arrival
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
                extra='' if p.get('_dialogue_v69') and (s.get('session',{}).get('draft') or {}).get('awaiting')=='confirm' else tee_brief(a)
                if extra:out['text']=extra+out.get('text','');out['speak_allowed']=bool(out['text'])
        return out
    text=p.get('text');require(isinstance(text,str) and 0<len(text.strip())<=2000,'text required');text=text.strip()
    stage=j['stage']
    if stage=='active' and j.get('green_query_context'):
        from green_context import resolve as continuing_green
        if continuing_green(s,text,now) is None:j.pop('green_query_context',None)
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

        if text not in ('东莞凤凰山（A+B蓝台演示）','演示球场（合成）'):return ask(stage)
        real=text=='东莞凤凰山（A+B蓝台演示）'
        j['number']+=1;j['round']={'id':'round-'+str(j['number']),'course':'dongguan-phoenix-ab-blue-demo' if real else 'synthetic-journey','synthetic':not real,'reference_simulation':real,'finished':False}
        return ask('tee')
    if stage=='tee':
        if j['round']['course']=='dongguan-phoenix-ab-blue-demo' and text!='蓝台':return ask('tee','凤凰山演示先使用A+B蓝台组合。')
        j['round']['tee']=None if text=='跳过' else text[:30]
        if j['round'].get('start_hole_source')=='gps_tee_dwell':return ask('ready')
        return ask('start_hole','暂未通过定位确认发球台。')
    if stage=='start_hole':
        allowed=range(1,19) if j['round']['course']=='dongguan-phoenix-ab-blue-demo' else (1,2)
        if not text.isdigit() or int(text) not in allowed:return ask(stage)
        j['round']['start_hole']=int(text);j['round']['start_hole_source']='user_report';return next_stage()
    if stage in ('goal','condition'):
        question_words=re.sub(r'[\s，,。！!？?]','',text)
        asking_strategy=bool(re.search(r'怎么打|如何打|有何建议|有什么(?:好)?建议|有啥建议|给点建议|推荐一下|你怎么看|你觉得呢|你建议呢',question_words))
        if asking_strategy:
            suggestion='赛前我建议先求稳定：用最有把握的球杆开球，不勉强进攻；上场后再结合每洞距离和球位选打法。'
            j['round']['pre_round_suggestion']={'text':suggestion,'source':'caddie_suggestion','request_event_id':p['event_id'],'accepted':False}
            if stage=='goal':j['round']['goal']=None
            return ask('ready',suggestion)
        if '?' in text or '？' in text:return ask(stage)
    if stage=='goal':
        j['round']['goal']=text[:100];j['round']['goal_source']='user_report'
        relaxed=any(t in text for t in ('轻松','放松','休闲'))
        j['round']['service_policy']={'relaxed':relaxed,'training_prompts':False if relaxed else 'opt_in_only','score_pressure':False,'goal_does_not_set_shot_intent':True}
        return ask('ready','好，今天轻松打，需要距离或打法建议就叫我。' if relaxed else '')
    if stage=='condition':
        j['round']['condition']=None if text=='跳过' else text[:100]
        j['round'].setdefault('service_policy',{})['fatigued']=any(t in text for t in ('疲劳','累','不舒服'))
        return ask('ready')
    if stage=='ready':
        if text!='开始球局':return result('好，准备好了再说“开始球局”。')
        from phoenix_demo import course as phoenix_course
        selected_course=p['demo_course_snapshot'] if j['round']['course']=='dongguan-phoenix-ab-blue-demo' else demo_course()
        delegate(dict(type='course',event_id=p['event_id']+'-map',observed_at=p['observed_at'],data=selected_course))
        # Explicit player-selected starting hole, not an invented GPS observation.
        hole=j['round']['start_hole']
        s['facts']['context.active_hole']={'value':hole,'status':'confirmed','valid':True,'version':seq,'evidence_ids':[]}
        delegate(dict(type='voice',event_id=p['event_id']+'-pref',observed_at=p['observed_at'],text='换洞时提醒记分' if j['profile'].get('proactive',{}).get('value') else '不要主动提醒'))
        j['stage']='active';return result('这场开始了。到发球台先简报距离，你可说“不要发球台简报”。你不叫我也可以自己打；演示定位尚未提交，询距前请先发送位置。')
    if stage=='active' and any(t in text for t in ('有些疲劳','今天很累','今天有点累','身体不舒服','状态恢复了','今天只想放松')):
        policy=j['round'].setdefault('service_policy',{})
        if '放松' in text:policy.update(relaxed=True,training_prompts=False,score_pressure=False);return result('好，今天轻松打，需要我再叫我。')
        tired='恢复' not in text;policy['fatigued']=tired;j['round']['condition']=text
        return result('记下了，接下来优先用熟悉、轻松的打法，不靠额外发力补距离。' if tired else '好，已更新今天的状态。')
    if stage=='active':
        if p.get('_approach_lie_v109'):
            c=j.get('consultation') or {}
            if c.get('phase') in ('lie_detail','plan') and c.get('lie_report') in ('长草','沙坑','不清楚'):
                if c.get('phase')=='lie_detail' and c.get('lie_report')=='不清楚' and text in ('球道','长草','沙坑'):
                    c['lie_report']=text
                    c['lie_evidence']={'label':text,'source':'user_report','event_id':p['event_id']}
                    c.pop('lie_playability',None)
                    return open_plan(c)
                from approach_lie import answer
                detail=answer(text,c.get('lie_report'))
                if detail is not None:
                    from lie_position import fresh_position
                    pos=fresh_position(s,now)
                    if not pos:
                        return result('请先更新球位，再确认这颗球的触球条件。')
                    c['lie_evidence']={'label':c['lie_report'],'source':'user_report','event_id':p['event_id']}
                    c['lie_playability']={'lie':c['lie_report'],'status':detail,
                                          'point':copy.deepcopy(pos['value']),'at':now,
                                          'event_id':p['event_id'],'source':'user_report'}
                    return open_plan(c)
                if c.get('phase')=='lie_detail' and __import__('approach_dialogue').requested(text):
                    return open_plan(c)
        if p.get('_followups_v84'):
            from lie_position import fresh_position
            assessment=(j.get('consultation') or {}).get('strategy_assessment',{})
            landing=assessment.get('rough_landing_question')
            if landing:
                pos=fresh_position(s,now)
                live=bool(pos and pos['version']==landing['position_version']
                          and landing['course']==fact_value(s,'context.course_snapshot')
                          and landing['hole']==fact_value(s,'context.active_hole')
                          and 0<=now-landing['at']<=300)
                answer=re.sub(r'[。！!\s]','',text)
                if live and answer in ('有','有落点','有足够落点','没有','落点太窄','太窄'):
                    assessment.pop('rough_landing_question',None)
                    if answer in ('有','有落点','有足够落点'):
                        return result('球浮在草上，可以用熟悉的沙杆或挖起杆抛切，瞄你看到的那块落点，过沙留点余量。球埋得深就先找条能出球的路线。')
                    return result('沙坑后太窄，这杆先找一条看得见、能避开沙坑的路线，切回宽处再攻果岭。')
                assessment.pop('rough_landing_question',None)
        from dialogue_routing import classify,guard_assent,assent,pending_owner,owner_live,resume as resume_question
        route=classify(s,text,now)
        if route['domain']=='resume_question':
            prompt=resume_question(s,now)
            context=j.get('response_context',{})
            if context.get('question_owner')=='score.confirm' and prompt==context.get('spoken_text'):
                return delegate(dict(p,type='voice',refresh_score_confirmation=True))
            return result(prompt)
        if route['type']=='companion_dialogue':
            from dialogue_routing import companion_reply
            companion=companion_reply(text)
            if companion:return result(companion)
        if route['type']=='execution_report':
            from dialogue_routing import save_execution
            execution_reply=save_execution(s,p)
            if execution_reply:return result(execution_reply)
        if route['domain']=='score':return delegate(dict(p,type='voice',text=route['normalized_text'],original_text=text))
        if route['domain']=='score_unclear':
            session=s.get('session',{})
            if session.get('draft') or any(q.get('status')=='pending' for q in s.get('questions',{}).values()):
                return result('刚才的成绩没听清。你可以重报洞号和总杆数。')
            if j.get('quiet') or fact_value(s,'context.quiet',False) or fact_value(s,'context.preparing',False):
                return result()
            hole=route['hole']
            qid=p['event_id']+'-score-total'
            reduce(s,'question',{'id':qid,'target':f'holes.{hole}','field':'total','deps':{}},seq,now)
            s['version']=base
            session['question_id']=qid
            session['score_target']=hole
            return result(f'刚才的成绩没听清，第{hole}洞一共打了几杆？',question_id=qid)
        if route['domain']=='score_control':
            if text in ('确认','确认记录','确认保存') and not s.get('session',{}).get('draft'):return result('目前没有待确认的成绩。')
            if text in ('撤销上一条记分','撤销刚才的记分') and not s.get('session',{}).get('last_patch'):return result('目前没有可撤销的成绩记录。')
            return delegate(dict(p,type='voice'))
        if route['type']=='pending_answer':
            if p.get('_simulation_shot_v93') and assent(text) is True and not pending_owner(s):
                from shot_links import scope as shot_scope, haversine
                from lie_position import fresh_position
                offer=j.get('approach_club_offer',{})
                pos=fresh_position(s,now)
                if (offer and pos and offer['event_id']==j.get('response_context',{}).get('event_id')
                        and offer['scope']==list(shot_scope(s)) and 0<=now-offer['at']<=300
                        and haversine(pos['value'],offer['point'])<=5):
                    from decision_queries import commit
                    j.pop('approach_club_offer',None)
                    j['simulated_club_choice']={**offer,'event_id':p['event_id'],'at':now}
                    return result(commit(s,p,dict(club=offer['club'],target='green',wording='按刚才的落点打')))
            guarded=guard_assent(s,text,now)
            if guarded:return result(guarded)
            owner=j.get('response_context',{}).get('question_owner') or pending_owner(s);yes=assent(text)
            if owner=='hazard.identity':return result('你问的是近处还是远处的障碍？')
            if owner=='score.confirm':
                if yes:return delegate(dict(p,type='voice',text='确认',original_text=text))
                return result('好，先不确认。你可以修改成绩，或者说“先不记”。')
            if owner=='plan.confirm' and yes:text='按这个打'
            elif owner=='ball.position':text='就在球旁' if yes else '还在走过去'
            elif owner=='green.subject' and yes:text='是的'
        draft=s.get('session',{}).get('draft') or {}
        if draft.get('awaiting') in ('putts','penalties') and route['type'] not in ('fact_request','decision_commitment','execution_report'):
            field=draft['awaiting'];clean=re.sub(r'[\s，,。！!？?]','',text)
            from round_session import N
            pattern=N+(r'(?:推)?' if field=='putts' else r'(?:罚|罚杆)?')
            if re.fullmatch(pattern,clean) or re.fullmatch(r'\d+(?:推|罚|罚杆)?',clean) or clean in ('不清楚','不知道','跳过这一项','没有','无','没有罚杆','没罚杆','无罚杆'):
                normalized='没有罚杆' if field=='penalties' and clean in ('没有','无') else text
                return delegate(dict(p,type='voice',text=normalized,original_text=p['text']))
        from short_game_map import handle as short_game_request
        short_reply=short_game_request(s,p,now)
        if short_reply is not None:
            if j.get('last_short_game_advice',{}).get('event_id')==p['event_id'] and '？' not in short_reply:
                from short_pin_distance import estimate,pin_distance_wording
                pin=estimate(s,now)
                if pin:
                    unit=j.get('profile',{}).get('units',{}).get('value','码')
                    return result(pin_distance_wording(pin,unit)+'。'+short_reply,pin_distance_estimate=pin)
            return result(short_reply)
        from shot_links import handle as shot_link_request
        linked=shot_link_request(s,p,now)
        if linked is not None:return result(linked)
        from decision_queries import previous_distance,distance_answer,approach_selection,commit as commit_approach
        if previous_distance(text):return result(distance_answer(s,text))
        if p.get('_stroke_consistency_v111'):
            from shorter_approach import respond
            shorter=respond(s,text)
            if shorter is not None:return result(shorter)
        chosen=approach_selection(text.replace('打果岭中间','打向果岭中央').replace('打向果岭中间','打向果岭中央') if p.get('_dialogue_v69') else text)
        if p.get('_dialogue_v70'):
            from iron_estimates import parse_spoken_wedge_bag
            bag=parse_spoken_wedge_bag(text,j['profile'].get('units',{}).get('value','码')) if re.search(r'[，,]',text) else None
            if bag and (bag[1] or bag[2]):
                lofts,ranges,uses=bag
                for key,value in (('lofted_wedge_inventory',lofts),('lofted_wedge_ranges',ranges),('lofted_wedge_uses',uses)):
                    old=j['profile'].get(key,{}).get('value')
                    remember(key,list(dict.fromkeys((old or [])+value)) if isinstance(value,list) else {**(old or {}),**value})
                pending=j.get('consultation') or {}
                if (p.get('_wedge_continue_v77') and pending.get('phase')=='approach_club'
                        and pending.get('requested_approach_club','').startswith('wedge_')):
                    pending.pop('requested_approach_club',None)
                    summaries=[]
                    for n in lofts:
                        value=ranges.get(str(n))
                        if value:
                            carry=str(value['low']) if value['low']==value['high'] else str(value['low'])+'–'+str(value['high'])
                            summaries.append(f'{n}度杆Carry{carry}{value["units"]}')
                        elif str(n) in uses:
                            summaries.append(f'{n}度杆用于{uses[str(n)]}，未提供Carry')
                    return open_plan(pending,prefix='记下了：'+'；'.join(summaries)+'。')
                return result('记下了球包里的角度杆、Carry和用途。')
            landing=re.fullmatch(r'球道中间约(\d{2,3})(码|米)(?:可用|无障碍)',text)
            if landing:
                from tee_strategy import analyze
                a=analyze(s,now)
                if a and a['par'] in (4,5):
                    unit=landing[2];scale=.9144 if unit=='米' else 1
                    distance=int(landing[1])/scale
                    clubs=[(abs(v['carry_yards']-distance),k,v) for k,v in a['clubs'].items()
                           if 0<=distance-v['carry_yards']<=15]
                    if clubs:
                        _,_,club=min(clubs)
                        return result(f'按你确认的球道落区，可考虑{club["label"]}，瞄这一段球道中央。给落地滚动留空间。')
                    return result('现有球杆的Carry没有贴近你报的落区。再看一处更近的宽阔落点，或报一支你能控制距离的球杆。')
            c=j.get('consultation') or {}
            wedge=re.fullmatch(r'(?:好[，, ]*)?(?:就|用|选)?(4[6-9]|5[0-9]|6[0-4])(?:度(?:杆)?)?(?:吧)?[。！!]?',text)
            if wedge and (c.get('phase')=='plan' or ('度' in text and j.get('last_short_game_advice'))):
                chosen=dict(club=wedge[1]+'度杆',target='green',wording='打这杆')
            if re.fullmatch(r'(?:这杆|这一杆)?怎么推[？?]?',text):
                from lie_position import infer
                lie=infer(s,now)
                if lie and lie['label']=='果岭':
                    return result('先把速度控制到洞口附近。你看到这条线是上坡还是下坡？')
        live_plan=(j.get('consultation') or {}).get('phase')=='plan'
        if p.get('_dialogue_v71'):
            from short_game_map import scope as shot_scope
            saved=j.get('response_context',{})
            live_plan=live_plan or (saved.get('domain')=='pin_location' and saved.get('scope')==list(shot_scope(s))
                                    and 0<=now-saved.get('at',0)<=300 and not saved.get('question_owner'))
        if p.get('_pitching_choice_v81') and not chosen and live_plan and re.fullmatch(
            r'(?:好[，, ]*)?(?:就|用|选)?[Pp]杆(?:吧)?[。！!]?',text
        ):
            chosen=dict(club='P杆',target='green_center',wording='打向果岭中央')
        if p.get('_dialogue_v69') and not chosen and live_plan:
            short=re.fullmatch(r'(?:好(?:的)?[，,\s]*)?(?:那就|就)?(?:用|选)?([2-9二两三四五六七八九](?:号铁|铁))(?:吧)?[。！!]?',text)
            if short:chosen=approach_selection(short[1]+'打向果岭中央')
        if not chosen and live_plan:
            from club_selection import selection as choose_club
            choice=choose_club(text,hybrid=True,expanded=True)
            if choice and choice['key'] in ('hybrid','three_wood','five_wood'):
                chosen=dict(club=choice['label'],target='green',wording='按刚才的攻果岭方案打')
        if chosen:
            if p.get('_stroke_consistency_v111'):
                from shorter_approach import selection_wording
                chosen=selection_wording(s,chosen)
            if (j.get('consultation') or {}).get('approach_preference')=='layup' and not re.search(r'攻果岭|打向果岭|上果岭',text):
                chosen=dict(chosen,target='fairway',wording='按刚才的过渡落点打')
            from tee_strategy import analyze as current_tee
            tee=current_tee(s,now)
            if not tee or (p.get('_dialogue_v69') and tee['par']==3):return result(commit_approach(s,p,chosen))
        from green_context import resolve as green_resolve,answer as green_answer,remember as remember_green
        green_text=green_resolve(s,text,now)
        if green_text is not None:
            if not green_text:
                j['pending_green_followup']={'text':text,'hole':fact_value(s,'context.active_hole'),'course':fact_value(s,'context.course_snapshot'),'at':now}
                return result('你是问果岭这一侧的空间吗？')
            reply=green_answer(s,green_text,now);remember_green(s,now);return result(reply)
        j.pop('green_query_context',None);j.pop('pending_green_followup',None)
        from hazard_requests import parse as hazard_query
        from hazard_route import answer as hazard_answer
        hazard=hazard_query(text)
        if not hazard and j.get('pending_hazard') and text in ('右侧','右边','左侧','左边','近处','远处','近的','远的'):
            hazard=dict(j['pending_hazard'])
            if text.startswith(('近','远')):hazard['rank']='near' if text.startswith('近') else 'far'
            else:hazard['side']='right' if text.startswith('右') else 'left'
        if hazard:
            response=hazard_answer(s,hazard,now)
            if response.startswith(('你问的是哪个','这条线路上有多个')):j['pending_hazard']=hazard
            else:j.pop('pending_hazard',None)
            return result(response)
        # Short negative replies apply only to the pending all-penalties question.
        penalty_reply=re.sub(r'[，,。！!？?\s]','',text).lower()
        if (s.get('session',{}).get('draft') or {}).get('awaiting')=='penalties' and penalty_reply in ('没有','无','没有罚杆','没罚杆','无罚杆','没有ob也没下水','没有ob也没有下水','没ob也没下水'):
            return delegate(dict(p,type='voice',text='没有罚杆',original_text=text))
        from navigation_requests import distance_unit,selected_iron
        requested_unit=distance_unit(text,j['profile'].get('units',{}).get('value','码'))
        if requested_unit:
            from shot_links import observe
            observe(s,now,query=True,preserve_played_shots=p.get('_simulation_shot_v93',False))
            # Fact requests interrupt consultations without becoming a club, intent or confirmation.
            from lie_position import fresh_position
            if not fresh_position(s,now):return result('当前没有新鲜、准确的设备定位，更新位置后就能询距；刚才的球杆资料和讨论仍保留。')
            from round_state import StateError
            try:return delegate(dict(p,type='voice',text='还有多少'+requested_unit))
            except StateError:return result('当前定位与球洞或果岭目标还无法唯一对应，确认位置后我再报距离。')
        from club_selection import selection,same_label
        picked=selection(text,hybrid=p.get('_par_five_v95',False),expanded=p.get('_par_five_bag_v101',False))
        consult=j.get('consultation')
        if consult and consult.get('phase')=='tee_club' and consult.get('requested_club')=='par_five_bag' and text!='自己打':
            from tee_strategy import PAR_FIVE_BAG,analyze
            key=consult['bag_club']
            label=dict(PAR_FIVE_BAG)[key]
            answer=text.strip().rstrip('。！!')
            choices=['没有','不知道','跳过','自己打']
            if answer in ('没有','没有这支杆'):
                absent=j['profile'].get('absent_fairway_clubs',{}).get('value',[])
                remember('absent_fairway_clubs',list(dict.fromkeys([*absent,key])))
            elif answer in ('不知道','不清楚','跳过'):
                consult.setdefault('bag_skips',[]).append(key)
            else:
                report=re.fullmatch(r'(.*?)\s*(?:Carry|落地)?\s*(\d{2,3})\s*(码|米)?',answer,re.I)
                club=selection(report[1],hybrid=True,expanded=True) if report and report[1].strip() else None
                if not report or (report[1].strip() and (not club or club['key']!=key)):
                    return result(f'有的话，告诉我{label}的Carry，也可以说没有或跳过。',choices=choices)
                distance=int(report[2]);require(10<=distance<=400,'distance outside prototype range')
                unit=report[3] or j['profile'].get('units',{}).get('value','码')
                remember(key,{'distance':distance,'units':unit,'distance_type':'carry',
                              'club_name':club['label'] if club else label})
            fresh=analyze(s,now)
            if not fresh:
                consult['phase']='tee_refresh'
                return result('已记下。更新发球台定位后，我们继续。',choices=['自己打'])
            return tee_offer(consult,fresh)
        if (p.get('_ask_fairway_carry_v98') and consult and consult.get('phase')=='tee_club'
                and consult.get('requested_club')=='par_five_fairway'):
            skip=text.rstrip('。！!') in ('不知道','没有这支杆','跳过','没有','不清楚')
            if not skip and text!='自己打':
                report=re.fullmatch(r'(.*?)\s*(?:Carry|落地)?\s*(\d{2,3})\s*(码|米)?[。！!]?',text,re.I)
                club=selection(report[1],hybrid=True) if report and report[1].strip() else consult.get('fairway_club')
                if picked and picked['key'] in ('three_wood','hybrid','long_iron') and not report:
                    consult['fairway_club']=picked
                    return result(picked['label']+'在球道上的Carry大概多少？',choices=['不知道','跳过','自己打'])
                if not report or not club or club['key'] not in ('three_wood','hybrid','long_iron'):
                    return result('请一起报球杆和Carry，例如「3号木235码」，也可以说跳过。',choices=['不知道','跳过','自己打'])
                distance=int(report[2]);require(10<=distance<=400,'distance outside prototype range')
                unit=report[3] or j['profile'].get('units',{}).get('value','码')
                remember(club['key'],{'distance':distance,'units':unit,'distance_type':'carry','club_name':club['label']})
                consult.pop('fairway_club',None)
                from tee_strategy import analyze
                fresh=analyze(s,now)
                if fresh:
                    return tee_offer(consult,fresh)
                consult['phase']='tee_refresh'
                return result('球道杆距已记下。更新发球台定位后，我再比较两上和三上。',choices=['自己打'])
            if skip:
                text=text.rstrip('。！!')
        if picked:
            from tee_strategy import analyze
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
                offered=(consult.get('last_offer') or {}).get('options',[])
                if (consult.get('last_offer') or {}).get('tee_club_comparison'):
                    matches=[option for option in offered if same_label(option['club'],picked['label'])]
                    if len(matches)==1:
                        consult.update(selected_club=picked,suggestion=matches[0])
                        consult['last_offer']={**consult['last_offer'],'options':matches}
                if (p.get('_shared_tee_club_v103') and current and consult.get('phase')=='tee_commit'
                        and len(offered)>1 and all(same_label(picked['label'],option['club']) for option in offered)):
                    from tee_strategy import same_target
                    from shot_evidence import haversine
                    refreshed=tee_proposal(consult,current,picked)
                    options=refreshed['options']
                    if len(options)==len(offered) and all(same_target(old,new) for old,new in zip(offered,options)):
                        first,second=options
                        same_aim=(first['target']==second['target']
                                  and haversine(first['aim_point'],second['aim_point'])<=3)
                        consult['selected_club']=picked
                        consult['last_offer']=refreshed
                        choices=['两上方案','三上方案','自己打']
                        if not same_aim:
                            return result(f"好，两套都用{picked['label']}，瞄准点各有不同。你想走两上还是三上？",choices=choices)
                        if consult.get('shared_tee_club')!=picked:
                            consult['shared_tee_club']=picked
                            j.setdefault('player_decisions',[]).append({
                                'club':first['club'],'target':first['target'],'hole':first['hole'],
                                'source':'user_report','event_id':p['event_id'],
                                'type':'decision_commitment','execution_confirmed':False,
                            })
                        return result(f"好，开球用{picked['label']}，瞄{first['target']}。两上还是三上，可以等开球落定再决定。",choices=choices)
                if consult.get('phase')=='tee_commit' and same_label(picked['label'],consult.get('suggestion',{}).get('club','')):
                    consult['selected_club']=picked
                    if current:
                        from tee_strategy import same_target
                        refreshed=tee_proposal(consult,current,picked)
                        option=refreshed['options'][0] if refreshed['options'] else None
                        old=consult['suggestion']
                        if not same_target(old,option):return tee_offer(consult,current)
                        consult['suggestion']=option
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
            from tee_strategy import analyze
            a=analyze(s,now)
            if a and j.get('consultation',{}).get('phase','').startswith('tee_'):
                if j['consultation']['phase']=='tee_refresh':return tee_offer(j['consultation'],a)
                return result('发球区位置已确认，继续刚才的讨论。')
            if p.get('_dialogue_v69') and (s.get('session',{}).get('draft') or {}).get('awaiting')=='confirm':return result()
            return result(tee_brief(a,True)) if a else result('还没有发球区内的新鲜、准确定位和果岭中心资料，暂不报距离。')
        if text=='结束球局':
            j.pop('consultation',None)
            return ask('finish_confirm')
        if text=='自己打':
            j.pop('consultation',None);return result('好，按你的节奏来，需要时叫我。')
        from approach_dialogue import requested,advise
        advice_words=re.sub(r'[\s，,。！!？?]','',text)
        advice_query=bool(re.fullmatch(r'(?:小鸟)?(?:你)?(?:有何建议|有什么(?:好)?建议|有啥建议|建议呢|怎么看|觉得怎么打(?:好)?|建议怎么打)(?:吗|呢)?|(?:给|提)(?:我)?(?:个|点|些)?(?:建议|意见)|推荐一下',advice_words))
        if requested(text) or advice_query or (p.get('_stroke_consistency_v111') and (__import__('approach_dialogue').wants_layup(text) or re.search(r'还是直攻|改为直攻|直接攻果岭|还是攻果岭',text))):
            if s.get('session',{}).get('draft') or any(q['status']=='pending' for q in s['questions'].values()):
                return result('先完成或跳过当前待答记录，再讨论这杆风险，避免把两段回答混在一起。')
            c=j.get('consultation')
            from tee_strategy import analyze
            current_tee=analyze(s,now)
            if current_tee and current_tee['par'] in (4,5):
                if not c or not c.get('phase','').startswith('tee_'):
                    if c:j['last_consultation']=copy.deepcopy(c);j['last_consultation']['status']='superseded_by_tee_scene'
                    c={'phase':'tee_intent','analysis':current_tee};j['consultation']=c
                if p.get('_par_five_bag_v101') and current_tee['par']==5:
                    c['collect_par_five_bag']=True
                return tee_offer(c,current_tee)
            if c and c['phase'].startswith('tee_'):
                from tee_strategy import analyze
                fresh=analyze(s,now)
                if not fresh:
                    c['phase']='tee_refresh';return result('球杆资料和讨论都保留了；当前定位需要更新，更新后我会接着比较方案。',choices=['自己打'])
                return tee_offer(c,fresh)
            if not c:c={'phase':'ball'};j['consultation']=c
            elif c['phase']=='intent':c['phase']='ball'
            if p.get('_stroke_consistency_v111'):
                if __import__('approach_dialogue').wants_layup(text):c['approach_preference']='layup'
                elif re.search(r'还是直攻|改为直攻|直接攻果岭|还是攻果岭',text):c.pop('approach_preference',None)
            return open_plan(c)
        if route['type']=='fact_request' and route['domain']=='unresolved_question':
            return result('这个问题我还不能可靠判断，先保留当前讨论；你可以换个说法。')
        c=j.get('consultation')
        if c:
            if c['phase']=='approach_club':
                key=c.get('requested_approach_club','seven')
                skipped=text in ('不知道','跳过','不清楚','没有这支杆')
                unit=j['profile'].get('units',{}).get('value','码')
                if skipped:
                    if key.startswith('wedge_'):
                        prior=j['profile'].get('wedge_question_skips',{}).get('value',[])
                        remember('wedge_question_skips',[*prior,key])
                    else:c.setdefault('unavailable_clubs',[]).append(key)
                elif key.startswith('wedge_'):
                    if p.get('_approach_lie_v109'):
                        named=re.fullmatch(r'(4[6-9]|5[0-9]|6[0-4])度(?:杆)?[，,：: ]*(?:Carry|carry|落地)?\s*(\d{1,3})(码|米)?',text)
                        single=re.fullmatch(r'(?:Carry|carry|落地)?\s*(\d{1,3})(码|米)?',text)
                        if named:
                            text=f'{named[1]}度杆{named[2]}–{named[2]}{named[3] or unit}'
                        elif key!='wedge_inventory' and single:
                            text=f'{single[1]}–{single[1]}{single[2] or unit}'
                    from iron_estimates import parse_wedge_bag,parse_wedge_range,parse_spoken_wedge_bag
                    inventory=j['profile'].get('lofted_wedge_inventory',{}).get('value',[])
                    ranges=j['profile'].get('lofted_wedge_ranges',{}).get('value',{})
                    if key=='wedge_inventory' and text in ('没有','只有P杆','没有角度杆'):
                        remember('lofted_wedge_inventory',[])
                    elif key!='wedge_inventory' and (value:=parse_wedge_range(text.rstrip('。！! '),unit)):
                        remember('lofted_wedge_ranges',{**ranges,key.split('_',1)[1]:value})
                    else:
                        spoken=parse_spoken_wedge_bag(text,unit) if p.get('_wedge_bag_v68') else None
                        bag=spoken[:2] if spoken else parse_wedge_bag(text,unit)
                        if not bag or (key!='wedge_inventory' and not bag[1] and not (spoken and key.split('_',1)[1] in spoken[2])):
                            question='除了P杆，你球包里还有哪些角度杆？' if key=='wedge_inventory' else f'{key.split("_",1)[1]}度杆平时的Carry大概是几到几{unit}？'
                            return result(question)
                        lofts,reported=bag
                        remember('lofted_wedge_inventory',list(dict.fromkeys([*inventory,*lofts])))
                        if reported:remember('lofted_wedge_ranges',{**ranges,**reported})
                        if spoken and spoken[2]:
                            uses=j['profile'].get('lofted_wedge_uses',{}).get('value',{})
                            remember('lofted_wedge_uses',{**uses,**spoken[2]})
                else:
                    m=re.fullmatch(r'(?:(?:7号铁|7铁|七铁|七号铁)[，,：: ]*)?(?:Carry|carry|落地)?\s*(\d{2,3})(码|米)?',text)
                    if not m:return result('7号铁平常的Carry大概多少'+unit+'？',choices=['不知道','跳过','自己打'])
                    distance=int(m[1]);require(10<=distance<=400,'distance outside prototype range')
                    remember('seven',{'distance':distance,'units':m[2] or unit,'distance_type':'carry'})
                c.pop('requested_approach_club',None)
                return open_plan(c)
            if text in ('球道','长草','沙坑','果岭') and c['phase'] in ('plan','commit'):
                c['lie_report']=text;c['lie_evidence']={'label':text,'source':'user_report','event_id':p['event_id']};c.pop('player_plan',None)
                return open_plan(c,'按你现场更正的球位来。')
            if c['phase'] in ('tee_intent','tee_club','tee_commit','tee_refresh'):
                from tee_strategy import analyze,same_target
                a=analyze(s,now)
                if a and c['phase']!='tee_intent' and any(word in text for word in ('稳','保守','进攻','积极')):
                    c['player_intent']=text;return tee_offer(c,a)
                if c['phase']=='tee_club':
                    key=c['requested_club']
                    if text in ('不知道','没有这支杆','跳过','没有','不清楚'):
                        c.setdefault('unavailable_clubs',[]).append(key)
                    else:
                        labels=r'(?:[2-7二两三四五六七]号?)?(?:铁木杆|混合杆)' if key=='hybrid' else r'一号木|1号木|3号木|三号木|[2-7](?:号铁|铁)|七号铁|七铁|长铁杆'
                        if key in ('five_wood','iron3','iron4'):
                            labels={'five_wood':r'[5五]号?木','iron3':r'[3三]号?铁','iron4':r'[4四]号?铁'}[key]
                        m=re.fullmatch(r'(?:('+labels+r')[，,：: ]*)?(?:Carry|carry|落地)?\s*(\d{2,3})(码|米)?',text)
                        if not m:return result('只需告诉我这支杆的Carry，也可以说不知道或跳过。',choices=['不知道','没有这支杆','跳过','自己打'])
                        if (key=='driver' and m[1] not in (None,'一号木','1号木')) or (key=='three_wood' and m[1] not in (None,'3号木','三号木')) or (key=='seven' and m[1] not in (None,'7号铁','7铁','七号铁','七铁')) or (key=='long_iron' and m[1] in ('一号木','1号木','3号木','三号木','7号铁','7铁','七号铁','七铁')):
                            return result('这个杆号与正在了解的球杆不一致，请确认这支杆的Carry。')
                        selected_label=(c.get('selected_club') or {}).get('label')
                        reported=selection(m[1],hybrid=True) if key=='hybrid' and m[1] else None
                        if reported and not same_label(reported['label'],selected_label):
                            return result('这个杆号与正在了解的铁木杆不一致，请确认这支杆的Carry。')
                        distance=int(m[2]);require(10<=distance<=400,'distance outside prototype range')
                        remember(key,{'distance':distance,'units':m[3] or j['profile'].get('units',{}).get('value','码'),'distance_type':'carry','club_name':selected_label if key=='hybrid' else m[1] or selected_label})
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
                offered=(c.get('last_offer') or {}).get('options',[])
                old=c.get('suggestion',{})
                if len(offered)>1 and (c.get('last_offer') or {}).get('tee_club_comparison'):
                    labels=[option['club'] for option in offered]
                    return result('你想用'+'还是'.join(labels)+'？',choices=labels+['自己打'])
                if len(offered)>1:
                    pick=re.fullmatch(r'(?:我)?(?:要|选|走)?([两二三23])上(?:方案)?[。！!]?',text)
                    if not pick:
                        return result('你想走两上还是三上？',choices=['两上方案','三上方案','自己打'])
                    plan='three' if pick[1] in ('三','3') else 'two'
                    old=next(option for option in offered if option['par_plan']==plan)
                elif text!='按这个打':
                    c['phase']='tee_intent';return result('好，这一洞你现在更想怎么处理？')
                checked=tee_proposal(c,a,c.get('selected_club'))
                updated=next((option for option in checked['options']
                              if option.get('par_plan')==old.get('par_plan')),None)
                if not same_target(old,updated) or updated.get('strategy')!=old.get('strategy'):
                    return tee_offer(c,a)
                c['suggestion']=updated
                c['decision']=copy.deepcopy(c['suggestion']);j['last_consultation']=copy.deepcopy(c);j.pop('consultation',None)
                if p.get('_stroke_consistency_v111'):
                    j.setdefault('player_decisions',[]).append(dict(
                        club=c['decision']['club'],target=c['decision']['target'],hole=c['decision']['hole'],
                        source='user_report',event_id=p['event_id'],type='decision_commitment',execution_confirmed=False))
                plan_name={'two':'两上方案','three':'三上方案'}.get(c['decision'].get('par_plan'))
                if plan_name:
                    return result(f"好，走{plan_name}。先用{c['decision']['club']}瞄{c['decision']['target']}，开球落定后再确认第二杆。")
                return result('好，开球用'+c['decision']['club']+'，瞄'+c['decision']['target']+'，按平常节奏打。' if p.get('_stroke_consistency_v111') else '按你确认的'+c['decision']['club']+'、'+c['decision']['target']+'目标来。实际执行等你报告，不自动记作击球。')
            if c['phase']=='intent':
                c['player_intent']=text;c['phase']='ball'
                return result('你现在就在自己的球旁吗？',choices=['就在球旁','还在走过去','自己打'])
            if c['phase']=='ball':
                if text!='就在球旁':return result('到球旁再一起看，这里先不把设备位置当落点。',choices=['就在球旁','自己打'])
                c['ball_position_report']='user_confirmed'
                from shot_links import observe
                observe(s,now,query=True,preserve_played_shots=p.get('_simulation_shot_v93',False))
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
                routes=c.get('strategy_assessment',{}).get('route_choices',{})
                route_match=re.fullmatch(r'(?:好|好的)?[，,\s]*(?:就|选|走)?(两上|三上)(?:方案)?[。！! ]*',text)
                if routes and route_match:
                    if c.get('position_version') is not None and __import__('green_requests').position_changed(s,c,now):
                        return result('球位已变化，请重新问这杆怎么打。')
                    selected=routes['attack' if route_match[1]=='两上' else 'layup']
                    c['selected_route']=route_match[1]
                    from ball_outcome import reported_penalties
                    name=route_match[1]
                    if reported_penalties(s,fact_value(s,'context.active_hole')):
                        name='直接攻果岭' if name=='两上' else '过渡后攻果岭'
                    return result('好，采用刚才的'+name+'方案。'+selected+'这杆准备用哪支杆？')
                if __import__('short_game').question(text):return result('这是在询问打法，我不会把它记成你的决定。刚才的方案先保留。')
                if not __import__('short_game').explicit_plan(text):return result('刚才的打法方案先保留，这句话不记成击球决定。')
                if (c.get('position_version') is not None and __import__('green_requests').position_changed(s,c,now)):
                    c['phase']='ball';return result('位置已变化，我们先重新确认：你现在就在球旁吗？',choices=['就在球旁','自己打'])
                c['player_plan']=text;c['phase']='commit'
                return result('你选的是“'+text[:100]+'”。就按这个方案执行吗？',choices=['按这个打','再想想','自己打'])
            if c['phase']=='commit':
                if __import__('short_game').question(text):return result('这是在询问打法，刚才的方案先保留，不替你确认执行。')
                if text!='按这个打':c['phase']='intent';return result('好，你现在更想怎么处理？',choices=['稳一点','想上果岭','自己打'])
                if (c.get('position_version') is not None and __import__('green_requests').position_changed(s,c,now)):
                    c['phase']='ball';return result('位置已变化，先确认你是否仍在球旁？',choices=['就在球旁','自己打'])
                c['decision']=c['player_plan'];j['last_consultation']=copy.deepcopy(c);j.pop('consultation',None)
                return result('按你确认的“'+c['decision'][:100]+'”来，专注一个目标，按熟悉节奏挥杆。实际用了什么杆，等你报告再记录。')
        query=text+(j['profile'].get('units',{}).get('value','码')) if text=='还有多少' else text
        r=delegate(dict(p,type='voice',text=query))
        if r.get('unsupported'):
            return result('我听到了。这版先保留你的表达，不把普通聊天写成击球事实。你可以继续聊，或询距、报成绩。',unsupported=True)
        return r
    if p.get('_stroke_consistency_v111'):
        from postgame_delivery import handle as postgame_reply
        delivered=postgame_reply(s,text,p['event_id'])
        if delivered:return result(delivered['text'],choices=delivered['choices'])
    if stage=='finish_confirm':
        if text=='继续打球':j['stage']='active';return result('继续打，需要时叫我。')
        if text!='确认结束':return ask(stage)
        require(not s.get('session',{}).get('draft'),'尚有未确认成绩，请继续打球后确认或跳过该记录')
        current=summary(s);j['round']['finished']=True;j['history'].append({'round':copy.deepcopy(j['round']),**current})
        if p.get('_stroke_consistency_v111'):
            from course_history_comparison import basis
            j['history'][-1]['course_basis']=basis(s)
            from hole_history import archive_current
            archive_current(s)
        plan=j['coach'].get('plan')
        note=''
        if j['coach']['enabled'] and plan and j['coach'].get('paused_round')!=j['round']['id']:
            evaluation=compare(plan,current);plan.setdefault('checks',[]).append({'round_id':j['round']['id'],**evaluation});note=evaluation['text']
        if p.get('_stroke_consistency_v111'):
            return ask('review_offer',f"已收好{current['confirmed_holes']}洞确认成绩；未记的洞保持未知。"+note)
        return ask('feeling',f"已收好{current['confirmed_holes']}洞确认成绩；未记的洞保持未知。"+note)
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
        if p.get('_stroke_consistency_v111') and text not in ('不想提升','不愿意','不开启','不用','不需要','拒绝'):
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


@planning_geometry_cache
def reduce_journey(s,p,seq,now):
    if p.get('protocol_version') in (54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99,100,101,102,103,104,105,106,107,108,109,110,111):
        from journey_style_preferences import reduce_journey as styles
        return styles(s,p,seq,now)
    if p.get('protocol_version')==53:
        from journey_habits import reduce_journey as habits
        return habits(s,p,seq,now)
    if p.get('protocol_version')==52:
        return reduce_journey(s,dict(p,protocol_version=51,_pin_reply_v52=True),seq,now)
    if p.get('protocol_version')==51:
        from journey_recovery import reduce_journey as recovery
        return recovery(s,p,seq,now)
    if p.get('protocol_version')==50:
        from journey_previous_club import reduce_journey as previous_club
        return previous_club(s,p,seq,now)
    if p.get('protocol_version')==49:
        from journey_named_tee_choice import reduce_journey as tee_choice
        return tee_choice(s,p,seq,now)
    if p.get('protocol_version')==48:
        from journey_onboarding import reduce_journey as onboarding
        return onboarding(s,p,seq,now)
    if p.get('protocol_version')==47:
        from journey_round_preferences import reduce_journey as preferences
        return preferences(s,p,seq,now)
    if p.get('protocol_version')==46:
        from journey_spoken_assent import reduce_journey as spoken_assent
        return spoken_assent(s,p,seq,now)
    if p.get('protocol_version')==45:
        from journey_bare_score import reduce_journey as bare_score
        return bare_score(s,p,seq,now)
    if p.get('protocol_version')==44:
        from journey_carry_report import reduce_journey as carry_report
        return carry_report(s,p,seq,now)
    if p.get('protocol_version')==43:
        from journey_par_three import reduce_journey as par_three
        return par_three(s,p,seq,now)
    if p.get('protocol_version')==42:
        from journey_simulation_score import reduce_journey as score_prompt
        return score_prompt(s,p,seq,now)
    if p.get('protocol_version')==41:
        from journey_simulation_navigation import reduce_journey as navigation
        return navigation(s,p,seq,now)
    if p.get('protocol_version')==40:
        from journey_pin_location import reduce_journey as pin
        return pin(s,p,seq,now)
    if p.get('protocol_version')==39:
        from journey_current_distance import reduce_journey as current
        return current(s,p,seq,now)
    if p.get('protocol_version')==38:
        from journey_round_flow import reduce_journey as flow
        return flow(s,p,seq,now)
    if p.get('protocol_version')==37:
        from journey_tee_options import reduce_journey as options
        return options(s,p,seq,now)
    if p.get('protocol_version')==36:
        from journey_distance_comparison import reduce_journey as comparison
        return comparison(s,p,seq,now)
    if p.get('protocol_version')==35:
        from journey_distance_followup import reduce_journey as followup
        return followup(s,p,seq,now)
    if p.get('protocol_version')==34:
        from journey_projection import reduce_journey as projection
        return projection(s,p,seq,now)
    if p.get('protocol_version')==33:
        from journey_navigation_queries import reduce_journey as navigation_queries
        return navigation_queries(s,p,seq,now)
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
    if p.get('protocol_version')==17:
        from journey_hazards import reduce_journey as hazards
        return hazards(s,p,seq,now)
    if p.get('protocol_version')==18:
        from journey_phoenix import reduce_journey as phoenix
        return phoenix(s,p,seq,now)
    if p.get('protocol_version')==19:
        from journey_short_selection import reduce_journey as short_selection
        return short_selection(s,p,seq,now)
    if p.get('protocol_version')==20:
        from journey_actionable import reduce_journey as actionable
        return actionable(s,p,seq,now)
    if p.get('protocol_version')==21:
        from journey_preround_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==22:
        from journey_approach_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==23:
        from journey_green_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==24:
        from journey_space_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==25:
        from journey_lateral_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==26:
        from journey_routing_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==27:
        from journey_link_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==28:
        from journey_short_game_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==29:
        from journey_map_first_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==30:
        from journey_hazard_route_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    if p.get('protocol_version')==31:
        from journey_dialogue_legacy import reduce_journey as previous
        return previous(s,p,seq,now)
    require(p.get('protocol_version')==32,'unsupported journey protocol')
    if ((s.get('journey',{}).get('stage')=='ready' and p.get('type')=='message' and p.get('text')=='开始球局') or (p.get('type')=='gps' and s.get('journey',{}).get('stage') in ('tee','start_hole','goal','ready'))) and (s.get('journey',{}).get('round') or {}).get('course')=='dongguan-phoenix-ab-blue-demo':
        if 'demo_course_snapshot' not in p:
            from phoenix_demo import course
            p['demo_course_snapshot']=course()
        require(p['demo_course_snapshot'].get('course_id')=='dongguan-phoenix-ab-blue-demo' and p['demo_course_snapshot'].get('reference_simulation') is True,'invalid demo snapshot')
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
    from dialogue_routing import record_response
    record_response(s,p,out,now)
    s['journey']['turn_choices']=out.get('choices',[])
    if 'choices' in out:out['choices']=list(out['choices'])
    s['journey'].setdefault('receipts',{})[p['event_id']]={'digest':digest,'result':copy.deepcopy(out)}
    return out
