"""Contextual shot preferences from explicit choices and on-course reports."""
import hashlib
import re

from journey_tee_options import choice as tee_choice, silent
from round_state import canonical, require, fact_value

OPTIONS = {
    'water': ('直接过水', '先打到水前'),
    'green': ('切滚', '高抛'),
}
CONTEXT = {'water': '过水', 'green': '果岭边'}
BOTH = {'water': '确认能过水也能打到水前', 'green': '确认切滚和高抛都能打'}
CHOICE = re.compile(r'(确认能过水也能打到水前|确认切滚和高抛都能打)[，,]\s*我选([^，,。！？?]+)')
PREFERENCE = re.compile(r'(过水|果岭边)我通常([^，,。！？?]+)')
EDGE_CHOICE = re.compile(r'靠边旗两种目标都能打[，,]\s*我选(打向果岭中央|攻旗)')
EDGE_PREFERENCE = re.compile(r'靠边旗我通常(打向果岭中央|攻旗)')
EDGE_SIDES = {'左', '右'}
EDGE_DEPTHS = {'前', '后'}

def edge_pin(pin):
    return pin.get('status') == 'complete' and (
        pin.get('side') in EDGE_SIDES or pin.get('depth') in EDGE_DEPTHS
    )


def edge_reply(state, journey, text, event_id):
    from dialogue_routing import scope

    preferences = journey['profile'].get('shot_style_preferences', {})
    if text == '忘记靠边旗打法偏好':
        preferences.pop('edge_pin', None)
        journey.get('shot_style_evidence', {}).pop('edge_pin', None)
        return '好，已清除靠边旗打法偏好。'
    declared = EDGE_PREFERENCE.fullmatch(text)
    choice = EDGE_CHOICE.fullmatch(text)
    if not (declared or choice):
        return None
    if journey.get('memory_allowed') is not True:
        return '开启跨场记忆后，我可以把这个偏好留到下次。'
    method = (declared or choice)[1]
    if declared:
        journey['profile'].setdefault('shot_style_preferences', {})['edge_pin'] = {
            'value': method, 'source': 'user_report', 'event_id': event_id,
        }
        journey.get('shot_style_evidence', {}).pop('edge_pin', None)
        return f'记下了，靠边旗两种目标都合适时，你通常选{method}。'
    current_scope = scope(state)
    pin = journey.get('pin_locations', {}).get(canonical(current_scope), {})
    if not edge_pin(pin):
        return '先告诉我这洞的旗位，我再把这次选择用来了解你的习惯。'
    learned = learn(journey, 'edge_pin', method, event_id, current_scope[2])
    if learned and not preferences.get('edge_pin'):
        journey['profile'].setdefault('shot_style_preferences', {})['edge_pin'] = {
            'value': learned, 'source': 'repeated_choices', 'event_id': event_id,
        }
        return f'记下了，最近几次靠边旗两种目标都能打时，你都选择{method}。'
    return f'听到了，这杆你选择{method}。'


def edge_note(journey, result):
    if not edge_pin(result.get('pin_location', {})):
        return None
    preference = journey['profile'].get('shot_style_preferences', {}).get('edge_pin', {}).get('value')
    if preference == '打向果岭中央':
        return '靠边旗你通常瞄果岭中央，可以先看中央的落点。'
    if preference == '攻旗':
        return '有余量时你喜欢攻旗。这杆先核对旗侧落点和飞越余量，确认有空间再考虑攻旗。'
    return None


ASK = re.compile(r'(确认能过水也能打到水前|确认切滚和高抛都能打)[，,]\s*怎么选[？?]?')


def learn(journey, kind, choice, event_id, hole):
    history = journey.setdefault('shot_style_evidence', {}).setdefault(kind, [])
    round_id = journey['round']['id']
    # Count at most one comparable choice per hole and round.
    key = [round_id, hole]
    history[:] = [row for row in history if row['key'] != key]
    history.append({'key': key, 'choice': choice, 'event_id': event_id})
    del history[:-5]
    if len(history) >= 3 and all(row['choice'] == choice for row in history[-3:]):
        return choice
    return None


