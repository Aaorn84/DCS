"""Associate a selected tee club with the first location pair leaving that tee."""
import re

from lie_position import fresh_position
from journey_previous_club import pair_key, reported_club
from round_state import canonical
from shot_evidence import haversine
from shot_links import pair, scope, valid_record

CORRECTION = re.compile(r'(?:刚才(?:那杆)?|上一杆)?(?:实际)?(?:换了|用的是|用了|用的)(.+)')


def update(state, event, now, before, result, *, decision=None):
    journey = state['journey']
    if (journey.get('stage') != 'active'
            or journey['profile'].get('shot_recording', {}).get('value') is not True):
        journey.pop('tee_club_fallback', None)
        return result
    last = journey.get('last_consultation') or {}
    if (event.get('type') == 'message' and last != before and last.get('phase') == 'tee_commit'
            and last.get('decision') and last.get('selected_club')):
        position = fresh_position(state, now)
        if position:
            journey['tee_club_fallback'] = {
                'scope': list(scope(state)), 'point': position['value'],
                'club': last['selected_club']['label'], 'event_id': event['event_id'],
            }
    if decision:
        position = fresh_position(state, now)
        if position:
            journey['tee_club_fallback'] = {
                'scope': list(scope(state)), 'point': position['value'],
                'club': decision['club'], 'event_id': event['event_id'], 'source': 'selected_shot_plan',
            }
    plan = journey.get('tee_club_fallback')
    if not plan:
        return result
    if plan['scope'] != list(scope(state)) or event.get('type') == 'simulation_hole':
        journey.pop('tee_club_fallback', None)
        return result
    key = pair_key(state, now)
    if not key:
        return result
    if plan.get('pair_key', key) != key:
        journey.pop('tee_club_fallback', None)
        return result
    start, end = pair(state)
    if haversine(plan['point'], start['point']) > max(5, min(15, start['point']['accuracy_m'] + plan['point']['accuracy_m'])):
        if not decision and (not plan.get('source') or haversine(plan['point'], end['point']) > 10):
            journey.pop('tee_club_fallback', None)
        return result

    plan['pair_key'] = key
    reports = journey.setdefault('previous_club_reports', {})
    correction = CORRECTION.fullmatch(event.get('text', '').strip().rstrip('。！! '))
    club = reported_club(correction[1]) if correction else None
    if decision is None and event.get('protocol_version',0) >= 81 and correction and correction[1].upper() == 'P杆':
        club = 'P杆'
    if club:
        reports[key] = {'club': club, 'source': 'user_report', 'event_id': event['event_id']}
    elif key not in reports:
        reports[key] = {'club': plan['club'], 'source': plan.get('source','selected_tee_plan'), 'event_id': plan['event_id']}
    report = reports[key]
    for row in journey.get('confirmed_shot_distances', []):
        if valid_record(state, row) and canonical([*row['scope'], *row['pair_ids']]) == key:
            if not row.get('club') or row.get('club_source') in ('selected_tee_plan','selected_shot_plan') or club:
                row.update(club=report['club'], club_source=report['source'], club_event_id=report['event_id'])
    pending = journey.get('pending_previous_club') or {}
    if (report['source'] in ('selected_tee_plan','selected_shot_plan') and result.get('distance', {}).get('target') == 'green_center'
            and result.get('text') and not plan.get('disclosed')):
        plan['disclosed'] = True
        text = result['text'].removesuffix('刚才那杆用的什么杆？')
        result = {**result, 'text': text + f'上一杆暂按你选的{report["club"]}记录。换了杆可以告诉我。'}
    if pending.get('key') == key:
        journey.pop('pending_previous_club', None)
        text = result.get('text', '').removesuffix('刚才那杆用的什么杆？')
        return {**result, 'text': text}
    if club and result.get('text'):
        return {**result, 'text': f'已更新，上一杆实际用的是{club}。'}
    return result
