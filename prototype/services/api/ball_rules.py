"""Ball identities, relief decisions and a replayable stroke/penalty sequence."""
import copy
import re

from lie_position import fresh_position
from round_state import canonical, fact_value
from shot_evidence import haversine
from shot_links import scope

def current(state):
    return state.get('journey', {}).get('ball_rules', {}).get(canonical(scope(state)))


def initialize(state):
    journey = state['journey']
    key = canonical(scope(state))
    if key in journey.get('ball_rules', {}):
        return journey['ball_rules'][key]
    # Seed a saved pre-107 round before installing the new projection.
    from journey import round_records
    from ball_outcome import reported_penalties
    rows = [row for row in round_records(state)['clubs']
            if row.get('hole') == scope(state)[2] and row.get('club') != '推杆']
    penalty = reported_penalties(state, scope(state)[2])
    flow = dict(scope=list(scope(state)), sequence=[], incidents=[], balls={},
                active_ball='original', pending=None, search=None, next_ball=1)
    flow['balls']['original'] = dict(id='original', parent=None, status='in_play')
    last_number = 0
    for index, row in enumerate(rows):
        number = row.get('stroke_number') or last_number+1
        gap = max(0, number-last_number-1)
        if gap and penalty:
            amount = min(gap, penalty)
            flow['sequence'].append(dict(kind='penalty', id='imported-'+str(index),
                                         amount=amount, active=True, ball_id='original'))
            penalty -= amount
        flow['sequence'].append(dict(kind='stroke', id='imported-stroke-'+str(index),
                                     ball_id='original', club=row.get('club'),
                                     distance_m=row.get('total_horizontal_m'), active=True))
        last_number = number
    if penalty:
        flow['sequence'].append(dict(kind='penalty', id='imported-remaining',
                                     amount=penalty, active=True, ball_id='original'))
    migrate_pending(state,flow)
    journey.setdefault('ball_rules', {})[key] = flow
    return flow



def migrate_pending(state, flow):
    """Keep pre-107 unfinished incidents usable through the normal entry point."""
    legacy=state['journey'].get('ball_outcomes',{}).get(canonical(flow['scope'])) or {}
    if not legacy.get('incident_id'):
        return
    phase_map={'check':'search','provisional':'search','water_check':'water_certainty',
               'placement':'relief_position','provisional_live':'live_position',
               'water':'water_color','replay':'replay'}
    pending_phase=phase_map.get(legacy.get('phase'))
    imported_penalties=[item for item in flow['sequence'] if item['kind']=='penalty']
    if not pending_phase and not imported_penalties:
        return
    stroke=last_stroke(flow)
    if not stroke and pending_phase:
        add_stroke(flow,'legacy-original-'+legacy['incident_id'],'original',
                   selected_club(state),legacy.get('provisional_origin'))
        stroke=last_stroke(flow)
    row=dict(id=legacy['incident_id'],ball_id='original',
             cause=legacy.get('outcome') or 'uncertain',
             phase=pending_phase or 'closed',shot_id=stroke['id'] if stroke else None,
             origin=legacy.get('provisional_origin') or (stroke or {}).get('origin'),
             status='active',penalty_ids=[item['id'] for item in imported_penalties],
             provisional_ids=[],drop_count=0,history=[],migrated=True,
             completed_sequence_count=len(flow['sequence']))
    for item in imported_penalties:
        item['incident_id']=row['id']
    if legacy.get('provisional_played') and pending_phase:
        ball_id='legacy-provisional-'+row['id']
        live=legacy.get('phase')=='provisional_live'
        flow['balls'][ball_id]=dict(id=ball_id,parent='original',status='in_play' if live else 'provisional')
        flow['active_ball']=ball_id
        row['provisional_ids']=[ball_id]
        row['promoted']=live
        if live:
            strokes=[item for item in flow['sequence'] if item['kind']=='stroke']
            row['shot_id']=strokes[0]['id'] if strokes else row['shot_id']
            if len(strokes)>1:
                strokes[-1]['ball_id']=ball_id
            else:
                add_stroke(flow,'legacy-live-provisional-'+row['id'],ball_id,
                           legacy.get('provisional_club'),row['origin'])
        if not live:
            add_penalty(flow,row,1,ball_id,suffix=ball_id)
            add_stroke(flow,'legacy-provisional-stroke-'+row['id'],ball_id,
                       legacy.get('provisional_club'),row['origin'])
    flow['incidents'].append(row)
    flow['pending']=row['id'] if pending_phase else None

def reset(state):
    key = canonical(scope(state))
    state['journey'].get('ball_rules', {}).pop(key, None)
    initialize(state)


def ball_counts(flow, ball_id):
    ball = flow['balls'][ball_id]
    return ball['status'] != 'discarded' and ball['status'] != 'provisional'


def rows(flow):
    number = 0
    result = []
    for event in flow['sequence']:
        if not event.get('active', True) or not ball_counts(flow, event['ball_id']):
            continue
        if event['kind'] == 'penalty':
            number += event['amount']
        else:
            number += 1
            result.append(dict(hole=flow['scope'][2], stroke_number=number,
                               club=event.get('club'), total_horizontal_m=event.get('distance_m'),
                               source='ball_rules', ball_id=event['ball_id']))
    return result


def penalties(state, hole):
    flows = state.get('journey', {}).get('ball_rules', {})
    round_id, course, _ = scope(state)
    flow = flows.get(canonical((round_id, course, hole)))
    if flow is None:
        return None
    return sum(event['amount'] for event in flow['sequence']
               if event['kind'] == 'penalty' and event.get('active', True)
               and ball_counts(flow, event['ball_id']))


def position(state, now):
    pos = fresh_position(state, now)
    return copy.deepcopy(pos['value']) if pos else None


def selected_club(state):
    journey=state['journey']
    key=list(scope(state))
    since=journey.get('simulation_attempts',{}).get(canonical(key))
    plans=[plan for plan in journey.get('player_decisions',[])
           if plan.get('hole')==key[2]
           and (not plan.get('round_scope') or plan['round_scope']==key)
           and (not since or plan.get('observed_at','')>=since)]
    return plans[-1].get('club') if plans else None