def swing_reply(state, journey, text, event_id):
    from dialogue_routing import scope

    preferences = journey['profile'].get('shot_style_preferences', {})
    if text == '忘记两支杆之间的偏好':
        preferences.pop('between_clubs', None)
        journey.get('shot_style_evidence', {}).pop('between_clubs', None)
        return '好，已清除两支杆之间的挥杆偏好。'
    declared = re.fullmatch(r'两支杆之间我通常(短一号正常挥|长一号收着打)', text)
    choice = re.fullmatch(r'两支杆都能打[，,]\s*我选(短一号正常挥|长一号收着打)', text)
    if not (declared or choice):
        return None
    if journey.get('memory_allowed') is not True:
        return '开启跨场记忆后，我可以把这个偏好留到下次。'
    method = (declared or choice)[1]
    _, _, hole = scope(state)
    learned = choice and hole is not None and not preferences.get('between_clubs') and learn(
        journey, 'between_clubs', method, event_id, hole
    )
    if declared or learned:
        journey['profile'].setdefault('shot_style_preferences', {})['between_clubs'] = {
            'value': method, 'source': 'user_report' if declared else 'repeated_choices', 'event_id': event_id,
        }
        if declared:
            journey.get('shot_style_evidence', {}).pop('between_clubs', None)
        return f'记下了，两支杆都合适时，你通常{method}。'
    return f'听到了，这杆你选{method}。'


def tee_preferences(journey, text, event_id):
    profile = journey['profile']
    preferences = profile.get('shot_style_preferences', {})
    route = re.fullmatch(r'开球我通常(选保守路线|选进取路线)', text)
    leave = re.fullmatch(r'我喜欢(?:给)?下一杆留([1-9][0-9]{0,2})(码|米)', text)
    if text in ('忘记开球打法偏好', '忘记下一杆距离偏好'):
        kind = 'tee' if text == '忘记开球打法偏好' else 'leave_distance'
        preferences.pop(kind, None)
        journey.get('shot_style_evidence', {}).pop(kind, None)
        return '好，已清除这项偏好。'
    if not (route or leave):
        return None
    if journey.get('memory_allowed') is not True:
        return '开启跨场记忆后，我可以把这个偏好留到下次。'
    preferences = profile.setdefault('shot_style_preferences', {})
    if route:
        value = 'conservative' if route[1] == '选保守路线' else 'aggressive'
        preferences['tee'] = {'value': value, 'source': 'user_report', 'event_id': event_id}
        journey.get('shot_style_evidence', {}).pop('tee', None)
        return '记下了，两条开球路线都合适时，我会参考你的选择习惯。'
    preferences['leave_distance'] = {'value': int(leave[1]), 'unit': leave[2],
                                     'source': 'user_report', 'event_id': event_id}
    return f'记下了，你喜欢下一杆留{leave[1]}{leave[2]}。'


def tee_note(journey, routes, learned_leave=None, *, use_leave=True):
    preferences = journey.get('profile', {}).get('shot_style_preferences', {})
    leave = (preferences.get('leave_distance') or learned_leave) if use_leave else None
    safe = [route for route in routes if route['kind'] == 'conservative'
            or '要留意偏向障碍' not in route['risk']]
    if leave and safe:
        reason = '你喜欢' if preferences.get('leave_distance') else '按你的短杆实绩，可以先参考'
        target = leave['value'] / (.9144 if leave['unit'] == '米' else 1)
        best = min(safe, key=lambda route: abs(route['remaining_yards'] - target))
        if abs(best['remaining_yards'] - target) <= 10:
            name = '保守' if best['kind'] == 'conservative' else '进取'
            return f'{reason}下一杆留{leave["value"]}{leave["unit"]}，{name}方案的预计剩余距离接近这个距离。'
    preferred = preferences.get('tee', {}).get('value')
    if preferred and any(route['kind'] == preferred for route in safe):
        name = '保守' if preferred == 'conservative' else '进取'
        return f'按你平时的开球习惯，可以先看{name}方案。'
    return None


