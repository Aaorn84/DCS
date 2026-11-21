"""Apply saved preferences to current, explicitly reported playing conditions."""
import re

from round_state import fact_value
from lie_position import fresh_position
from shot_evidence import haversine

MODES = {
    '树下': ('tree_recovery', ('横打回球道', '低飞向前')),
    '长推': ('long_putt', ('只听距离和速度', '也听路线')),
}


def respond(state, text, event_id, now, *, check_layup_match=False, learned_leave=None, learned_pace=False, risk_first=False):
    journey = state['journey']
    profile = journey['profile']
    saved = profile.get('shot_style_preferences', {}) if journey.get('memory_allowed') else {}
    for label, (key, options) in MODES.items():
        if text == f'忘记{label}偏好':
            saved.pop(key, None)
            return f'好，已清除{label}偏好。'
        declared = next((option for option in options if text == f'{label}我通常{option}'), None)
        if declared:
            if not journey.get('memory_allowed'):
                return '开启跨场记忆后，我可以把这个偏好留到下次。'
            profile.setdefault('shot_style_preferences', {})[key] = {
                'value': declared, 'source': 'user_report', 'event_id': event_id,
            }
            return f'记下了，{label}时你通常{declared}。'

    recovery = re.fullmatch(r'树下(只有横向|只有前方|横向和前方都)有出球窗口[，,](横向|前方|两边)落点可用', text)
    if recovery:
        windows = {'只有横向': {'横向'}, '只有前方': {'前方'}, '横向和前方都': {'横向', '前方'}}
        landing = {'横向': {'横向'}, '前方': {'前方'}, '两边': {'横向', '前方'}}
        routes = windows[recovery[1]] & landing[recovery[2]]
        if not routes:
            return '先找一条出球窗口和落点都合适的路线。'
        preferred = saved.get('tree_recovery', {}).get('value')
        if '前方' in routes and ('横向' not in routes or preferred == '低飞向前'):
            return '按你确认的前方窗口和落点，可以先看低飞向前。用熟悉的打法，给树枝留余量。'
        return '按你确认的横向窗口和落点，可以先横打回球道，给下一杆留干净球位。'
    if re.fullmatch(r'树下怎么打[？?]?', text):
        return '横向回球道和低飞向前，哪条有出球窗口和可用落点？'

    putt = re.fullmatch(r'长推([1-9][0-9]?)(米|码)(?:[，,](上坡|下坡|平坡))?(?:[，,]球会向([左右])偏)?[，,]怎么推[？?]?', text)
    if putt:
        distance, unit, grade, drift = putt.groups()
        pace = {'上坡': '上坡需要多给一点力', '下坡': '下坡先控住速度', '平坡': '按平坡的节奏控制速度'}
        reply = f'{distance}{unit}长推，{pace.get(grade, "先按现场坡度和果岭速度找手感")}，把球送到洞口附近。'
        if learned_pace:
            from putt_performance import pace_note

            reply += pace_note(journey, int(distance), unit, grade)
        if saved.get('long_putt', {}).get('value') == '只听距离和速度':
            return reply
        if drift:
            other = '右' if drift == '左' else '左'
            return reply + f'按你看到的向{drift}偏，起线先瞄洞口偏{other}，偏多少要结合速度。'
        return reply + '要判断起线，先看球沿推击方向会向哪边偏。'

    edge = re.fullmatch(r'靠边旗[，,]旗在([左右])侧[，,]旗侧(有障碍|落点太窄|有足够落点且飞越有余量)[，,]怎么打[？?]?', text)
    if edge:
        flag_side, conditions = edge.groups()
        preferred = saved.get('edge_pin', {}).get('value')
        usual_miss = profile.get('usual_miss', {}).get('value', '')
        if conditions != '有足够落点且飞越有余量':
            return '旗侧的障碍或落点空间限制了攻旗，先瞄果岭较宽的中央区域。'
        if usual_miss in ('偏'+flag_side, '容易偏'+flag_side):
            return f'旗在{flag_side}侧，你也常偏{flag_side}。把目标移向果岭中央，给常见偏差留空间。'
        if preferred == '攻旗':
            return '按你确认的飞越余量和落点，可以考虑攻旗，把落点留在旗的内侧。'
        return '先瞄果岭中央的宽处。'

    routes = re.fullmatch(r'五杆洞第二杆[，,]两条落点都可用[，,]可推进(\d{1,3})或(\d{1,3})(码|米)[，,]怎么选[？?]?', text)
    if routes and risk_first:
        return '这两条落点分别朝哪个方向、附近有什么障碍？先按落区空间和下一杆风险比较。'
    if routes:
        return layup(state, saved, now, (int(routes[1]), int(routes[2]), routes[3]),
                     check_match=check_layup_match, learned_leave=learned_leave)
    if re.fullmatch(r'五杆洞第二杆怎么打[？?]?', text):
        if risk_first:return None
        return layup(state, saved, now, learned_leave=learned_leave)
    return None