def add_stroke(flow, event_id, ball_id, club=None, origin=None, landing=None,
               pair_ids=None):
    if any(event['id'] == event_id for event in flow['sequence']):
        return
    from_penalty=flow['balls'][ball_id].get('inside_penalty_area',False)
    if origin and not from_penalty:
        flow['last_outside_origin']=copy.deepcopy(origin)
    flow['sequence'].append(dict(kind='stroke', id=event_id, ball_id=ball_id,
                                 from_penalty_area=from_penalty,
                                 club=club, origin=copy.deepcopy(origin),
                                 landing=copy.deepcopy(landing),
                                 pair_ids=pair_ids, active=True,
                                 distance_m=haversine(origin, landing)
                                 if origin and landing else None))


def last_stroke(flow, ball_id=None):
    ball_id = ball_id or flow['active_ball']
    return next((event for event in reversed(flow['sequence'])
                 if event['kind'] == 'stroke' and event['ball_id'] == ball_id
                 and event.get('active', True)), None)


def capture_original(state, flow, event, now):
    ball_id = flow['active_ball']
    existing = last_stroke(flow, ball_id)
    # The most recent mapped shot has already been registered by on_record.
    if existing and not existing.get('outcome_checked'):
        existing['outcome_checked'] = True
        return existing
    journey = state['journey']
    plan = journey.get('tee_club_fallback') or journey.get('simulated_club_choice') or {}
    origin = plan.get('point') or position(state, now)
    add_stroke(flow, event['event_id']+'-original', ball_id,
               selected_club(state), origin)
    stroke = last_stroke(flow, ball_id)
    stroke['outcome_checked'] = True
    return stroke


def incident(state, flow, event, now, cause='uncertain'):
    if flow.get('pending'):
        return next(row for row in flow['incidents'] if row['id'] == flow['pending'])
    stroke = capture_original(state, flow, event, now)
    row = dict(id=event['event_id'], ball_id=flow['active_ball'], cause=cause,
               phase='search', shot_id=stroke['id'], origin=stroke.get('origin'),
               status='active', penalty_ids=[], provisional_ids=[], drop_count=0,
               history=[], created_at=event['observed_at'],
               from_penalty_area=stroke.get('from_penalty_area',False),
               last_outside_origin=copy.deepcopy(flow.get('last_outside_origin')))
    flow['incidents'].append(row)
    flow['pending'] = row['id']
    from ball_outcome import clear_plan
    clear_plan(state)
    return row


def pending(flow):
    return next((row for row in flow['incidents'] if row['id'] == flow.get('pending')), None)


def record_change(row, event):
    row['history'].append(dict(event_id=event['event_id'], phase=row['phase'],
                               cause=row['cause'], status=row['status']))


def add_penalty(flow, row, amount, ball_id=None, suffix='relief'):
    event_id = row['id']+'-'+suffix
    existing=next((event for event in flow['sequence'] if event['id']==event_id),None)
    if existing:
        existing.update(active=True,amount=amount)
        return
    flow['sequence'].append(dict(kind='penalty', id=event_id, amount=amount,
                                 active=True, incident_id=row['id'],
                                 ball_id=ball_id or row['ball_id']))
    row['penalty_ids'].append(event_id)


def close_incident(flow, row):
    row['phase'] = 'closed'
    row['completed_sequence_count']=len(flow['sequence'])
    flow['pending'] = None


def rules_for(state):
    _, course, hole = scope(state)
    configured = state['journey'].get('local_rules', {})
    return {**configured.get(canonical((scope(state)[0], course, 'all')), {}),
            **configured.get(canonical((scope(state)[0], course, hole)), {})}


def config(state, event, text):
    match = re.fullmatch(r'(?:本场|本洞)(?:采用|启用|关闭)(?:当地规则)?(E-5|E5|B-3|B3|指定抛球区)', text, re.I)
    if not match:
        return None
    course = scope(state)[1]
    area = 'all' if text.startswith('本场') else scope(state)[2]
    key = match[1].upper().replace('-', '')
    key = {'E5':'e5', 'B3':'b3', '指定抛球区':'dropping_zone'}[key]
    row = state['journey'].setdefault('local_rules', {}).setdefault(canonical((scope(state)[0], course, area)), {})
    row[key] = '关闭' not in text
    row['event_id'] = event['event_id']
    if key == 'b3':
        return '已记录本场确认采用的 B-3 适用范围。该范围内可按罚杆区规则打暂定球；找到原球时还可选择打原球或继续该暂定球。'
    return '已记录'+('关闭' if '关闭' in text else '采用')+match[1]+'及其适用范围。'


def choices(state):
    flow = current(state)
    row = pending(flow) if flow else None
    if not row:
        return None
    phase = row['phase']
    if phase=='identify':
        return ['确认是我的球','不是我的球']
    if phase == 'water_color':
        return ['红桩', '黄桩', '桩色不清楚', '原球可以打']
    if phase == 'water_option':
        options = ['原球可以打', '回上一杆位置', '向后延线抛球']
        if row.get('from_penalty_area'):
            options.append('回最后一次罚杆区外位置')
        if row.get('color') == 'red':
            options.append('侧向两杆范围抛球')
        if rules_for(state).get('dropping_zone'):
            options.append('使用指定抛球区')
        return options
    if phase == 'entry_point':
        return ['已确认最后越界点', '越界点不清楚']
    if phase in ('drop', 'redrop', 'place'):
        return ['已在合法位置抛球', '抛球停在救济区外', '抛球方式不对', '就在这里完成救济']
    if phase == 'drop_result':
        return ['球停在救济区内', '抛球停在救济区外']
    if phase == 'place_result':
        return ['已在第二次落地点放置', '放置后球停不住']
    if phase == 'search':
        return ['开始找球', '暂定球已打', '球在界内', '确认出界', '确认下水', '三分钟没找到']
    if phase == 'water_certainty':
        return ['确认下水', '也可能在长草里', '只可能进罚杆区']
    if phase == 'replay':
        return ['已回原位', '已按当地规则E-5抛球']+(['回最后一次罚杆区外位置','改按罚杆区向后延线'] if row.get('from_penalty_area') else [])
    if phase == 'b3_found':
        return ['打原球', '继续罚杆区暂定球']
    return None