def reduce_journey(state, event, seq, now):
    event_id = event.get('event_id')
    require(isinstance(event_id, str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}', event_id)), 'invalid event id')
    digest = hashlib.sha256(canonical(event).encode()).hexdigest()
    journey = state.get('journey', {})
    prior = journey.get('style_receipts', {}).get(event_id)
    if prior:
        require(prior == digest, 'event id reused with different payload')
        return {'text': '', 'speak_allowed': False, 'duplicate': True}

    if event.get('protocol_version',0)>=111 and event.get('type')=='correct_stroke_origin_to_tee':
        from stroke_origin_correction import apply
        result=apply(state,event,now)
        journey.pop('round_review_cache',None)
        journey.setdefault('style_receipts',{})[event_id]=digest
        state['version']=seq
        return result

    if event.get('protocol_version',0)>=111 and event.get('type')=='clear_round_review':
        for key in ('round_review_requested','round_review_expand_event','round_review_cache','postgame_followup'):
            journey.pop(key,None)
        journey.setdefault('style_receipts',{})[event_id]=digest
        state['version']=seq
        return dict(text='已清除本场分析总结及展示状态，成绩和实际用杆保留。',speak_allowed=False)

    if event.get('protocol_version',0)>=111 and event.get('type')=='course_metadata_correction':
        from copy import deepcopy
        evidence_id=fact_value(state,'context.course_snapshot')
        snapshot=state.get('evidence',{}).get(evidence_id,{}).get('data',{})
        require(snapshot.get('course_id')=='dongguan-phoenix-ab-blue-demo','Phoenix snapshot required')
        number=event.get('data',{}).get('hole')
        require(number in (11,17),'unsupported hole correction')
        hole=next(h for h in snapshot['holes'] if h['number']==number)
        yardage=event['data'].get('published_yardage')
        require((number==11 and yardage in (None,380)) or (number==17 and yardage==130),'unsupported yardage correction')
        par=4 if number==11 else 3
        hole.update(par=par,published_yardage=yardage,metadata_correction=deepcopy(event['data']['provenance']))
        journey.pop('round_review_cache',None)
        for key in ('consultation','last_consultation','tee_route_options','response_context'):
            journey.pop(key,None)
        journey.setdefault('style_receipts',{})[event_id]=digest
        state['version']=seq
        return dict(text=f'第{number}洞已修正为{par}杆洞，'+(f'{yardage}码。' if yardage else '公布长度待核实。'),speak_allowed=False)

    if (event.get('protocol_version',0)>=111 and event.get('type')=='gps'
            and journey.get('stage') not in ('tee','start_hole','goal','ready','active')):
        journey.setdefault('style_receipts',{})[event_id]=digest
        state['version']=seq
        return dict(text='',speak_allowed=False,ignored=True,reason='round_inactive')

    data=event.get('data',{})
    if event.get('protocol_version',0)>=111 and event.get('type')=='gps' and data.get('simulation_refresh') and data.get('simulation_source')=='map_click':
        from shot_evidence import haversine
        position=fact_value(state,'context.device_position')
        if position and all(type(data.get(k)) in (int,float) for k in ('latitude','longitude','accuracy_m')):
            wrong_hole=data.get('simulation_hole')!=fact_value(state,'context.active_hole')
            moved=haversine(position,data)>max(5,min(15,position.get('accuracy_m',2)+data['accuracy_m']))
            if wrong_hole or moved:
                journey.setdefault('style_receipts',{})[event_id]=digest
                state['version']=seq
                return dict(text='',speak_allowed=False,ignored=True,reason='stale_simulation_position')

    text = event.get('text', '').strip().rstrip('。！!')
    enhanced = event.get('protocol_version') in (55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111)
    edge_enabled = event.get('protocol_version') in (56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111)
    offer = journey.get('tee_route_options') or {}
    selected = (tee_choice(text) if enhanced and event.get('type') == 'message'
                and offer.get('status') == 'awaiting_choice'
                and journey.get('memory_allowed') is True
                and journey.get('response_context', {}).get('question_owner') == 'tee.choice'
                and all('要留意偏向障碍' not in route['risk'] for route in offer.get('routes', []))
                else None)
    learned_leave = None
    if 60<=event['protocol_version']<111 and journey.get('memory_allowed') is True:
        from wedge_leave import suggested_leave

        learned_leave = suggested_leave(journey)
    if event.get('protocol_version',0)>=107 and journey.get('stage')=='active':
        from ball_rules import initialize
        flow=initialize(state)
        if event.get('protocol_version',0)>=111:
            from ball_rules import enable_consistency
            enable_consistency(state,flow)
    before = journey.get('last_consultation')
    reply = None
    if event.get('type') == 'message' and journey.get('stage') == 'active' and not silent(state):
        if event['protocol_version'] >= 111:
            from landing_reports import handle as landing_reply
            reply=landing_reply(state,event,now)
        if reply is None and event['protocol_version'] >= 107:
            from ball_rules import handle as rule_reply
            reply=rule_reply(state,event,text,now)
        if reply is None and event['protocol_version'] >= 106:
            from shot_audio import handle
            reply=handle(state,event,now)
        if reply is None and 105<=event['protocol_version']<107:
            from ball_outcome import handle
            reply=handle(state,event,text,now)
        if reply is None and event['protocol_version']>=111:
            from fairway_finder import handle as finder_reply
            reply=finder_reply(state,text,event_id)
        if reply is None and event['protocol_version']>=111:
            from bunker_distance_query import handle as bunker_query
            reply=bunker_query(state,text,now)
        if reply is None and event['protocol_version']>=111:
            from safer_tee_query import handle as safer_query
            reply=safer_query(state,text,now,event_id)
        if reply is None and event['protocol_version']>=111:
            from tee_club_query import handle as tee_club_query
            reply=tee_club_query(state,text,now)
        if reply is None and event['protocol_version'] >= 65:
            from putt_performance import record

            reply = record(state, text, event_id)
        if reply is None and event['protocol_version'] >= 64:
            from lie_performance import compare_flight, respond as lie_reply

            reply = lie_reply(state, text, event_id)
            if reply is None and event['protocol_version'] >= 65:
                reply = compare_flight(journey, text)
        if reply is None and event['protocol_version'] >= 63:
            from tee_performance import record

            reply = record(state, text, event_id)
        if reply is None and event['protocol_version'] >= 62:
            from wedge_leave import record_or_compare_green

            reply = record_or_compare_green(state, text, event_id)
        if reply is None and event['protocol_version'] >= 60:
            from wedge_leave import record_or_query

            reply = record_or_query(state, text, event_id, combinations=event['protocol_version'] >= 61)
        if reply is None and event.get('protocol_version') in (58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111):
            from on_course_preferences import approach_note, respond as on_course_reply

            reply = on_course_reply(state, text, event_id, now, check_layup_match=event['protocol_version'] >= 59, learned_leave=learned_leave, learned_pace=event['protocol_version'] >= 65,risk_first=event['protocol_version']>=111) or approach_note(journey, text)
        if event.get('protocol_version') in (57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111) and reply is None:
            reply = swing_reply(state, journey, text, event_id)
        if edge_enabled and reply is None:
            reply = edge_reply(state, journey, text, event_id)
        if enhanced and reply is None:
            reply = tee_preferences(journey, text, event_id)
        if reply is None:
            reply = respond(state, journey, text, event_id)
    if reply is None:
        from journey import reduce_journey as previous

        adapted = dict(event, protocol_version=53)
        if event['protocol_version'] >= 67:
            adapted['_pin_reply_v67'] = True
        if event['protocol_version'] >= 68:
            adapted['_wedge_bag_v68'] = True
        if event['protocol_version'] >= 69:
            adapted['_dialogue_v69'] = True
        if event['protocol_version'] >= 70:
            adapted['_dialogue_v70'] = True
        if event['protocol_version'] >= 71:
            adapted['_dialogue_v71'] = True
        if event['protocol_version'] >= 72:
            adapted['_score_v72'] = True
        if event['protocol_version'] >= 73 and event.get('type') == 'message' and re.fullmatch(
            r'打了(?:多少(?:码|米)?|多远|几码|几米)(?:呢|啊)?[？?。！!]?', text
        ):
            adapted['text'] = '上一杆' + text
        if event['protocol_version'] >= 74:
            adapted['_infer_putts_v74'] = True
        if event['protocol_version'] >= 76:
            adapted['_score_copy_v76'] = True
        if event['protocol_version'] >= 77:
            adapted['_wedge_continue_v77'] = True
        if event['protocol_version'] >= 78 and event.get('type') == 'message':
            from round_session import N

            number = '(?:' + N[1:-1] + ')'
            compact = re.sub(r'\s+', '', text)
            score = re.fullmatch(
                rf'((?:{number}号洞|这洞|本洞)?{number}杆)[，,]?({number}推)(?:[，,]?({number}罚(?:杆)?))?',
                compact,
            )
            if score:
                adapted['text'] = '，'.join(field for field in score.groups() if field)
        if event['protocol_version'] >= 79:
            adapted['_infer_multi_putts_v79'] = True
        if event['protocol_version'] >= 80:
            adapted['_zero_penalties_v80'] = True
        if event['protocol_version'] >= 81:
            adapted['_pitching_choice_v81'] = True
        if event['protocol_version'] >= 82:
            adapted['_sim_putts_v82'] = True
        if event['protocol_version'] >= 83:
            adapted['_practical_rough_v83'] = True
        if event['protocol_version'] >= 84:
            adapted['_followups_v84'] = True
        if event['protocol_version'] >= 85:
            adapted['_landing_depth_v85'] = True
        if event['protocol_version'] >= 86:
            adapted['_aim_lines_v86'] = True
        if event['protocol_version'] >= 87:
            adapted['_audit_v87'] = True
        if event['protocol_version'] >= 88:
            adapted['_correction_v88'] = True
        if event['protocol_version'] >= 89:
            adapted['_pin_distance_prompt_v89'] = True
        if event['protocol_version'] >= 90 and event.get('type') == 'message':
            pitching_choice = re.fullmatch(r'好的[，,\s]*(用[Pp]杆(?:吧)?[。！!]?)', text)
            if pitching_choice:
                adapted['text'] = pitching_choice[1]
        if event['protocol_version'] >= 92:
            adapted['_score_wording_v92'] = True
        if event['protocol_version'] >= 93:
            adapted['_simulation_shot_v93'] = True
        if event['protocol_version'] >= 94:
            adapted['_tee_geometry_v94'] = True
        if event['protocol_version'] >= 95:
            adapted['_par_five_v95'] = True
        if event['protocol_version'] >= 96:
            adapted['_carry_crossing_v96'] = True
        if event['protocol_version'] >= 97:
            adapted['_par_five_compare_v97'] = True
        if event['protocol_version'] >= 98:
            adapted['_ask_fairway_carry_v98'] = True
        if event['protocol_version'] >= 99:
            adapted['_carry_playability_v99'] = True
        if event['protocol_version'] >= 100:
            adapted['_tee_brief_order_v100'] = True
        if event['protocol_version'] >= 101:
            adapted['_par_five_bag_v101'] = True
        if event['protocol_version'] >= 102:
            adapted['_par_five_roll_v102'] = True
        if event['protocol_version'] >= 103:
            adapted['_shared_tee_club_v103'] = True
        if event['protocol_version'] >= 104:
            adapted['_approach_risk_v104'] = True
        if event['protocol_version'] >= 105:
            adapted['_ball_outcome_v105'] = True
        if event['protocol_version'] >= 107:
            adapted['_ball_rules_v107'] = True
        if event['protocol_version'] >= 108:
            adapted['_middle_pin_v108'] = True
        if event['protocol_version'] >= 109:
            adapted['_approach_lie_v109'] = True
        if event['protocol_version'] >= 111:
            adapted['_stroke_consistency_v111'] = True
        draft=state.get('session',{}).get('draft') or {}
        if (event.get('protocol_version',0)>=106 and event.get('type')=='resume'
                and not draft.get('penalties_explicit')
                and type(draft.get('total')) is int and type(draft.get('putts')) is int
                and (draft.get('penalties') or 0)>draft['total']):
            from ball_outcome import reported_penalties
            penalty=reported_penalties(state,draft['hole'])
            if draft['putts']+penalty<=draft['total']:
                adapted.update(type='message',text=f"{draft['hole']}号洞{draft['total']}杆，{draft['putts']}推，{penalty}罚杆")
        learning_consultation=journey.get('consultation') or {}
        learning_offer=__import__('copy').deepcopy(learning_consultation.get('last_offer') or {}) if learning_consultation.get('phase','').startswith('tee_') else {}
        decisions_before=len(journey.get('player_decisions', []))
        result = previous(state, adapted, seq, now)
        journey = state['journey']
        from tee_decision_framework import record as record_tee_preference
        record_tee_preference(state,learning_offer,journey.get('player_decisions',[])[decisions_before:])
        if event.get('protocol_version',0)>=107:
            from shot_links import scope as decision_scope
            for decision in journey.get('player_decisions',[])[decisions_before:]:
                decision.update(round_scope=list(decision_scope(state)),observed_at=event['observed_at'])
        if event['protocol_version'] >= 66 and not result.get('duplicate'):
            from tee_club_fallback import update

            result = update(state, event, now, before, result,
                            decision=(journey.get('player_decisions') or [None])[-1]
                            if event['protocol_version'] >= 70 and len(journey.get('player_decisions', [])) > decisions_before else None)
        if result.get('simulation_hole_switched') is not None and not result.get('duplicate'):
            from shot_links import scope
            target_key=canonical(scope(state))
            if event.get('protocol_version',0)>=111:
                if event.get('clear_test_records') is True:
                    journey.setdefault('simulation_attempts',{})[target_key]=event['observed_at']
                    from simulation_hole_reset import clear
                    clear(state)
                    result.update(text='已清除本轮第'+str(event['hole'])+'洞测试记录，回到该洞发球台；未新增击球。',speak_allowed=True)
                # Navigation is not a new attempt: retain shots, penalties,
                # pin observations and the score prompt's current attempt.
                from ball_rules import initialize,enable_consistency
                enable_consistency(state,initialize(state))
            else:
                outcome=journey.get('ball_outcomes', {}).get(target_key)
                if outcome:outcome.update(phase='closed',outcome=None)
                journey.get('pin_locations',{}).pop(target_key,None)
                journey.setdefault('simulation_attempts',{})[target_key]=event['observed_at']
                if event.get('protocol_version',0)>=107:
                    from ball_rules import reset
                    reset(state)
            journey.pop('shot_audio', None)
            for key in ('tee_club_fallback','simulated_club_choice','last_consultation','approach_club_offer'):
                journey.pop(key, None)
        handled_position = False
        if (event['protocol_version'] >= 105 and event.get('type') == 'gps'
                and not result.get('ignored') and not result.get('duplicate')):
            if event['protocol_version']>=107:
                from ball_rules import on_position, blocking, correct_landing
                if event.get('data',{}).get('simulation_position_action')=='correct':
                    correct_landing(state,event,now)
                handled_position=on_position(state,event,now)
                if handled_position is not None:
                    result.update(text=handled_position,speak_allowed=bool(handled_position) and not silent(state))
                    if silent(state):result['text']=''
                    handled_position=True
                elif blocking(state):
                    handled_position=True
            else:
                from ball_outcome import after_position, current
                handled_position=after_position(state,event,now)
                if handled_position and not silent(state):
                    result.update(text=handled_position,speak_allowed=True)
                elif (current(state) or {}).get('phase') in ('check','search','water_check','provisional','replay','water'):
                    handled_position=True
        if (not handled_position and event['protocol_version'] >= 91 and event.get('type')=='gps'
                and journey.get('stage')=='active' and not result.get('ignored') and not result.get('duplicate')):
            from shot_links import record_simulated_landing

            preserve_played_shots = event['protocol_version'] >= 93
            recorded = record_simulated_landing(state,event,now,preserve_played_shots=preserve_played_shots)
            if preserve_played_shots and recorded:
                result['simulated_shot_recorded'] = True
                if event['protocol_version']>=107:
                    from ball_rules import on_record, map_landing
                    on_record(state,event,now)
                    note=map_landing(state,event,now)
                elif event['protocol_version']>=105:
                    from ball_outcome import after_landing
                    note=after_landing(state,event)
                else:
                    note=None
                if note and not silent(state):
                    result.update(text=result.get('text','')+note,speak_allowed=True)
        if event['protocol_version'] >= 71 and result.get('saved'):
            from score_shot_reconciliation import reconcile

            note = reconcile(state, event_id, allow_partial_clubs=event['protocol_version'] >= 75, trim_green=event['protocol_version'] >= 84, current_only=event['protocol_version'] >= 87)
            if note:
                result = {**result, 'text': result.get('text', '') + note}
        if event['protocol_version'] >= 75 and event.get('type') == 'resume':
            from score_shot_reconciliation import reconcile

            for index, (patch_id, patch) in enumerate(state.get('patches', {}).items()):
                if patch.get('status') == 'committed':
                    note = reconcile(state, f'{event_id}-backfill-{index}', allow_partial_clubs=True, patch_id=patch_id, trim_green=event['protocol_version'] >= 84, current_only=event['protocol_version'] >= 87)
                    if note and result.get('speak_allowed'):
                        result['text'] += note
        advice = journey.get('last_short_game_advice', {})
        green = journey.get('profile', {}).get('shot_style_preferences', {}).get('green', {}).get('value')
        if (journey.get('memory_allowed') is True and green and result.get('text')
                and advice.get('event_id') == event_id
                and advice.get('source') in ('mapped_route', 'user_confirmed_rollable_route')
                and not journey.get('round', {}).get('service_policy', {}).get('fatigued')):
            if green == '切滚':
                result['text'] = '这类通畅路线符合你惯用的切滚。' + result['text']
            else:
                result['text'] = ('这条线也能切滚。按你惯用的打法，如果球位干净、'
                                  '有宽阔落点且今天高抛有把握，可以先考虑高抛。' + result['text'])
    else:
        result = {'text': reply, 'speak_allowed': True}
    if edge_enabled and journey.get('memory_allowed') is True and result.get('text'):
        note = edge_note(journey, result)
        if note:
            result['text'] = note + result['text']
    if enhanced and journey.get('memory_allowed') is True:
        selection = (journey.get('consultation') or {}).get('selection_report', {})
        if selected and selection.get('event_id') == event_id:
            from dialogue_routing import scope

            _, _, hole = scope(state)
            preferences = journey['profile'].setdefault('shot_style_preferences', {})
            if hole is not None and not preferences.get('tee'):
                learned = learn(journey, 'tee', selected, event_id, hole)
                if learned:
                    preferences['tee'] = {'value': learned, 'source': 'repeated_choices', 'event_id': event_id}
        if result.get('tee_routes') and result.get('text'):
            note = tee_note(journey, result['tee_routes'], learned_leave,use_leave=event.get('protocol_version',0)<111)
            if note:
                result['tee_preference_note'] = note
    if journey.get('memory_allowed') is not True:
        if event['protocol_version'] >= 60:
            journey.pop('wedge_leave_reports', None)
        if event['protocol_version'] >= 62:
            journey.pop('greenside_reports', None)
        if event['protocol_version'] >= 63:
            journey.pop('tee_performance', None)
        if event['protocol_version'] >= 64:
            journey.pop('lie_carry_reports', None)
        if event['protocol_version'] >= 65:
            journey.pop('putt_performance', None)
        journey.pop('shot_style_evidence', None)
        journey.get('profile', {}).pop('shot_style_preferences', None)
    if event.get('protocol_version', 0) >= 106 and event.get('type') == 'message' and reply is None:
        from shot_audio import arm
        arm(state, event, now)
    # Pin observations belong to this round/hole, not to a single club choice.
    if event.get('protocol_version',0)<111 and event.get('type')=='message' and reply is None and len(journey.get('player_decisions', [])) > decisions_before:
        from shot_links import scope
        journey.get('pin_locations', {}).pop(canonical(scope(state)), None)
    if event.get('protocol_version',0)>=111:
        from confirmed_shot_sync import sync
        sync(state)
        from tee_dispersion import sync as sync_dispersion
        sync_dispersion(state)
    if event.get('protocol_version',0)>=111:
        from postgame_delivery import ensure_cache
        ensure_cache(state)
    journey.setdefault('style_receipts', {})[event_id] = digest
    return result


def respond(state, journey, text, event_id):
    from dialogue_routing import scope

    profile = journey['profile']
    saved = profile.get('shot_style_preferences', {})
    for kind, context in CONTEXT.items():
        if text == f'忘记{context}打法偏好':
            saved.pop(kind, None)
            journey.get('shot_style_evidence', {}).pop(kind, None)
            return f'好，已清除你的{context}打法偏好。'

    choice = CHOICE.fullmatch(text)
    declared = PREFERENCE.fullmatch(text)
    ask = ASK.fullmatch(text)
    if ask:
        kind = next(key for key, phrase in BOTH.items() if phrase == ask[1])
        preferred = saved.get(kind, {}).get('value')
        if kind == 'water':
            safety = '先核对过水所需Carry和水后落点。余量不足就先打到水前。'
        else:
            safety = '地面路线通畅且有滚动空间时可以切滚。遇到挡线障碍或空间变化，重新看落点。'
        prefix = f'按你{CONTEXT[kind]}的偏好，可以优先考虑{preferred}这个方案。' if preferred else ''
        return prefix + safety
    if not (choice or declared):
        return None

    match = choice or declared
    contexts = BOTH if choice else CONTEXT
    kind = next(key for key, phrase in contexts.items() if phrase == match[1])
    method = match[2]
    if method not in OPTIONS[kind]:
        return None
    if journey.get('memory_allowed') is not True:
        return f'听到了，你选{method}。'
    if declared:
        profile.setdefault('shot_style_preferences', {})[kind] = {'value': method, 'source': 'user_report', 'event_id': event_id}
        journey.get('shot_style_evidence', {}).pop(kind, None)
        return f'记下了，两种打法都合适时，你通常选{method}。'

    _, _, hole = scope(state)
    if hole is None:
        return f'这杆按你选的{method}。'
    learned = learn(journey, kind, method, event_id, hole)
    if learned and not saved.get(kind):
        profile.setdefault('shot_style_preferences', {})[kind] = {'value': learned, 'source': 'repeated_choices', 'event_id': event_id}
        return f'这杆按你选的{method}。最近几次两种打法都能打时，你都选了{method}，下次我会先考虑这条路线。'
    return f'这杆按你选的{method}。'
