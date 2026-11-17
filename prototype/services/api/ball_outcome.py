"""Round-scoped ball outcome dialogue. Map evidence prompts; player reports decide."""
import math
import re

from round_state import canonical
from shot_links import scope

CHECK = '原球确认在界内、出界、下水，还是暂时没看到？'
PROVISIONAL = ('如果原球可能出界或在罚杆区外遗失，可以在上一杆位置打暂定球。'
               '击球前向同组明确说“我打暂定球”，打完可告诉我“暂定球已打”。'
               '若唯一可能是进了罚杆区，通常先核实，不打暂定球。')
REPLAY = ('按一杆加距离处理，罚一杆，回上一杆位置重打；上一杆在发球区可重新架球。'
          '若本场明确采用当地规则 E-5 且这颗原球没有打过暂定球，才可能改用罚两杆的指定救济范围。')
WATER = ('确认或几乎确定球停在罚杆区时，可原位打；如采取救济，罚一杆。'
         '可回上一杆位置，或以球最后越过罚杆区边界的点和球洞连线，向远离球洞方向后退抛球。'
         '红桩还可在最后越界点两支球杆范围内侧向抛球，不更靠洞。只有当地规则指定了抛球区才可使用。')

def current(state):
    return state.get('journey', {}).get('ball_outcomes', {}).get(canonical(scope(state)))

def save(state, event, **changes):
    j = state['journey']
    key = canonical(scope(state))
    entry = j.setdefault('ball_outcomes', {}).setdefault(key, {})
    if entry.get('phase') == 'closed' and changes.get('phase') != 'closed':
        entry.clear()
    if changes.get('phase') in ('placement', 'provisional_live'):
        from round_state import fact_value
        changes['previous_position'] = fact_value(state, 'context.device_position')
    entry.setdefault('incident_id', event['event_id'])
    entry.update(event_id=event['event_id'], observed_at=event['observed_at'], **changes)
    j.setdefault('ball_outcome_history', []).append(dict(entry, scope=list(scope(state))))
    return entry

def reported_penalties(state, hole):
    from ball_rules import penalties
    count=penalties(state,hole)
    if count is not None:return count
    round_id = scope(state)[0]
    rows=[row for row in state.get('journey', {}).get('ball_outcome_history', [])
          if row['scope'][0]==round_id and row['scope'][2]==hole]
    latest={row['incident_id']:row for row in rows}
    attempts=state.get('journey',{}).get('simulation_attempts',{})
    eligible=[]
    legacy=[]
    for row in latest.values():
        since=attempts.get(canonical(row['scope']))
        if not since or row.get('observed_at','')>=since:
            eligible.append(row)
        elif 'observed_at' not in row:
            legacy.append(row)
    # Older demo events have no timestamp. Only the current incident is usable
    # after a restart, rather than summing all earlier test attempts.
    if legacy and not eligible:
        active=(state.get('journey',{}).get('ball_outcomes',{}).get(canonical(legacy[-1]['scope'])) or {})
        if active.get('outcome') in ('ob','lost','water'):
            eligible.append(latest.get(active.get('incident_id'),legacy[-1]))
    return sum(row.get('penalty') or 0 for row in eligible)


def clear_plan(state):
    j = state['journey']
    for key in ('consultation', 'response_context', 'pending_green_followup', 'approach_club_offer', 'tee_route_options'):
        j.pop(key, None)

def choices(state):
    phase = (current(state) or {}).get('phase')
    if phase in ('check', 'search', 'water_check', 'provisional'):
        return (['暂定球已打'] if phase in ('check', 'search') else []) + ['球在界内', '确认出界', '确认下水', '三分钟没找到']
    if phase in ('replay', 'water'):
        return ['已回原位'] + (['已在合法位置抛球', '原球可以打'] if phase == 'water' else [])

def provisional_intent(text):
    return '暂定球' in text and bool(re.search(r'打|要不要|能不能|可以', text))

