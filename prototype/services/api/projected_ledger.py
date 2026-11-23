"""Read-only presentation of shared-core projections, with no rule transitions."""
from round_state import fact_value,canonical

def current(state):
 j=state.get('journey',{});key=canonical([(j.get('round') or {}).get('id'),fact_value(state,'context.course_snapshot'),fact_value(state,'context.active_hole')])
 return j.get('round_ledger',{}).get(key)

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
                               source='shared_core', ball_id=event['ball_id']))
    return result
