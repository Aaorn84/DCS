"""Compare reported lateral misses against current tee-route hazards."""
import re
from statistics import median

from dialogue_routing import scope

CLUBS = {'一号木': 'driver', '1号木': 'driver', '三号木': 'three_wood',
         '3号木': 'three_wood', '长铁杆': 'long_iron', '铁木杆': 'long_iron'}
REPORT = re.compile(r'开球实绩[，,]\s*用([^，,]+)[，,]\s*(?:打直|偏([左右])(\d{1,3})(码|米))')


def record(state, text, event_id):
    journey = state['journey']
    if text == '忘记开球实绩':
        journey.pop('tee_performance', None)
        return '好，已清除开球偏差实绩。'
    match = REPORT.fullmatch(text)
    if not match:
        return None
    club, side, distance, unit = match.groups()
    if club not in CLUBS:
        return '目前可以记录一号木、3号木，或你档案里的长铁杆或铁木杆。'
    if journey.get('memory_allowed') is not True:
        return '开启跨场记忆后，我可以用你报告的开球偏差比较球杆。'
    shot_scope = scope(state)
    if shot_scope[2] is None:
        return '先确认当前球洞，再记录开球实绩。'
    offset = int(distance or 0) / (.9144 if unit == '米' else 1)
    rows = journey.setdefault('tee_performance', [])
    rows[:] = [row for row in rows if row['scope'] != shot_scope]
    rows.append({'scope': shot_scope, 'club': CLUBS[club],
                 'offset_yd': -offset if side == '左' else offset, 'event_id': event_id})
    del rows[:-120]
    return f'已记下这杆{club}相对瞄准线的偏差。'


def comparison(journey, routes, details):
    if journey.get('memory_allowed') is not True:
        return ''
    notes = []
    flagged = set()
    for route in routes:
        rows = [row for row in journey.get('tee_performance', []) if row['club'] == route['club_key']]
        if len(rows) < 3 or len({row['scope'][0] for row in rows}) < 2:
            continue
        offsets = [row['offset_yd'] for row in rows]
        left = [abs(value) for value in offsets if value < 0]
        right = [value for value in offsets if value > 0]
        unit = journey.get('profile', {}).get('units', {}).get('value', '码')
        scale = .9144 if unit == '米' else 1
        sides = '、'.join(f'偏{side}{len(values)}次（中位约{round(median(values)*scale)}{unit}）'
                         for side, values in [('左', left), ('右', right)] if values)
        note = f'{route["club"]}，你报告的{len(rows)}次开球中，{sides or "都报为打直"}。'
        facts = (details or {}).get(route['kind'], {})
        for key, label in [('bunker', '沙坑'), ('water', '水障碍')]:
            hazard = facts.get(key)
            if not hazard or hazard['side'] not in ('左侧', '右侧'):
                continue
            misses = left if hazard['side'] == '左侧' else right
            if misses:
                note += f'这条路线{hazard["side"]}有{label}，与你用这支杆的偏差方向重合。'
                flagged.add(route['kind'])
        if facts.get('width_yards'):
            beyond = sum(abs(value) > facts['width_yards'] / 2 for value in offsets)
            if beyond:
                note += f'若瞄落区中央，有{beyond}次报告偏差超过这里约{round(facts["width_yards"]*scale)}{unit}宽落区的一半。'
        notes.append(note)
    if flagged == {'aggressive'}:
        notes.append('这洞可以先看保守路线。')
    return ''.join(notes)