def invalidate_score(state, hole):
    """Invalidate a stale score proposal after changing its underlying penalties."""
    session = state.get('session', {})
    draft = session.get('draft')
    if draft and draft.get('hole') == hole:
        draft.pop('penalties', None)
        draft.pop('penalties_explicit', None)
        draft['awaiting'] = 'penalties'
        patch = state.get('patches', {}).get(session.get('pending_patch'))
        if patch and patch.get('status') != 'committed':
            patch['status'] = 'invalidated'
        session['pending_patch'] = None
        qid = session.get('question_id')
        if qid in state.get('questions', {}):
            state['questions'][qid]['status'] = 'invalidated'
        session['question_id'] = None
    # Preserve a committed total until the player corrects it, but mark its
    # penalty fact and its putt inference as requiring reconfirmation.
    total=fact_value(state,f'holes.{hole}.total')
    if type(total) is int and not draft:
        putts=fact_value(state,f'holes.{hole}.putts')
        source=state['facts'][f'holes.{hole}.total']
        session['draft']=dict(hole=hole,total=total,putts=putts,awaiting='penalties',
                              evidence_ids=list(source.get('evidence_ids',[])))
        session['pending_patch']=None
        source.update(status='unknown',valid=False)
    fact = state.get('facts', {}).get(f'holes.{hole}.penalties')
    if fact:
        fact.update(status='unknown', valid=False)
    return bool(draft and draft.get('hole') == hole or fact)


def discard_descendants(flow, ball_id):
    for ball in flow['balls'].values():
        if ball.get('parent') == ball_id:
            ball['status'] = 'discarded'
            discard_descendants(flow, ball['id'])


def correction(state, flow, event, text):
    match = re.fullmatch(r'(?:更正第(\d+)次事故[，,]?)?(撤销上次罚杆|撤销刚才的罚杆|刚才看错了原球在界内|刚才看错了，原球在界内|实际是红桩区|实际是黄桩区)', text)
    if not match:
        return None
    candidates=flow['incidents'] if match[1] else [row for row in flow['incidents'] if row['status']!='cancelled']
    index=int(match[1])-1 if match[1] else len(candidates)-1
    if index < 0 or index >= len(candidates):
        return '当前没有对应的事故可更正。'
    row = candidates[index]
    if row['status']=='cancelled':
        return '这次事故已经撤销。'
    record_change(row, event)
    # A late discovery alone cannot revive an original ball already replaced
    # under the rules. Explicitly correcting a previous report is a data correction.
    row['status'] = 'cancelled'
    for item in flow['sequence']:
        if item.get('incident_id') == row['id']:
            item['active'] = False
    discard_descendants(flow, row['ball_id'])
    flow['balls'][row['ball_id']].update(status='in_play',inside_penalty_area=False)
    flow['active_ball'] = row['ball_id']
    close_incident(flow, row)
    stale = invalidate_score(state, flow['scope'][2])
    if '实际是' in text:
        row.update(status='active', cause='water', phase='water_option',
                   color='red' if '红' in text else 'yellow', penalty_ids=[],
                   provisional_ids=[], drop_count=0, option=None)
        flow['pending'] = row['id']
        return '已更正为'+('红桩' if row['color']=='red' else '黄桩')+'罚杆区，原先罚杆和暂定球记录已重算。'+water_options(state, row)
    return '已撤销这次判断及其罚杆，相关暂定球作废，原球恢复。'+('这洞成绩需要重新确认。' if stale else '')


def water_options(state, row):
    text = '可原位打原球；采取救济罚一杆，可回上一杆位置或向后延线抛球。'
    if row.get('color') == 'red':
        text += '红桩也可从最后越界点两杆范围内侧向抛球，不更靠洞。'
    elif row.get('color') == 'yellow':
        text += '黄桩按回原位或向后延线处理。'
    if rules_for(state).get('dropping_zone'):
        text += '本场指定抛球区也可选。'
    return text+'你选哪种处理？'


def provisional(state, flow, row, event, now, club=None):
    parent_id = flow['active_ball']
    parent = flow['balls'][parent_id]
    if parent['status'] != 'provisional':
        parent_id = row['ball_id']
    ball_id = event['event_id']+'-ball'
    parent_stroke=last_stroke(flow,parent_id)
    origin=row.get('provisional_origin') or (parent_stroke or {}).get('origin') or row.get('origin') or position(state,now)
    flow['balls'][ball_id] = dict(id=ball_id, parent=parent_id, status='provisional',
                                 origin=origin, local_b3=bool(row.get('local_b3')))
    # Penalty precedes the provisional stroke, but is counted only if this ball is live.
    add_penalty(flow, row, 1, ball_id, suffix=ball_id)
    add_stroke(flow, event['event_id']+'-stroke', ball_id, club, origin)
    row['provisional_ids'].append(ball_id)
    flow['active_ball'] = ball_id
    row['phase'] = 'search'
    row['awaiting_provisional_position'] = ball_id
    row['awaiting_provisional_club']=ball_id if not club else None
    return '暂定球已登记，用杆'+(club or '未知')+'，先保留为暂定记录。'+('这颗暂定球用的什么杆？' if not club else '')+'请更新暂定球落点，再确认原球。找球从开始寻找起最多三分钟。'


def promote(flow, row):
    active_id = flow['active_ball']
    # All ancestors of the latest provisional contribute to the played sequence.
    cursor = active_id
    while cursor:
        ball = flow['balls'][cursor]
        if ball['status'] == 'provisional':
            ball['status'] = 'in_play' if cursor == active_id else 'superseded'
        cursor = ball.get('parent')
    flow['balls'][row['ball_id']]['status'] = row['cause']
    row.update(phase='live_position', promoted=True)
    flow['pending'] = row['id']


def confirm_outcome(state, flow, row, cause):
    if row.get('promoted'):
        return '原球已退出使用，继续处理当前使用中球。若这颗球又出界或下水，请明确报告“暂定球出界”或“暂定球下水”。'
    if row['cause'] == cause and row['phase'] in ('replay', 'water_color', 'water_option', 'live_position'):
        return '这个结果已登记。'+('请更新暂定球的位置。' if row['phase']=='live_position' else '继续选择处理方式。')
    row['cause'] = cause
    row['status'] = 'active'
    if cause=='water' and row.get('local_b3') and row['provisional_ids']:
        promote(flow,row)
        return '本场 B-3 下原球已确认或几乎确定停在罚杆区，罚杆区暂定球成为使用中球。请更新该球位置。'
    if cause == 'water':
        if row['provisional_ids'] and not row.get('local_b3'):
            discard_descendants(flow, row['ball_id'])
            flow['active_ball'] = row['ball_id']
        row['phase'] = 'water_color'
        return '已确认或几乎确定球停在罚杆区。'+('普通暂定球作废。' if row['provisional_ids'] and not row.get('local_b3') else '')+'现场是红桩还是黄桩？原球可以打时也可直接选择。'
    if row['provisional_ids']:
        promote(flow, row)
        return '原球'+('出界' if cause=='ob' else '遗失')+'，暂定球成为使用中球，按球的身份计入击球与罚杆。请更新到暂定球的位置。'
    row['phase'] = 'replay'
    add_penalty(flow, row, 1)
    from ball_outcome import REPLAY
    return REPLAY