def handle(state, event, text, now):
    t = re.sub(r'[，,。！!？?\s]', '', text).lower()
    entry = current(state) or {}
    phase = entry.get('phase')
    active = bool(choices(state))
    draft = state.get('session', {}).get('draft') or {}
    if draft.get('awaiting') == 'penalties' and re.fullmatch(r'(?:没有|没)(?:ob|出界)?(?:也)?(?:没|没有)?下水|没有罚杆', t):
        return None
    if re.search(r'^(?:球|原球)?(?:在界内|没出界|没ob|没下水)$|^找到原球(?:在界内)?$|^原球可以打$', t):
        if active:
            if t == '原球可以打' and phase != 'water':
                return '请先确认原球在界内，或报告它的实际去向。'
            had_provisional = entry.get('provisional_played')
            save(state, event, phase='closed', outcome='original', penalty=None)
            return '继续打原球。'+('暂定球作废，相关击球不计分。' if had_provisional else '可以再问我这杆怎么打。')
        return None
    if re.fullmatch(r'(?:暂定球(?:已经|已)?打(?:了)?|(?:已经|已)打(?:了)?暂定球)', t):
        if phase not in ('check', 'search', 'provisional'):
            return '请先告诉我原球是否可能出界或在罚杆区外遗失，再确认是否适用暂定球。'
        if entry.get('provisional_played'):
            return '这颗暂定球已登记，先确认原球的结果。'
        from lie_position import fresh_position
        pos=fresh_position(state,now)
        plans=state['journey'].get('player_decisions',[])
        plan=plans[-1] if plans and plans[-1].get('hole')==scope(state)[2] else {}
        save(state, event, phase='provisional', provisional_played=True,
             provisional_origin=pos['value'] if pos else None, provisional_club=plan.get('club'))
        return '暂定球已登记，先不计入成绩。找原球从开始寻找起最多三分钟。'+CHECK
    if re.search(r'三分钟.*(?:没找到|找不到|未找到)|(?:确认|已经)遗失|球已遗失', t):
        outcome = 'lost'
    elif re.fullmatch(r'(?:刚才|上一杆|这杆|开球)?(?:原球|球)?(?:已经|确认|确定|确实)?(?:出界|ob|在白桩(?:外|之外))(?:了|了ob)?', t):
        outcome = 'ob'
    elif re.fullmatch(r'(?:刚才|上一杆|这杆|开球)?(?:原球|球)?(?:已经|确认|确定|确实|几乎确定)?(?:下水|进水|进了?罚杆区|进了?[红黄]桩区)(?:了)?', t):
        outcome = 'water'
    else:
        outcome = None
    if outcome:
        if phase in ('replay', 'water', 'placement', 'provisional_live') and entry.get('outcome') == outcome:
            return '这个结果已登记。'+(WATER if outcome == 'water' else REPLAY)
        clear_plan(state)
        if outcome == 'water':
            save(state, event, phase='water', outcome=outcome, penalty=None)
            return ('暂定球作废。' if entry.get('provisional_played') else '')+WATER
        if entry.get('provisional_played') and phase == 'provisional':
            save(state, event, phase='provisional_live', outcome=outcome, penalty=1)
            return '原球'+('出界' if outcome == 'ob' else '遗失')+'，暂定球成为使用中球。罚一杆，并计入暂定球已打的杆数。请更新到暂定球的位置。'
        save(state, event, phase='replay', outcome=outcome, penalty=1, provisional_played=False)
        return ('已确认出界。' if outcome == 'ob' else '原球按遗失处理；如果几乎确定进了罚杆区，请报“确认下水”。')+REPLAY
    if t in ('已按当地规则e-5抛球', '已按当地规则e5抛球'):
        if phase != 'replay' or entry.get('provisional_played'):
            return '请先确认原球出界或遗失，并且没有打过暂定球，才能使用本场明确采用的 E-5。'
        save(state, event, phase='placement', penalty=2)
        return '按你确认采用的当地规则 E-5 登记两杆罚杆。请更新到抛球位置。'
    if re.fullmatch(r'已(?:经)?(?:回原位|回到原位|在合法位置抛球|抛球)', t):
        if phase in ('replay', 'water') and ('抛球' not in t or phase == 'water'):
            save(state, event, phase='placement', penalty=1)
            return '已登记一杆罚杆。请更新到重打位置或已抛球的位置，再讨论下一杆。'
    water = bool(re.search(r'下水|进水|水里|罚杆区', t))
    outside = bool(re.search(r'ob|出界|白桩|长草.*(?:遗失|找不到)|罚杆区外', t))
    unseen = bool(re.search(r'没看(?:到|见)|没找到|找不到|看不清|不知道球在哪', t))
    uncertain = bool(re.search(r'可能|疑似|怀疑|不确定|好像|应该(?:是)?|估计|大概', t))
    if re.search(r'^(?:这杆|下一杆|这样打|这条线).*(?:会不会|风险|可能吗)', t) and not unseen and not provisional_intent(t):
        return None
    provisional = provisional_intent(t)
    if (uncertain or unseen or provisional) and (outside or water or unseen or provisional):
        clear_plan(state)
        if phase == 'provisional':
            return '已经登记暂定球，先确定原球去向。'+CHECK
        if water and not outside and (not provisional or uncertain or unseen):
            save(state, event, phase='water_check')
            return '看到的只是可能下水。球也可能出界或在罚杆区外遗失吗？如果只可能进水，先核实；当地规则有明确例外时按当地规则。'
        if phase == 'water_check' and provisional and not outside:
            return '先确认球是否也可能出界或在罚杆区外遗失；只有可能下水时，通常不打暂定球。'
        save(state, event, phase='search')
        return PROVISIONAL
    from approach_dialogue import requested
    if not entry and requested(text):
        from lie_position import fresh_position
        from shot_evidence import haversine

        pos = fresh_position(state, now)
        if pos and pos['value'].get('simulation_source') == 'map_click':
            rows = state['journey'].get('confirmed_shot_distances', [])
            last = next((r for r in reversed(rows) if r['scope'] == list(scope(state)) and
                         r.get('simulated_landing') and r.get('valid')), None)
            if last and haversine(pos['value'], last['endpoints'][-1]['point']) <= 3 and simulated_risk(state, pos['value']):
                return after_landing(state, dict(event, data=pos['value']))
    if active or phase in ('placement', 'provisional_live'):
        if requested(text) or re.fullmatch(r'球道|长草|沙坑|左前|右前|左后|右后|前旗|中旗|后旗|继续|刚才问什么', t):
            if phase in ('check', 'search', 'water_check', 'provisional'):
                return '先确认上一杆的球。'+CHECK
            if phase in ('placement', 'provisional_live'):
                return '请先更新到'+('暂定球' if phase == 'provisional_live' else '重打或抛球')+'的位置。'
            return WATER if phase == 'water' else REPLAY
    return None

