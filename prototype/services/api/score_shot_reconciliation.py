"""Reconcile a complete sequence of selected shots with a confirmed hole score."""
from round_state import canonical, fact_value
from shot_evidence import haversine
from shot_links import live


def reconcile(state, score_event, *, allow_partial_clubs=False, patch_id=None, trim_green=False, current_only=False):
    journey = state['journey']
    session = state['session']
    patch_id = patch_id or session.get('last_patch')
    patch = state['patches'].get(patch_id, {})
    if allow_partial_clubs and patch.get('status') != 'committed':
        return ''
    total_path = next((op['path'] for op in patch.get('operations', [])
                       if op['path'].endswith('.total')), None)
    if not total_path:
        return ''
    if allow_partial_clubs and state.get('facts', {}).get(total_path, {}).get('version') != patch.get('committed_version'):
        return ''
    hole = int(total_path.split('.')[1])
    total, putts, penalty = (fact_value(state, f'holes.{hole}.{field}')
                             for field in ('total', 'putts', 'penalties'))
    if total is None or putts is None or total <= putts:
        return ''
    scope = [(journey.get('round') or {}).get('id'), fact_value(state, 'context.course_snapshot'), hole]
    points = [p for p in journey.get('shot_location_candidates', [])
              if [p['round_id'], p['course'], p['hole']] == scope]
    count = total - putts - (penalty or 0)
    if trim_green and len(points)>count+1 and count>0:
        course=state.get('evidence',{}).get(scope[1],{}).get('data',{})
        geometry=next((h for h in course.get('holes',[]) if h['number']==hole),{})
        if course.get('reference_simulation') is True:
            from journey_simulation_score import simulated_green_point
            if (all(simulated_green_point(geometry,row['point']) for row in points[count:])
                    and not any(simulated_green_point(geometry,row['point']) for row in points[:count])):
                points=points[:count+1]
    if count <= 0 or len(points) != count + 1 or not all(live(state, p) for p in points):
        return ''
    reports = journey.get('previous_club_reports', {})
    pairs = [(a, b, reports.get(canonical([*scope, a['id'], b['id']])))
             for a, b in zip(points, points[1:])]
    if not allow_partial_clubs and any(not report for _, _, report in pairs):
        return ''
    records = journey.setdefault('confirmed_shot_distances', [])
    rejected = {tuple(row['pair_ids']) for row in journey.get('rejected_shot_links', [])
                if row['scope'] == scope}
    if any((a['id'], b['id']) in rejected for a, b, _ in pairs):
        return ''
    added = 0
    for a, b, report in pairs:
        ids = [a['id'], b['id']]
        from shot_links import current_score_record
        if any(row['scope'] == scope and row['pair_ids'] == ids
               and (not current_only or (row.get('valid') and current_score_record(state,row))) for row in records):
            continue
        report = report or {}
        records.append(dict(id=f'{score_event}-{added}', scope=scope, pair_ids=ids, endpoints=[a, b],
                            total_horizontal_m=haversine(a['point'], b['point']),
                            distance_type='total_horizontal', carry=False, learning_eligible=False,
                            club=report.get('club'), club_source=report.get('source'), club_event_id=report.get('event_id'),
                            valid=True, inferred_from_score=True, score_patch_id=patch_id))
        added += 1
    if not added:
        return ''
    suffix = '罚杆未知，已标为暂估。' if penalty is None else '已标为按成绩和球位推算。'
    return f'按确认的成绩和球位顺序，补记了{added}杆水平距离。{suffix}'
