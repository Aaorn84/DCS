"""Keep player-reported carry separated by club and lie."""
import re
from statistics import median

from dialogue_routing import scope
from wedge_leave import yards

CLUB = r'[2-9]号?铁|[3-9]号木|[2-9]号铁木杆|[PpSsGgLl]杆|(?:4[6-9]|5[0-9]|6[0-4])度杆'
REPORT = re.compile(rf'球位实绩[，,]\s*(球道|长草)[，,]\s*用({CLUB})[，,]\s*Carry\s*(\d{{1,3}})(码|米)', re.I)
QUERY = re.compile(rf'({CLUB})(?:在)?(球道和长草|球道|长草)(?:的)?Carry(?:多少|怎么选)?[？?]?', re.I)


def club_name(club):
    return re.sub(r'^([2-9])铁$', r'\1号铁', club.upper())


def stats(journey, club, lie):
    if journey.get('memory_allowed') is not True:
        return None
    rows = [row for row in journey.get('lie_carry_reports', [])
            if row['club'] == club and row['lie'] == lie]
    if len(rows) < 3 or len({row['scope'][0] for row in rows}) < 2:
        return None
    carries = [row['carry_yd'] for row in rows]
    return len(rows), min(carries), median(carries), max(carries)


def wording(journey, club, lie):
    report = stats(journey, club, lie)
    if not report:
        return None
    count, low, center, high = report
    unit = journey['profile'].get('units', {}).get('value', '码')
    scale = .9144 if unit == '米' else 1
    return (f'{club}在{lie}有{count}条实绩，Carry中位数约{round(center*scale)}{unit}，'
            f'记录范围{round(low*scale)}到{round(high*scale)}{unit}。')


def respond(state, text, event_id):
    journey = state['journey']
    if text == '忘记球位实绩':
        journey.pop('lie_carry_reports', None)
        return '好，已清除球道和长草的Carry实绩。'
    query = QUERY.fullmatch(text)
    if query:
        club = club_name(query[1])
        return ''.join(wording(journey, club, lie) or f'{club}在{lie}的Carry实绩还不足。'
                       for lie in query[2].split('和'))
    match = REPORT.fullmatch(text)
    if not match:
        return None
    if journey.get('memory_allowed') is not True:
        return '开启跨场记忆后，我可以分别记住这支杆在球道和长草的Carry。'
    shot_scope = scope(state)
    if not shot_scope[0] or shot_scope[2] is None:
        return '先确认当前球洞，再记录这杆的Carry。'
    lie, club, amount, unit = match.groups()
    club = club_name(club)
    carry = yards(int(amount), unit)
    if not 0 < carry <= 400:
        return '请核对球第一次落地的距离。'
    rows = journey.setdefault('lie_carry_reports', [])
    rows[:] = [row for row in rows if (row['scope'], row['club'], row['lie']) != (shot_scope, club, lie)]
    rows.append({'scope': shot_scope, 'club': club, 'lie': lie, 'carry_yd': carry, 'event_id': event_id})
    del rows[:-120]
    return f'已记下{club}在{lie}的Carry约{amount}{unit}。'


def approach_context(journey, text):
    consultation = journey.get('consultation') or {}
    assessment = consultation.get('strategy_assessment') or {}
    lie = consultation.get('lie_report')
    if consultation.get('phase') != 'plan' or lie not in ('球道', '长草') or not assessment.get('distance_m'):
        return ''
    if not re.search(r'到(?:果岭(?:中心|参考点)|旗位)约', text):
        return ''
    target = assessment['distance_m'] / .9144
    choices = {row['club'] for row in journey.get('lie_carry_reports', [])}
    candidates = [(club, stats(journey, club, lie)) for club in sorted(choices)]
    comparable = [(club, record) for club, record in candidates if record and abs(record[2]-target) <= 15]
    if not comparable:
        return ''
    club, _ = min(comparable, key=lambda item: abs(item[1][2]-target))
    note = wording(journey, club, lie)
    if lie == '长草':
        return note + '还要看球埋得多深，飞越余量不足时先脱困。'
    return note + '用这组实绩核对这杆的飞越距离和落点。'

FLIGHT = re.compile(
    rf'飞越比较[，,]\s*(球道|长草)[，,]\s*飞越至少(\d{{1,3}})(码|米)'
    rf'[，,]\s*用({CLUB})或({CLUB})[，,]\s*怎么选[？?]?', re.I
)


def compare_flight(journey, text):
    match = FLIGHT.fullmatch(text)
    if not match:
        return None
    lie, minimum, unit, first, second = match.groups()
    threshold = yards(int(minimum), unit)
    if threshold <= 0:
        return '请核对障碍远沿所需的飞越距离。'
    clubs = dict.fromkeys(map(club_name, (first, second)))
    details, candidates = [], []
    for club in clubs:
        record = stats(journey, club, lie)
        if not record:
            details.append(f'{club}在{lie}的实绩不足。')
        elif record[1] <= threshold:
            details.append(wording(journey, club, lie) + '记录中有球未留出飞越余量。')
        else:
            details.append(wording(journey, club, lie))
            candidates.append((record[1] - threshold, club))
    if not candidates:
        return ''.join(details) + '先考虑打到障碍前或绕开。'
    club = max(candidates)[1]
    return ''.join(details) + f'可先考虑{club}，再确认当杆球位、风和障碍后落点。'