def simulated_risk(state, point):
    from lie_position import polygon_contains
    from phoenix_demo import preview
    from tee_geometry import mapped_polygons
    _, course_id, number = scope(state)
    data = state.get('evidence', {}).get(course_id, {}).get('data', {})
    if not data.get('reference_simulation'):
        return None
    hole = next((h for h in data.get('holes', []) if h['number'] == number), None)
    if not hole:
        return None
    maps = mapped_polygons(hole, True)
    for kind, label in (('ob', '出界'), ('water', '下水')):
        if any(polygon_contains(rings, point) for rings in maps[kind].values()):
            return label
    # The two short demo-only white-stake lines have an explicitly chosen
    # in-bounds reference (the green). Do not extend past the end stakes.
    green = hole['simulation_positions']['green']
    for line in preview(number, data).get('test_stakes', []):
        if line['kind'] != 'white':
            continue
        a, b = line['points'][0], line['points'][-1]
        scale = math.cos(math.radians(a['latitude']))
        def xy(p):
            return ((p['longitude']-a['longitude'])*111000*scale, (p['latitude']-a['latitude'])*111000)
        x, y = xy(b)
        px, py = xy(point)
        gx, gy = xy(green)
        along = (px*x+py*y)/(x*x+y*y)
        cross = x*py-y*px
        if 0 <= along <= 1 and (cross*(x*gy-y*gx) < 0 or abs(cross)/math.hypot(x,y) <= point['accuracy_m']):
            return '出界'
    return None