def layup(state, saved, now, routes=None, *, check_match=True, learned_leave=None):
    """Compute a distance budget, with the landing area confirmed on course."""
    number = fact_value(state, 'context.active_hole')
    evidence = state.get('evidence', {}).get(fact_value(state, 'context.course_snapshot'), {})
    hole = next((hole for hole in evidence.get('data', {}).get('holes', [])
                 if hole['number'] == number), {})
    position = fresh_position(state, now)
    greens = [point for point in hole.get('objects', []) if point.get('kind') == 'green_center']
    if hole.get('par') != 5 or not position or len(greens) != 1:
        return '先确认当前是五杆洞，并更新球位和果岭参考点，我再倒推留距。'
    target = saved.get('leave_distance') or learned_leave
    if not target:
        return '你下一杆想留下多少距离？可以说“我喜欢下一杆留90码”。'
    unit = target['unit']
    inferred = learned_leave is not None and not saved.get('leave_distance')
    basis = '按你的短杆实绩，' if inferred else ''
    distance = haversine(position['value'], greens[0]) / (.9144 if unit == '码' else 1)
    advance = distance - target['value']
    if routes:
        first, second, route_unit = routes
        scale = 1 if route_unit == unit else (.9144 if unit == '米' else 1/.9144)
        choices = [(length, distance-length*scale) for length in (first, second)
                   if 0 < length*scale < distance]
        if check_match and not any(abs(left-target['value']) <= 10 * (.9144 if unit == '米' else 1)
                                   for _, left in choices):
            reply = f'这两条路线都留不出接近{target["value"]}{unit}的下一杆。'
            if advance <= 0:
                return reply + '当前剩余距离已经不长于你想留的距离，可以按当前球位规划下一杆。'
            return (reply + f'{basis}想留{target["value"]}{unit}，这杆沿果岭方向大约推进{round(advance)}{unit}。'
                    '先确认这个距离有可用落点，再按落地加滚动的总距离选杆。')
        if not choices:
            return '这两个距离都无法在果岭前留出下一杆，请核对落点和剩余距离。'
        length, remainder = min(choices, key=lambda item: abs(item[1]-target['value']))
        comparison = '，'.join(f'推进{v}{route_unit}预计剩{round(left)}{unit}' for v, left in choices)
        return f"{comparison}。按你确认的落点，推进{length}{route_unit}更接近{'按实绩推断的留距' if inferred else '你喜欢的留距'}。"
    if advance < 5:
        return '现在到果岭参考点已经接近或短于你喜欢的留距，可以按当前距离直接规划下一杆。'
    return (f'{basis}想留{target["value"]}{unit}，沿果岭方向这杆预计推进约{round(advance)}{unit}。'
            '选杆要用落地加滚动的总距离。先确认这一带有宽阔落点，'
            '再与继续推进的路线比较；绕障碍时按实际落点重算。')


def approach_reply(text):
    """Use the player's current clearance and landing assessment, in one unit."""
    match = re.fullmatch(
        r'(?:三杆洞|攻果岭)[，,]短杆Carry(\d{1,3})[，,]长杆收挥Carry(\d{1,3})'
        r'[，,]飞越至少(\d{1,3})[，,]可用落点(\d{1,3})到(\d{1,3})(码|米)[，,]怎么选[？?]?', text)
    if not match:
        return None
    short, long, clear, front, back = map(int, match.groups()[:5])
    if not 0 < front < back or not short or not long:
        return '请核对当前球位到落区前沿、后沿和两支杆的Carry。'
    candidates = {label for label, carry in (('短一号正常挥', short), ('长一号收着打', long))
                  if carry > clear and front <= carry < back}
    return candidates


def approach_note(journey, text):
    candidates = approach_reply(text)
    if candidates is None or isinstance(candidates, str):
        return candidates
    if not candidates:
        return '按你提供的飞越距离和落点范围，两种挥法都缺少余量，先换一个更宽的目标。'
    preferred = None
    if journey.get('memory_allowed'):
        preferred = journey['profile'].get('shot_style_preferences', {}).get('between_clubs', {}).get('value')
    if preferred not in candidates:
        preferred = '短一号正常挥' if '短一号正常挥' in candidates else '长一号收着打'
    return f'按你提供的飞越距离和落点，可以先考虑{preferred}。再给距离波动和落地滚动留余量。'
