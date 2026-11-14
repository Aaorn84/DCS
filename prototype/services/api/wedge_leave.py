"""Infer a leave distance from player-reported single-shot wedge outcomes."""
import re
from statistics import median

from dialogue_routing import scope

REPORT = re.compile(r'短杆实绩[，,]\s*起杆离旗(\d{1,3})(码|米)[，,]\s*一杆后离旗(\d{1,3})(码|米)')

COMBINATION_REPORT = re.compile(
    REPORT.pattern + r'[，,]\s*用(P杆|S杆|G杆|L杆|[45][0-9]度杆|6[0-4]度杆)[，,]\s*(半挥杆|四分之三挥杆|全挥杆)',
    re.IGNORECASE,
)


GREEN_REPORT = re.compile(
    REPORT.pattern + r'[，,]\s*球位(球道|果岭边短草)[，,]\s*两种打法都可用[，,]\s*用(切滚|抛切|高抛)'
)
GREEN_QUERY = re.compile(
    r'果岭边[，,]\s*离旗(\d{1,2})(码|米)[，,]\s*球位(球道|果岭边短草)'
    r'[，,]\s*两种打法都可用[，,]\s*怎么选[？?]?'
)


def green_comparison(journey, distance, unit, lie):
    groups = {}
    if journey.get('memory_allowed') is True:
        for row in journey.get('greenside_reports', []):
            if row['lie'] == lie and abs(row['start_yd'] - yards(distance, unit)) <= 5:
                groups.setdefault(row['style'], []).append(row)
    stats = {style: median(row['finish_yd'] for row in rows) for style, rows in groups.items()
             if len(rows) >= 3 and len({row['scope'][0] for row in rows}) >= 2}
    habit = journey['profile'].get('shot_style_preferences', {}).get('green', {}).get('value')
    prefix = f'你平时偏好{habit}。' if habit else ''
    if '切滚' not in stats or len(stats) < 2:
        return prefix + '相近距离、相同球位的实绩还不足以比较。两种打法都可用时，先考虑你更熟悉的打法。'
    scale = .9144 if unit == '米' else 1
    summary = '，'.join(f'{style}一杆后离旗中位数约{value*scale:.1f}{unit}'
                       for style, value in sorted(stats.items()))
    best = min(stats, key=stats.get)
    if list(stats.values()).count(stats[best]) > 1:
        return prefix + summary + '。领先的打法表现相近，可以按当天手感选。'
    return prefix + summary + f'。按这批实绩，可以先考虑{best}，再看今天的落点和滚动空间。'


def record_or_compare_green(state, text, event_id):
    journey = state['journey']
    if text == '忘记果岭边实绩':
        journey.pop('greenside_reports', None)
        return '好，已清除果岭边打法实绩。'
    query = GREEN_QUERY.fullmatch(text)
    if query:
        return green_comparison(journey, int(query[1]), query[2], query[3])
    report = GREEN_REPORT.fullmatch(text)
    if not report:
        return None
    if journey.get('memory_allowed') is not True:
        return '开启跨场记忆后，我可以用这些果岭边实绩比较打法。'
    shot_scope = scope(state)
    if not shot_scope[0] or shot_scope[2] is None:
        return '先确认当前球洞，再记录果岭边实绩。'
    start = yards(int(report[1]), report[2])
    if not 0 < start <= 50:
        return '目前比较的是起杆离旗50码以内的果岭边打法。'
    rows = journey.setdefault('greenside_reports', [])
    rows[:] = [row for row in rows if row['scope'] != shot_scope]
    rows.append({'scope': shot_scope, 'start_yd': start, 'finish_yd': yards(int(report[3]), report[4]),
                 'lie': report[5], 'style': report[6], 'event_id': event_id})
    del rows[:-60]
    return f'已记下这杆从{report[5]}用{report[6]}后的离旗距离。'


def suggested_combination(journey, distance_yd):
    if journey.get('memory_allowed') is not True:
        return None
    groups = {}
    for row in journey.get('wedge_leave_reports', []):
        if row.get('club') and abs(row['start_yd'] - distance_yd) <= 5:
            groups.setdefault((row['club'], row['swing']), []).append(row)
    eligible = [(key, rows) for key, rows in groups.items()
                if len(rows) >= 3 and len({row['scope'][0] for row in rows}) >= 2]
    if not eligible:
        return None
    (club, swing), rows = min(
        eligible, key=lambda item: (median(row['finish_yd'] for row in item[1]), -len(item[1]), item[0])
    )
    return {'club': club, 'swing': swing, 'samples': len(rows),
            'median_finish_yd': median(row['finish_yd'] for row in rows)}


def yards(value, unit):
    return value / (.9144 if unit == '米' else 1)


def suggested_leave(journey):
    profile = journey.get('profile', {})
    groups = {}
    for report in journey.get('wedge_leave_reports', []):
        bucket = int((report['start_yd'] + 5) // 10)
        groups.setdefault(bucket, []).append(report)
    eligible = [rows for rows in groups.values()
                if len(rows) >= 3 and len({row['scope'][0] for row in rows}) >= 2]
    if not eligible:
        return None
    # Rank comparable distance bands by median leave after one stroke.
    best = min(eligible, key=lambda rows: (median(row['finish_yd'] for row in rows), -len(rows)))
    unit = profile.get('units', {}).get('value', '码')
    scale = .9144 if unit == '米' else 1
    return {'value': round(median(row['start_yd'] for row in best) * scale), 'unit': unit}


def record_or_query(state, text, event_id, *, combinations=False):
    journey = state['journey']
    profile = journey['profile']
    if text == '忘记短杆实绩':
        journey.pop('wedge_leave_reports', None)
        return '好，已清除用来推断留距的短杆实绩。'
    if text in ('我擅长留多少码', '我擅长留多少码？', '我擅长留多少码?'):
        target = profile.get('shot_style_preferences', {}).get('leave_distance')
        if target:
            return f'你设定的留距是{target["value"]}{target["unit"]}。'
        learned = suggested_leave(journey)
        if learned:
            return f'按你目前报告的短杆实绩，可以先参考留{learned["value"]}{learned["unit"]}。'
        return '目前实绩还不够。可以用“短杆实绩，起杆离旗75码，一杆后离旗5码”记录。'
    combo = COMBINATION_REPORT.fullmatch(text) if combinations else None
    report = combo or REPORT.fullmatch(text)
    if not report:
        return None
    if journey.get('memory_allowed') is not True:
        return '开启跨场记忆后，我可以用你报告的短杆实绩推断留距。'
    shot_scope = scope(state)
    if not shot_scope[0] or shot_scope[2] is None:
        return '先确认当前球洞，再记录这杆短杆实绩。'
    start, finish = yards(int(report[1]), report[2]), yards(int(report[3]), report[4])
    if not 20 - 1e-8 <= start <= 120 + 1e-8:
        return '目前用约20到120码的短杆实绩推断留距。'
    rows = journey.setdefault('wedge_leave_reports', [])
    rows[:] = [row for row in rows if row['scope'] != shot_scope]
    row = {'scope': shot_scope, 'start_yd': start, 'finish_yd': finish, 'event_id': event_id}
    if combo:
        row.update(club=combo[5].upper(), swing=combo[6])
    rows.append(row)
    del rows[:-60]
    if combo:
        return f'已记下{row["club"]}{row["swing"]}，包括起杆距离和一杆后的离旗距离。'
    return '已记下这杆的起杆距离和一杆后的离旗距离。'
