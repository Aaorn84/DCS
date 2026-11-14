import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import unittest
from unittest.mock import patch

from round_state import canonical
from score_shot_reconciliation import reconcile


class ScoreShotReconciliationTests(unittest.TestCase):
    def test_five_with_two_putts_backfills_two_missing_distances(self):
        scope = ['round-1', 'course', 1]
        points = [dict(id=str(n), round_id=scope[0], course=scope[1], hole=1,
                       point={'latitude': 30, 'longitude': 110+n*.001}) for n in range(4)]
        reports = {canonical([*scope, str(n), str(n+1)]):
                   {'club': club, 'source': 'selected_shot_plan', 'event_id': f'club-{n}'}
                   for n, club in enumerate(('一号木', '8号铁', '52度杆'))}
        journey = {'round': {'id': scope[0]}, 'shot_location_candidates': points,
                   'previous_club_reports': reports, 'confirmed_shot_distances': [
                       {'scope': scope, 'pair_ids': ['0', '1']},
                   ]}
        state = {'journey': journey, 'session': {'last_patch': 'score'},
                 'patches': {'score': {'operations': [{'path': 'holes.1.total'}]}}}
        values = {'holes.1.total': 5, 'holes.1.putts': 2, 'context.course_snapshot': 'course'}
        with patch('score_shot_reconciliation.fact_value', side_effect=lambda s,k: values.get(k)), patch(
            'score_shot_reconciliation.live', return_value=True
        ):
            self.assertIn('补记了2杆', reconcile(state, 'confirm'))
            self.assertEqual(reconcile(state, 'retry'), '')
            journey['confirmed_shot_distances'][1:] = []
            del reports[canonical([*scope, '1', '2'])]
            state['patches']['score']['status'] = 'committed'
            self.assertEqual(reconcile(state, 'legacy'), '')
            self.assertIn('补记了2杆', reconcile(state, 'partial', allow_partial_clubs=True))
            self.assertEqual(reconcile(state, 'retry', allow_partial_clubs=True), '')
        rows = journey['confirmed_shot_distances'][1:]
        self.assertEqual([row['club'] for row in rows], [None, '52度杆'])
        self.assertTrue(all(row['inferred_from_score'] and not row['carry'] for row in rows))

    def test_round_records_order_by_location_pairs(self):
        from journey import round_records
        scope = ['round-1', 'course', 1]
        points = [dict(id=str(n), round_id=scope[0], course=scope[1], hole=1)
                  for n in range(4)]
        reports = {canonical([*scope, str(n), str(n+1)]):
                   {'club': club, 'event_id': str(n)}
                   for n, club in ((2, '52度杆'), (0, '一号木'), (1, 'P杆'))}
        state = {'journey': {'round': {'id': scope[0]}, 'shot_location_candidates': points,
                             'previous_club_reports': reports}}
        rows = round_records(state)['clubs']
        self.assertEqual([(row['stroke_number'], row['club']) for row in rows],
                         [(1, '一号木'), (2, 'P杆'), (3, '52度杆')])