def finish_relief(state, flow, row, event, now, same_position=False):
    if row.get('option') is None:
        row['option'] = 'stroke_distance' if row['cause'] in ('ob','lost') else 'user_confirmed'
    amount=row.get('relief_penalty_amount',2 if row['option']=='e5' else 1)
    add_penalty(flow,row,amount,suffix='rule17-2' if row.get('relief_penalty_amount') else 'relief')
    row.update(phase='relief_position', explicit_position=same_position)
    if same_position:
        accept_position(state, flow, row, event, now, position(state, now) or fact_value(state,'context.device_position'))
        return '已按你确认的位置完成救济，罚'+str(amount)+'杆。下一杆从这里打。'
    return '已登记'+str(amount)+'杆罚杆。请更新处理后的球位；若就在当前位置，可说“就在这里完成救济”。'


def accept_position(state, flow, row, event, now, point):
    if not point:
        row['phase'] = 'relief_position'
        return False
    from shot_links import add
    pos = fresh_position(state, now)
    if pos:
        # Establish a new origin without interpreting relocation as a stroke.
        state['journey']['shot_location_candidates'] = [
            candidate for candidate in state['journey'].get('shot_location_candidates', [])
            if [candidate['round_id'], candidate['course'], candidate['hole']] != flow['scope']]
        add(state, point, pos['evidence_ids'], 'rules_relief_position')
    if row['phase'] == 'live_position':
        stroke = last_stroke(flow)
        if stroke and not stroke.get('landing'):
            stroke['landing'] = copy.deepcopy(point)
            stroke['distance_m'] = haversine(stroke['origin'], point) if stroke.get('origin') else None
    else:
        new_id = event['event_id']+'-relief-ball'
        flow['balls'][new_id] = dict(id=new_id, parent=row['ball_id'], status='in_play', origin=copy.deepcopy(point))
        flow['active_ball'] = new_id
    row['relief_point'] = copy.deepcopy(point)
    close_incident(flow, row)
    state['journey'].pop('tee_club_fallback', None)
    state['journey'].pop('simulated_club_choice', None)
    return True


def on_position(state, event, now):
    flow = current(state)
    row = pending(flow) if flow else None
    if not row:
        return None
    if event.get('data',{}).get('simulation_refresh'):
        return ''
    point = position(state, now)
    pos = fresh_position(state, now)
    if not point or not pos or not any(state['evidence'][eid].get('observed_at') == event['observed_at']
                                       for eid in pos['evidence_ids']):
        return None
    if row.get('awaiting_provisional_position'):
        ball_id = row.pop('awaiting_provisional_position')
        stroke = last_stroke(flow, ball_id)
        if stroke:
            stroke.update(landing=point, distance_m=haversine(stroke['origin'], point)
                          if stroke.get('origin') else None)
        if row.get('promoted'):
            accept_position(state,flow,row,event,now,point)
            return '已更新使用中球落点，杆序和罚杆已计入。'
        return '已更新暂定球落点，保留其独立记录。原球确认在界内、出界、下水，还是暂时没看到？'
    if row['phase'] in ('live_position', 'relief_position'):
        was_provisional_water=row.get('provisional_water')==flow['active_ball']
        accept_position(state, flow, row, event, now, point)
        if was_provisional_water:
            water_incident=incident(state,flow,event,now,'water')
            water_incident['phase']='water_color'
            return '已更新使用中球位置。这颗球还需处理罚杆区救济，现场是红桩还是黄桩？'
        return '已更新处理后的球位，移动未计作击球。可以再问我这杆怎么打。'
    return ''


def on_record(state, event, now):
    flow = initialize(state)
    record = next((row for row in reversed(state['journey'].get('confirmed_shot_distances', []))
                   if row['id'] == event['event_id']), None)
    if not record:
        return
    start, end = record['endpoints']
    existing=next((item for item in flow['sequence'] if item.get('pair_ids')==record['pair_ids']),None)
    if existing:
        existing.update(club=record.get('club') or existing.get('club'),landing=end['point'],
                        distance_m=record['total_horizontal_m'])
        return
    add_stroke(flow, record['id'], flow['active_ball'], record.get('club'),
               start['point'], end['point'], record['pair_ids'])
    record['ball_id'] = flow['active_ball']
    from lie_position import infer
    label=(infer(state,now) or {}).get('label')
    if label in ('球道','长草','沙坑','果岭','发球台'):
        flow['balls'][flow['active_ball']]['inside_penalty_area']=False


def correct_landing(state, event, now):
    flow=current(state)
    if not flow:
        return
    stroke=last_stroke(flow)
    point=position(state,now)
    if not stroke or not point:
        return
    from shot_links import pair
    endpoints=pair(state)
    stroke['landing']=copy.deepcopy(point)
    stroke['distance_m']=haversine(stroke['origin'],point) if stroke.get('origin') else None
    if len(endpoints)==2:
        stroke['pair_ids']=[row['id'] for row in endpoints]


def map_landing(state, event, now):
    from ball_outcome import simulated_risk
    risk = simulated_risk(state, event['data'])
    if not risk:
        return None
    flow = initialize(state)
    row = incident(state, flow, event, now)
    row['phase'] = 'water_certainty' if risk=='下水' else 'search'
    return '模拟落点提示可能'+risk+'，请现场确认。'+('球整体是否在界外？' if risk=='出界' else '是否已确认或几乎确定球停在罚杆区？')


def blocking(state):
    flow = current(state)
    return bool(flow and flow.get('pending'))


