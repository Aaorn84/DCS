"""Common additional rule paths remain explicit and share the stroke ledger."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_stroke_consistency as support
from ball_rules import current,penalties
from journey import view


class AdditionalRuleTests(unittest.TestCase):
    protocol_version=111
    setUp=support.StrokeConsistencyTests.setUp
    tearDown=support.StrokeConsistencyTests.tearDown
    send=support.StrokeConsistencyTests.send
    onboard=support.StrokeConsistencyTests.onboard
    start=support.StrokeConsistencyTests.start
    point=support.StrokeConsistencyTests.point
    select_and_sound=support.StrokeConsistencyTests.select_and_sound

    def hit(self,lat=22.7013,lon=114.15062):
        with patch('ball_rules.map_landing',return_value=None):
            return self.point(lat,lon)

    def check(self):
        self.assertEqual(self.e.state('j'),self.e.replay('j'))

    def test_unplayable_general_area(self):
        self.start();self.hit()
        for word in ('这球不可打','一般区域','后延线救济','已确认原球位置','就在这里完成救济'):
            self.send(word)
        self.assertEqual(1,penalties(self.e.state('j'),4))
        self.assertIsNone(current(self.e.state('j'))['pending'])
        self.hit(22.70145,114.15055)
        self.assertEqual([1,3],[r['stroke_number'] for r in view(self.e.state('j'))['round_records']['clubs']])
        self.check()

    def test_unplayable_bunker_outside_costs_two(self):
        self.start();self.hit()
        for word in ('这球不可打','沙坑','沙坑外后延线救济','已确认原球位置','就在这里完成救济'):
            self.send(word)
        self.assertEqual(2,penalties(self.e.state('j'),4))
        self.check()

    def test_unplayable_unknown_reference_requires_stroke_distance(self):
        self.start()
        for word in ('这球不可打','一般区域','侧向两杆救济'):
            self.send(word)
        self.assertIn('回上一杆位置',self.send('找不到原球位置')['text'])
        self.assertEqual(0,penalties(self.e.state('j'),4))

    def test_unplayable_in_penalty_area_uses_rule17(self):
        self.start()
        self.send('确认下水');self.send('原球可以打')
        self.assertIn('规则17',self.send('这球不可打')['text'])
        self.assertEqual('water',current(self.e.state('j'))['incidents'][-1]['cause'])
        self.check()

    def test_free_relief_general_area(self):
        self.start();self.hit()
        for word in ('球在修理地','一般区域','影响球位、站姿或挥杆','区内免罚救济','就在这里完成救济'):
            self.send(word)
        self.assertEqual(0,penalties(self.e.state('j'),4))
        self.assertIsNone(current(self.e.state('j'))['pending'])
        self.check()

    def test_abnormal_condition_bunker_outside_is_one(self):
        self.start();self.hit()
        for word in ('球在临时积水里','沙坑','影响球位、站姿或挥杆','沙坑外后延线救济','就在这里完成救济'):
            self.send(word)
        self.assertEqual(1,penalties(self.e.state('j'),4))
        self.check()

    def test_free_relief_green_uses_placing(self):
        self.start()
        for word in ('球在修理地','果岭','只影响击球线路','区内免罚救济','已完成免罚放置'):
            self.send(word)
        self.assertEqual(0,penalties(self.e.state('j'),4))
        self.assertIsNone(current(self.e.state('j'))['pending'])
        self.check()

    def test_line_only_in_general_area_not_free_relief(self):
        self.start()
        for word in ('球在修理地','一般区域'):
            self.send(word)
        self.assertIn('仅线路',self.send('只影响击球线路')['text'])
        self.assertIsNone(current(self.e.state('j'))['pending'])

    def test_wrong_ball_stroke_play_excludes_wrong_stroke(self):
        self.start();self.hit();self.hit(22.70145,114.15055)
        for word in ('打错球了','洞中打了别人的球','刚才记录的这一杆打错球','比杆赛','已回原球位置'):
            self.send(word)
        self.assertEqual(2,penalties(self.e.state('j'),4))
        self.assertEqual(1,len(view(self.e.state('j'))['round_records']['clubs']))
        self.hit(22.7016,114.15045)
        self.assertEqual([1,4],[r['stroke_number'] for r in view(self.e.state('j'))['round_records']['clubs']])
        self.check()

    def test_wrong_ball_match_play_records_hole_lost(self):
        self.start()
        for word in ('打错球了','洞中打了别人的球','错球击球尚未记录','比洞赛'):
            self.send(word)
        self.assertEqual('lost',self.e.state('j')['journey']['round']['hole_results']['4'])
        self.assertEqual(0,penalties(self.e.state('j'),4))

    def test_switching_ball_for_tee_shot_is_not_wrong_ball(self):
        self.start();self.hit()
        self.send('打错球了')
        self.send('仅在发球区换球开球')
        self.assertEqual(0,penalties(self.e.state('j'),4))
        self.assertEqual(1,len(view(self.e.state('j'))['round_records']['clubs']))

    def test_whiff_counts_as_stroke_and_practice_does_not(self):
        self.start();self.select_and_sound()
        self.send('挥空了');self.send('有意击球但挥空')
        rows=view(self.e.state('j'))['round_records']['clubs']
        self.assertEqual(1,len(rows))
        self.assertEqual(0,rows[0]['total_horizontal_m'])
        self.send('挥空了');self.send('只是练习挥杆')
        self.assertEqual(1,len(view(self.e.state('j'))['round_records']['clubs']))
        self.assertEqual(0,penalties(self.e.state('j'),4))
        self.check()

    def test_accidentally_moved_on_green_is_free(self):
        self.start()
        for word in ('球被我碰动了','果岭','普通意外碰动','已放回原位置'):
            self.send(word)
        self.assertEqual(0,penalties(self.e.state('j'),4))
        self.assertEqual([],view(self.e.state('j'))['round_records']['clubs'])
        self.check()

    def test_accidentally_moved_in_general_area_costs_one(self):
        self.start()
        for word in ('球被我碰动了','一般区域','普通意外碰动','已放回原位置'):
            self.send(word)
        self.assertEqual(1,penalties(self.e.state('j'),4))
        self.check()

    def test_search_movement_and_natural_force(self):
        self.start()
        self.send('寻找时碰动球');self.send('已放回原位置')
        self.assertEqual(0,penalties(self.e.state('j'),4))
        self.send('风把球吹动了');self.send('都不是')
        self.assertIsNone(current(self.e.state('j'))['pending'])
        self.assertEqual(0,penalties(self.e.state('j'),4))
        self.check()