def after_landing(state, event):
    if (current(state) or {}).get('phase') in ('replay','water','search','water_check','provisional'):
        return None
    point = event['data']
    risk = simulated_risk(state, point)
    if risk:
        clear_plan(state)
        save(state, event, phase='check', outcome=None, penalty=None, provisional_played=False)
        return '模拟落点提示可能'+risk+'。先按现场边界确认。'+CHECK
    if (current(state) or {}).get('phase') == 'check':
        save(state, event, phase='closed', outcome=None, penalty=None, provisional_played=False)
    return None

def after_position(state, event, now):
    from lie_position import fresh_position
    from shot_evidence import haversine
    from shot_links import add

    entry = current(state) or {}
    phase = entry.get('phase')
    if phase not in ('placement', 'provisional_live'):
        return None
    pos = fresh_position(state, now)
    if not pos or not any(state['evidence'][eid].get('observed_at') == event['observed_at']
                          for eid in pos.get('evidence_ids', [])):
        return None
    p = pos['value']
    if entry.get('previous_position') and haversine(p, entry['previous_position']) <= 5:
        return '位置还在原球落点附近，请更新到处理后的球位。'
    if phase=='provisional_live':
        from shot_links import scope as shot_scope
        from journey import round_records
        key=list(shot_scope(state))
        existing=[r for r in round_records(state)['clubs'] if r.get('hole')==key[2]]
        original=max((r.get('stroke_number') or 0 for r in existing),default=0)
        original=max(1,original)
        origin=entry.get('provisional_origin')
        rows=state['journey'].setdefault('provisional_strokes',[])
        if not any(r['incident_id']==entry['incident_id'] for r in rows):
            original_has_distance=any(r.get('stroke_number')==original and r.get('total_horizontal_m') is not None for r in existing)
            if not original_has_distance:
                rows.append(dict(incident_id=entry['incident_id'],scope=key,observed_at=event['observed_at'],
                                 stroke_number=original,club=entry.get('provisional_club'),
                                 total_horizontal_m=None))
            rows.append(dict(incident_id=entry['incident_id'],scope=key,observed_at=event['observed_at'],
                             stroke_number=original+2,club=entry.get('provisional_club'),
                             total_horizontal_m=haversine(origin,p) if origin else None))
        state['journey']['shot_location_candidates']=[
            r for r in state['journey'].get('shot_location_candidates',[])
            if [r['round_id'],r['course'],r['hole']]!=key]
        add(state,p,pos['evidence_ids'],'provisional_ball_in_play')
        state['journey']['shot_location_candidates'][-1]['stroke_base']=original+2
        state['journey'].pop('tee_club_fallback',None)
        save(state,event,phase='closed')
        return '已更新暂定球的位置，并计入其击球和一杆罚杆。可以再问我这杆怎么打。'
    if p.get('simulation_source') == 'map_click':
        add(state, p, pos['evidence_ids'], 'simulated_relief_position')
        points = state['journey']['shot_location_candidates']
        for row in points:
            if row['id'] in pos['evidence_ids']:
                row['relief_position'] = True
        records = state['journey'].get('confirmed_shot_distances', [])
        previous = next((r for r in reversed(records) if r['scope'] == list(scope(state)) and r.get('valid')), {})
        if phase == 'placement' and entry.get('outcome') in ('ob', 'lost') and previous.get('club'):
            state['journey']['simulated_club_choice'] = dict(
                scope=list(scope(state)), point=p, club=previous['club'],
                event_id=event['event_id'], at=now)
        state['journey'].pop('tee_club_fallback', None)
    for row in state['journey'].get('ball_outcome_history', []):
        if row['incident_id'] == entry['incident_id'] and row.get('phase') == 'placement':
            row['relief_point_id'] = pos['evidence_ids'][0]
    save(state, event, phase='closed', relief_point_id=pos['evidence_ids'][0])
    return '已更新处理后的球位。这次位置更新不算击球，可以再问我怎么打。'
