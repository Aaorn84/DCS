"""Missing-shot data rules: never turn phone movement or a gap into one shot."""
import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]


def gate():
    spec=importlib.util.spec_from_file_location('shot_evidence',ROOT/'scripts/shot_evidence.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def point(latitude=22.5,longitude=114.,**updates):
    value=dict(latitude=latitude,longitude=longitude,crs='WGS84',accuracy_m=3,
               observed_at='2026-11-06T07:00:00Z',hole_id='h1',ball_position_confirmed=True)
    value.update(updates);return value


def event(**updates):
    value=dict(recording_consent=True,start=point(),
               end=point(longitude=114.001,observed_at='2026-11-06T07:03:00Z'),
               single_stroke_confirmed=True,intervening_strokes=0,relief_or_provisional=False,
               gap_open=False,club_id='7i',club_confirmed=True,max_position_error_sum_m=15)
    value.update(updates);return value


class ShotEvidenceTests(unittest.TestCase):
    def test_confirmed_pair_gives_horizontal_total_not_carry(self):
        m=gate();result=m.assess(event())
        self.assertEqual(result['status'],'confirmed_total')
        self.assertGreater(result['total_horizontal_m'],100)
        self.assertLess(result['total_horizontal_m'],105)
        self.assertTrue(result['usable_for_club_total_stats'])
        self.assertFalse(result['usable_for_carry_stats'])
        self.assertIsNone(result['followup_field'])

    def test_missing_start_never_substitutes_tee_center(self):
        result=gate().assess(event(start=None))
        self.assertIsNone(result['total_horizontal_m'])
        self.assertIn('start',result['missing_fields'])
        self.assertEqual(result['next_start_candidate']['longitude'],114.001)

    def test_unknown_club_keeps_unassigned_distance_only(self):
        result=gate().assess(event(club_id=None,club_confirmed=False))
        self.assertEqual(result['status'],'unassigned_total')
        self.assertIsNotNone(result['total_horizontal_m'])
        self.assertFalse(result['usable_for_club_total_stats'])
        self.assertEqual(result['followup_field'],'club_id')

    def test_gap_or_multiple_strokes_or_relief_cannot_form_one_shot(self):
        for updates in (dict(gap_open=True),dict(intervening_strokes=1),
                        dict(relief_or_provisional=True),dict(single_stroke_confirmed=False)):
            with self.subTest(updates=updates):
                result=gate().assess(event(**updates))
                self.assertIsNone(result['total_horizontal_m'])
                self.assertFalse(result['usable_for_club_total_stats'])
                self.assertIn(result['followup_field'],('single_stroke_link',None))

    def test_phone_position_not_automatically_ball_position(self):
        result=gate().assess(event(end=point(longitude=114.001,ball_position_confirmed=False)))
        self.assertIsNone(result['total_horizontal_m'])
        self.assertIsNone(result['next_start_candidate'])
        self.assertIn('end_ball_position',result['missing_fields'])

    def test_bad_accuracy_cross_hole_and_time_order_rejected(self):
        for end in (point(longitude=114.001,accuracy_m=30),point(longitude=114.001,hole_id='h2'),
                    point(longitude=114.001,observed_at='2026-11-06T06:59:00Z')):
            with self.subTest(end=end):
                result=gate().assess(event(end=end))
                self.assertIsNone(result['total_horizontal_m'])
                self.assertFalse(result['usable_for_club_total_stats'])

    def test_declined_recording_does_not_keep_coordinates_or_ask_club(self):
        result=gate().assess(event(recording_consent=False))
        self.assertEqual(result['status'],'disabled')
        self.assertIsNone(result['next_start_candidate'])
        self.assertIsNone(result['followup_field'])
        self.assertNotIn('start',result)

    def test_invalid_coordinates_and_same_position_do_not_create_shot(self):
        m=gate()
        with self.assertRaises(m.InputError):m.assess(event(end=point(latitude=91)))
        result=m.assess(event(end=point(observed_at='2026-11-06T07:03:00Z')))
        self.assertEqual(result['status'],'unresolved')
        self.assertIsNone(result['total_horizontal_m'])


if __name__=='__main__':unittest.main()