def handle(state, event, text, now):
    flow = initialize(state)
    clean = re.sub(r'[，,。！!？?\s]', '', text).lower()
    if re.fullmatch(r'(?:原球|球|这杆|刚才)?(?:确定|确认|已经|确实)?(?:是)?(?:出界|ob)(?:了)?',clean):
        clean='确认出界'
    elif re.fullmatch(r'(?:原球|球|这杆|刚才)?(?:确定|确认|已经|几乎确定)?(?:是)?(?:下水|进水|在罚杆区)(?:了)?',clean):
        clean='确认下水'
    elif not clean.startswith('暂定球') and re.search(r'(?:又|再次)(?:出界|ob)(?:了)?$',clean):
        clean='这杆又出界了'
    elif not clean.startswith('暂定球') and re.search(r'(?:又|再次)(?:下水|进水)(?:了)?$',clean):
        clean='这杆又下水了'
    if clean in ('找了三分钟没找到','三分钟还是没找到','找球超过三分钟'):
        clean='三分钟没找到'
    reply = config(state, event, text)
    if reply is not None:
        return reply
    reply = correction(state, flow, event, text)
    if reply is not None:
        return reply
    row=pending(flow)
    latest=flow['incidents'][-1] if flow['incidents'] else None
    if not row and latest and latest.get('promoted') and re.search(r'找到(?:了)?原球',clean):
        return '原球已退出使用，继续打当前使用中球。若先前报告有误，请明确更正该次事故。'
    if row and row.get('awaiting_provisional_club'):
        from club_selection import selection
        club=selection(text,hybrid=True,expanded=True)
        if club:
            stroke=last_stroke(flow,row['awaiting_provisional_club'])
            if stroke:stroke['club']=club['label']
            row['awaiting_provisional_club']=None
            return '已记录这颗暂定球实际用'+club['label']+'。'
    actual=re.fullmatch(r'(?:刚才|上一杆)?(?:实际)?(?:用了|用的是|用的)(.+)',clean)
    if actual:
        from club_selection import selection
        club=selection(actual[1],hybrid=True,expanded=True)
        stroke=last_stroke(flow)
        if club and stroke:
            stroke['club']=club['label']
            return '已更新上一杆实际用杆为'+club['label']+'。'
    original_club=re.fullmatch(r'原球(?:用|用的是)(.+)',clean)
    if original_club and flow['incidents']:
        from club_selection import selection
        club=selection(original_club[1],hybrid=True,expanded=True)
        target=next((stroke for stroke in flow['sequence'] if stroke['id']==flow['incidents'][-1]['shot_id']),None)
        if club and target:
            target['club']=club['label']
            return '已更新原球实际用杆为'+club['label']+'。'
    if not row and latest and clean in ('暂定球按e-5抛球','暂定球按e5抛球','已经从错误位置打了','从错误位置击球了'):
        row=latest
    active_ball=flow['balls'][flow['active_ball']]
    if not row and clean.startswith('暂定球') and active_ball['status']=='in_play':
        active_is_provisional=any(flow['active_ball'] in item['provisional_ids'] for item in flow['incidents'])
        if not active_is_provisional and re.fullmatch(r'暂定球(?:也|又)?(?:确认)?(?:出界|ob|下水|遗失)(?:了)?',clean):
            return '当前使用的是原球或救济后的替代球；已作废暂定球的后续结果不计入本洞。请确认你报告的是哪颗球。'
        if re.fullmatch(r'暂定球(?:也|又)?(?:确认)?(?:出界|ob|下水|遗失)(?:了)?',clean):
            cause='water' if '水' in clean else 'lost' if '遗失' in clean else 'ob'
            row=incident(state,flow,event,now,cause)
            return confirm_outcome(state,flow,row,cause)
    # A score reply continues through the score reducer even during an incident.
    if state.get('session', {}).get('draft') and re.fullmatch(r'\d+(?:推|罚杆|罚)?|[一二两三四五六七八九十]+(?:推|罚杆|罚)?|确认|确认记录', clean):
        return None
    if re.search(r'白桩附近|压线|碰到白线|一部分在界内', clean):
        row = row or incident(state, flow, event, now)
        return '球整体在边界外才是 OB，任何一部分仍在界内则在界内。请现场确认球的整体位置，可说“确认出界”或“球在界内”。'
    if clean in ('开始找球','开始寻找','开始寻找原球'):
        row = row or incident(state, flow, event, now)
        if (flow.get('search') or {}).get('incident_id')==row['id']:
            return '已保留最初开始寻找的时间，重复报告不会重置三分钟。'
        flow['search'] = dict(started_at=now, incident_id=row['id'])
        return '已记录开始找原球的时间，最多三分钟。找到时请确认球的身份。'
    if clean in ('找了多久','找球时间'):
        search = flow.get('search')
        if not search:
            return '还未记录找球起点，到开始寻找时说“开始找球”。'
        elapsed = max(0, int(now-search['started_at']))
        return '已找球约'+str(elapsed)+'秒。'+('已到三分钟，请确认是否找到原球。' if elapsed>=180 else '')
    if row and row['phase']=='b3_found' and clean in ('打原球','继续罚杆区暂定球'):
        if clean=='打原球':
            discard_descendants(flow,row['ball_id'])
            flow['active_ball']=row['ball_id']
            close_incident(flow,row)
            return '已选择打原球，罚杆区暂定球及其相关罚杆作废。'
        promote(flow,row)
        return '已按本场 B-3 选择继续罚杆区暂定球，请确认该球位置。'
    if clean in ('找到一个球不确定是不是我的','找到球还没确认身份'):
        row=row or incident(state,flow,event,now)
        search=flow.get('search')
        if search and search['incident_id']==row['id'] and now-search['started_at']>=180:
            return confirm_outcome(state,flow,row,'lost')
        row.update(phase='identify',found_at=now)
        return '请及时辨认是否为原球，允许合理的辨认及走到球旁时间。可说“确认是我的球”或“不是我的球”。'
    if row and row['phase']=='identify' and clean=='不是我的球':
        row.pop('found_at',None)
        row['phase']='search'
        return '继续找原球，找球时间从最初开始寻找计算。'
    if row and clean=='确认是我的球':
        clean='找到原球'
    if row and clean=='找到原球在罚杆区':
        search=flow.get('search')
        if search and search['incident_id']==row['id'] and now-search['started_at']>=180 and not row.get('found_at'):
            return confirm_outcome(state,flow,row,'water' if row.get('local_b3') else 'lost')
        if row.get('local_b3'):
            row['phase']='b3_found'
            return '已找到原球在罚杆区，可选打原球或继续罚杆区暂定球。'
        return confirm_outcome(state,flow,row,'water')
    surface=re.fullmatch(r'(原球|暂定球)?(?:在|落在)?(球道|长草|沙坑|果岭)(?:中间|中央|左侧|右侧|左边|右边|里|上)?(?:了)?',clean)
    if row and surface:
        if row['cause']=='water' and not row.get('promoted'):
            return '请确认球是否仍在罚杆区内。可以说“原球可以打”，或继续选择罚杆区救济；若之前判断有误，请明确更正。'
        if row['phase']=='water_certainty':
            return '球在罚杆区内，还是在区外长草中？可说“确认下水”或“原球在罚杆区外”。'
        if not surface[1] and row['provisional_ids']:
            return '你说的是原球还是暂定球？可以说“原球在球道中间”或“暂定球在球道中间”。'
        if surface[1]=='暂定球' and row['provisional_ids']:
            flow['balls'][flow['active_ball']]['reported_lie']=surface[2]
            return '已记录'+('使用中球' if row.get('promoted') else '暂定球')+'在'+surface[2]+'。'+('请更新实际球位。' if row.get('promoted') else '继续确认原球的结果。')
        clean='找到原球'
    if clean=='原球在罚杆区外':
        clean='找到原球'
    found = bool(re.fullmatch(r'(?:没出界|没ob|没下水|球弹回来了|(?:找到|找到了)(?:原球)?|(?:球|原球)?在界内)(?:在)?(?:球道|长草|沙坑)?(?:里|中间)?', clean))
    if found and row:
        search = flow.get('search')
        if row.get('promoted') or (search and search['incident_id']==row['id'] and now-search['started_at']>=180 and not row.get('found_at')):
            if not row.get('promoted'):
                return confirm_outcome(state,flow,row,'lost')
            return '原球已失去使用中球身份，继续使用替代球。若刚才报告有误，可说“刚才看错了，原球在界内”更正记录。'
        discard_descendants(flow,row['ball_id'])
        flow['active_ball']=row['ball_id']
        flow['balls'][row['ball_id']]['status']='in_play'
        close_incident(flow,row)
        return '继续打原球，暂定球及其相关击球、罚杆作废。'
    if clean in ('原球可以打','原位打','打原球') and row and row['cause']=='water':
        if row.get('no_play_zone'):
            return '这里已确认是禁止打球区，需要采取救济。'+water_options(state,row)
        flow['active_ball']=row['ball_id']
        flow['balls'][row['ball_id']].update(status='in_play',inside_penalty_area=True)
        discard_descendants(flow,row['ball_id'])
        close_incident(flow,row)
        return '按原位打原球处理，未增加救济罚杆。可以直接问这杆怎么打。'
    if '禁止打球区' in clean and row:
        row['no_play_zone']=True
        return '已记录禁止打球区，需要救济。'+water_options(state,row)
    if clean in ('红桩','红桩区','黄桩','黄桩区','桩色不清楚') and row and (row['cause']=='water' or row.get('local_b3')):
        row['color']='red' if '红' in clean else 'yellow' if '黄' in clean else 'unknown'
        row['phase']='water_option'
        return water_options(state,row)
    if row and row.get('local_b3') and clean in ('B-3向后延线暂定球'.lower(),'b3向后延线暂定球','b3侧向暂定球','b3指定抛球区暂定球'):
        if '侧向' in clean and row.get('color')!='red':
            return '请先报“红桩”，确认后再选择 B-3 侧向暂定球。'
        if '抛球区' in clean and not rules_for(state).get('dropping_zone'):
            return '请先确认本洞采用指定抛球区。'
        row['provisional_option']='lateral' if '侧向' in clean else 'dropping_zone' if '抛球区' in clean else 'back_on_line'
        row['phase']='b3_drop'
        return '已选 B-3 罚杆区暂定球救济方式。请现场确认最后越界点、正确抛球且停在规定救济区，再报“B3暂定球已抛球”。'
    if row and clean=='b3暂定球已抛球' and row['phase']=='b3_drop':
        row['provisional_origin']=position(state,now) or fact_value(state,'context.device_position')
        row['phase']='search'
        return '已记录罚杆区暂定球的起点。击球前声明暂定球，打完单独报告用杆。'
    if row and row.get('from_penalty_area') and clean in ('回最后一次罚杆区外位置','改按罚杆区向后延线'):
        for item in flow['sequence']:
            if item.get('incident_id')==row['id']:
                item['active']=False
        row['relief_penalty_amount']=1 if row['cause']=='water' else 2
        add_penalty(flow,row,row['relief_penalty_amount'],suffix='rule17-2')
        if clean=='回最后一次罚杆区外位置':
            row.update(option='last_outside',phase='replay')
            return '按规则17.2回最后一次罚杆区外击球位置，计'+str(row['relief_penalty_amount'])+'杆罚杆。按规则14.6回该位置重打，完成后更新球位。'
        row.update(option='back_on_line',phase='entry_point')
        return '从罚杆区打出的球在区外出界或遗失，可直接转罚杆区后延线救济，合计两杆罚杆。请确认最后越过原罚杆区边界的点。'
    if row and row['cause']=='water' and clean in ('回上一杆位置','回原位','向后延线抛球','侧向两杆范围抛球','使用指定抛球区'):
        option={'回上一杆位置':'stroke_distance','回原位':'stroke_distance','向后延线抛球':'back_on_line',
                '侧向两杆范围抛球':'lateral','使用指定抛球区':'dropping_zone'}[clean]
        if option=='lateral' and row.get('color')!='red':
            return '侧向两杆救济需要确认红桩。请确认桩色，或选择回上一杆位置、向后延线。'
        if option=='dropping_zone' and not rules_for(state).get('dropping_zone'):
            return '先确认本洞采用指定抛球区，可说“本洞采用指定抛球区”。'
        row['option']=option
        if option in ('back_on_line','lateral'):
            row['phase']='entry_point'
            return '请确认球最后越过罚杆区边界的点。向后延线以球洞和该点连线后退；侧向救济以该点为基准，两杆范围内且不更靠洞。'
        row['phase']='drop' if option=='dropping_zone' else 'replay'
        return '已选择'+clean+'。'+drop_instruction(row)
    if clean in ('已确认最后越界点','越界点已确认') and row and row['phase']=='entry_point':
        row['entry_confirmed']=True
        row['phase']='drop'
        return '已记录你确认的最后越界点。'+drop_instruction(row)
    if clean in ('越界点不清楚','没看到最后越界点') and row:
        return '结合最后观察位置和现场证据合理估计最后越界点；无法合理估计时，可选择回上一杆位置。'
    if row and clean in ('已回原位','已在合法位置抛球','已抛球','就在这里抛球','就在这里完成救济'):
        if row['phase']=='replay':
            return finish_relief(state,flow,row,event,now,same_position=clean=='就在这里完成救济')
        if row['phase'] in ('relief_position','live_position') and clean in ('就在这里完成救济','就在这里抛球'):
            if not accept_position(state,flow,row,event,now,position(state,now) or fact_value(state,'context.device_position')):
                return '已确认在当前位置完成，请更新定位以建立下一杆起点。'
            return '已确认当前位置，下一杆从这里打。'
        if row['cause']=='water' and row['phase'] in ('water_color','water_option'):
            row.update(option='user_confirmed',phase='drop')
        if row['phase'] in ('drop','redrop','place'):
            if clean=='就在这里完成救济':
                return finish_relief(state,flow,row,event,now,same_position=True)
            row['phase']='drop_result'
            return '抛球后球是否停在救济区内？'
    if row and clean in ('球停在救济区内','抛球在区内'):
        if row['phase'] in ('drop','redrop','drop_result'):
            return finish_relief(state,flow,row,event,now)
    if row and clean in ('抛球方式不对','抛球高度不对'):
        row['phase']='redrop'
        return '先纠正抛球方式，由本人从膝盖高度垂直抛球。方式不对的抛球不计入两次正确抛球。'
    if row and clean in ('抛球停在救济区外','抛球滚出去了','第二次也滚出去了'):
        if row['phase'] not in ('drop','redrop','drop_result','place'):
            return '请先选择救济方式，再记录抛球结果。'
        row['drop_count']+=1
        if row['drop_count']==1:
            row['phase']='redrop'
            return '第一次正确抛球停在救济区外，再正确抛一次，无额外罚杆。'
        row['phase']='place_result'
        return '两次正确抛球都停在区外，在第二次抛球首次触地点放置球。'
    if row and clean in ('已在第二次落地点放置','已放置'):
        if row['phase'] in ('place_result','place'):
            return finish_relief(state,flow,row,event,now)
    if row and clean=='放置后球停不住':
        row['phase']='place'
        return '先在同一点再放一次；仍停不住时，找不更靠洞、符合规则14.2e区域限制的最近能停住点放置。完成后说“已放置”。'
    if row and clean in ('暂定球按e-5抛球','暂定球按e5抛球'):
        ball=flow['balls'][flow['active_ball']]
        if not rules_for(state).get('e5'):
            return '先确认本场采用 E-5。'
        if ball.get('reported_outcome') not in ('ob','lost'):
            return '先确认这颗暂定球本身已出界或遗失，才能评估对它使用 E-5。'
        if not row.get('promoted'):
            return '先确认原球的结果，再处理这颗暂定球的 E-5 救济。'
        close_incident(flow,row)
        next_row=incident(state,flow,event,now,ball['reported_outcome'])
        next_row.update(option='e5',phase='relief_position')
        add_penalty(flow,next_row,2,suffix='e5')
        return '已对这颗出界或遗失的暂定球采用 E-5，另加两杆罚杆。请更新合法抛球位置。'
    if row and clean in ('已按当地规则e-5抛球','已按当地规则e5抛球'):
        if row.get('option')=='e5':
            return 'E-5 两杆罚杆已登记，请确认合法抛球位置。'
        if not rules_for(state).get('e5'):
            return '本场尚未确认采用 E-5。可先确认当地规则，或按一杆加距离回原位。'
        if row['cause'] not in ('ob','lost') or row['provisional_ids']:
            return '这颗原球当前不适用 E-5。已打暂定球后，应先处理暂定球身份。'
        for item in flow['sequence']:
            if item.get('incident_id')==row['id']:
                item['active']=False
        row['option']='e5'
        # Replace the earlier one-stroke option using a distinct immutable ID.
        add_penalty(flow,row,2,suffix='e5')
        row['phase']='relief_position'
        return ('已按 E-5 登记两杆罚杆。原球参考点取预计遗失落点或最后出界点；球道参考点取最近且不更靠洞的球道点。'
                '救济区在球洞分别连到这两点的线之间，原球线外侧及球道线向球道侧各可延两杆范围，必须在一般区域且不比原球参考点更靠洞。确认后更新球位。')
    if clean in ('没声明暂定球就打了','没有声明暂定球就打了'):
        row=row or incident(state,flow,event,now)
        reply=provisional(state,flow,row,event,now)
        row['cause']='lost'
        promote(flow,row)
        return '未明确声明暂定球，这颗球按一杆加距离成为使用中球，原球退出使用。请更新该球位置。'
    if row and clean in ('暂定球已打到原球预计位置附近','还没比原球预计位置更靠洞'):
        return '可继续打暂定球，但在比原球预计位置更靠洞处击球会使其成为使用中球。'
    if row and clean in ('已经从错误位置打了','从错误位置击球了'):
        row['phase']='wrong_place'
        row['wrong_place_played']=True
        return '需核对比杆赛或比洞赛，以及是否严重违规。比杆赛通常涉及一般处罚两杆，严重违规须及时纠正；请现场请裁判确认，明确处罚和补打后再记分。'
    if row and clean in ('裁判确认错误位置罚两杆','错误位置罚两杆'):
        add_penalty(flow,row,2,suffix='wrong-place')
        row['phase']='relief_position'
        invalidate_score(state,flow['scope'][2])
        return '已按现场确认另记两杆处罚。请确认已完成要求的纠正并更新球位。'
    if row and clean=='击球前发现抛错位置':
        row['phase']='drop'
        return '击球前可先纠正错误位置，按原救济规则重新完成；先前未生效的错误抛球不另加罚杆。'
    if '暂定球' in clean and re.search(r'可以|能不能|要不要|先打|打一个',clean):
        if not row:
            return '原球可能出界或在罚杆区外遗失时可先打暂定球，请先告诉我原球的去向。'
        if row.get('only_water') and not rules_for(state).get('b3') or row['cause']=='water' and not row.get('local_b3'):
            return '只可能或已确认进罚杆区时通常不打暂定球，先核实原球或选择罚杆区救济。'
        from ball_outcome import PROVISIONAL
        return PROVISIONAL
    provisional_match=re.fullmatch(r'(?:第二颗|再一颗)?暂定球(?:已|已经)?打(?:了)?(?:用|换了)?(.*)',clean)
    if provisional_match:
        row=row or incident(state,flow,event,now)
        active=flow['balls'][flow['active_ball']]
        if (active['status']=='provisional' and not active.get('reported_outcome')
                and not clean.startswith(('第二颗','再一颗'))):
            return '这颗暂定球已登记。若又击球可说“暂定球又打了一杆”；若再打另一颗，请说“第二颗暂定球已打”。'
        if (row['cause']=='water' or row.get('only_water')) and not rules_for(state).get('b3'):
            provisional(state,flow,row,event,now)
            row['cause']='lost'
            promote(flow,row)
            return '只可能或已确认进罚杆区时通常不打暂定球。你已打出的这颗球按一杆加距离成为使用中球，原球退出使用，请更新球位。'
        if row.get('only_water'):
            row['local_b3']=True
        from club_selection import selection
        club_text=provisional_match[1]
        club=selection(club_text,hybrid=True,expanded=True) if club_text else None
        # Independent club for every provisional; omitted club stays unknown.
        return provisional(state,flow,row,event,now,club['label'] if club else None)
    club_match=re.fullmatch(r'暂定球(?:换了|用|用的是)(.+)',clean)
    if club_match and row and row['provisional_ids']:
        from club_selection import selection
        club=selection(club_match[1],hybrid=True,expanded=True)
        if club:
            last_stroke(flow)['club']=club['label']
            return '已更新这颗暂定球用杆为'+club['label']+'。'
    if row and clean in ('暂定球又打了一杆','暂定球继续打','暂定球已经从原球预计位置更靠洞处击球'):
        ball_id=flow['active_ball']
        ball=flow['balls'][ball_id]
        if ball['status']!='provisional':
            return '这颗球已是使用中球，可更新实际落点和用杆。'
        if '更靠洞' in clean:
            row['cause']='lost'
            promote(flow,row)
        origin=last_stroke(flow).get('landing') or position(state,now)
        add_stroke(flow,event['event_id']+'-stroke',ball_id,None,origin)
        row['awaiting_provisional_position']=ball_id
        return '已登记这颗暂定球的后续击球。'+('它已成为使用中球，原球之后找到也不能继续使用。' if row.get('promoted') else '尚未确认更靠洞击球时，继续保留暂定身份。')+'请更新该球落点和用杆。'
    if row and re.fullmatch(r'暂定球(?:也|又)?(?:确认)?(?:出界|ob|下水|遗失)(?:了)?',clean):
        active_ball=flow['active_ball']
        if '下水' in clean:
            # Its penalty remains conditional until the original is resolved.
            row['provisional_water']=active_ball
            return '这颗暂定球疑似停在罚杆区，先确认原球身份；原球可继续时暂定球作废，原球出界或遗失时再处理这颗球的罚杆区救济。'
        flow['balls'][active_ball]['reported_outcome']='ob' if ('出界' in clean or 'ob' in clean) else 'lost'
        return '已记录这颗暂定球也出界或遗失。可在它上一杆位置再打第二颗暂定球，击球前声明，并单独报告用杆。'
    if not row and latest and latest.get('completed_sequence_count')==len(flow['sequence']) and clean in ('确认出界','确认下水','确认遗失'):
        expected={'确认出界':'ob','确认下水':'water','确认遗失':'lost'}[clean]
        if latest['cause']==expected and latest['status']=='active':
            return '这个结果已登记。新一杆再次出现情况时可说“这杆又出界了”或“这杆又下水了”。'
    if clean in ('这杆又出界了','这杆又下水了','又出界了','又下水了'):
        row=row or incident(state,flow,event,now)
        return confirm_outcome(state,flow,row,'water' if '水' in clean else 'ob')
    if re.fullmatch(r'(?:原球|球)?(?:确定|确认|已经|确实)(?:是)?(?:出界|ob)(?:了)?',clean):
        clean='确认出界'
    elif re.fullmatch(r'(?:原球|球)?(?:确定|确认|已经|几乎确定)(?:是)?(?:下水|进水|在罚杆区)(?:了)?',clean):
        clean='确认下水'
    if clean in ('确认出界','出界了','确认ob','确认ob了','确认下水','确认进水','确认遗失','三分钟没找到'):
        row=row or incident(state,flow,event,now)
        cause='water' if '水' in clean else 'lost' if ('遗失' in clean or '三分钟' in clean) else 'ob'
        record_change(row,event)
        if clean=='三分钟没找到' and row.get('only_water') and not row.get('local_b3'):
            return '若已确认或几乎确定停在罚杆区，请按罚杆区处理；仍有可能在区外遗失时才按遗失球处理。'
        return confirm_outcome(state,flow,row,cause)
    if row and clean in ('只可能进罚杆区','只可能下水'):
        row['only_water']=True
        row['phase']='water_certainty'
        if rules_for(state).get('b3'):
            row['local_b3']=True
            return '本洞采用 B-3，可以按其规定先打罚杆区暂定球。'
        return '先核实原球；普通规则下只可能进罚杆区时通常不打暂定球。确认或几乎确定停在区内后可按罚杆区救济。'
    if row and clean in ('也可能在长草里','也可能出界','也可能在罚杆区外遗失'):
        row.update(only_water=False,phase='search')
        from ball_outcome import PROVISIONAL
        return PROVISIONAL
    uncertain=bool(re.search(r'可能|好像|应该|估计|大概|没看到|没找到|找不到|看不清',clean))
    hazard=bool(re.search(r'ob|出界|下水|进水|罚杆区|找不到|没找到|没看到',clean))
    if uncertain and hazard:
        row=row or incident(state,flow,event,now)
        if '水' in clean or '罚杆区' in clean:
            row['phase']='water_certainty'
            return '你看到球停在罚杆区了吗，还是只看到它朝那个方向飞？也可能出界或在区外长草中遗失吗？'
        row['phase']='search'
        from ball_outcome import PROVISIONAL
        return PROVISIONAL
    if row:
        from approach_dialogue import requested
        if requested(text) or clean in ('继续','长草','球道','沙坑','再问一次'):
            options=choices(state)
            return '先处理这颗球。'+('可选择“'+'”“'.join(options)+'”。' if options else '请更新处理后的球位，或确认就在当前位置完成。')
    return None


def drop_instruction(row):
    if row.get('option')=='stroke_distance':
        return '上一杆在发球区可重新架球；一般区域或沙坑按原位置一杆范围抛球，留在原区域或同一沙坑且不更靠洞；上一杆在果岭则放回原位置。'
    if row.get('option')=='back_on_line':
        return ('由本人从膝盖高度垂直抛球，球首先触地的位置必须在球洞与最后越界点的后延线上。'
                '首次触地点形成向各方向一杆范围，球须停在其中、留在首次触地的同一区域且在原罚杆区外，不比最后越界点更靠洞。')
    if row.get('option')=='lateral':
        return '由本人从膝盖高度抛在最后越界点两杆范围内，停在规定救济区且在原罚杆区外，不比越界点更靠洞，并留在首次触地的同一区域。'
    return '由本人从膝盖高度垂直抛球，让球先落在并最终停在当地规则指定的救济区内。'
