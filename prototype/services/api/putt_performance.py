"""Learn pace tendencies from reported first putts at comparable distances and grades."""
import re
from statistics import median

from dialogue_routing import scope
from wedge_leave import yards

REPORT = re.compile(r'长推实绩[，,]起推([1-9]\d?)(码|米)[，,](上坡|下坡|平坡)[，,](推短|推过|进洞)(\d{0,2})(码|米)?')


def record(state, text, event_id):
    journey = state['journey']
    if text == '忘记长推实绩':
        journey.pop('putt_performance', None)
        return '好，已清除长推实绩。'
    match = REPORT.fullmatch(text)
    if not match:
        return None
    distance, unit, grade, outcome, leave, leave_unit = match.groups()
    if (outcome == '进洞' and (leave or leave_unit)) or (outcome != '进洞' and (not leave or not leave_unit or not int(leave))):
        return '请告诉我推短或推过后还剩多少，或者说进洞。'
    if journey.get('memory_allowed') is not True:
        return '开启跨场记忆后，我可以记住这类长推的控速实绩。'
    key = scope(state)
    if not key[0] or key[2] is None:
        return '先确认当前球洞，再记录长推实绩。'
    rows = journey.setdefault('putt_performance', [])
    rows[:] = [row for row in rows if row['scope'] != key]
    remaining = yards(int(leave), leave_unit) if leave else 0
    rows.append({'scope': key, 'distance_yd': yards(int(distance), unit),
                 'grade': grade, 'signed_leave_yd': -remaining if outcome == '推短' else remaining,
                 'event_id': event_id})
    del rows[:-120]
    return '已记下这次长推的距离、坡向和结果。'


def pace_note(journey, distance, unit, grade):
    if journey.get('memory_allowed') is not True or not grade:
        return ''
    rows = [row for row in journey.get('putt_performance', [])
            if row['grade'] == grade and abs(row['distance_yd'] - yards(distance, unit)) <= 3]
    if len(rows) < 3 or len({row['scope'][0] for row in rows}) < 2:
        return ''
    values = [row['signed_leave_yd'] for row in rows]
    typical = median(values)
    if not typical:
        return ''
    count = sum(value * typical > 0 for value in values)
    if count * 3 < len(rows) * 2:
        return ''
    direction = '推短' if typical < 0 else '推过'
    reminder = '可以稍多给一点力' if typical < 0 else '可以把速度再收一点'
    return f'类似的{grade}长推，你报告的{len(rows)}次里有{count}次{direction}。按今天的果岭速度，{reminder}。'
