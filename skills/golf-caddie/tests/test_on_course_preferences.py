import unittest
from unittest.mock import patch

from test_journey_style_preferences import StyleFixture
from on_course_preferences import layup


class OnCoursePreferencesTests(StyleFixture, unittest.TestCase):
    protocol_version = 58

    def test_tree_window_and_landing_override_favorite(self):
        self.at_fairway()
        self.send('树下我通常低飞向前')
        self.assertIn('先看低飞', self.send('树下横向和前方都有出球窗口，两边落点可用')['text'])
        self.assertIn('先横打', self.send('树下横向和前方都有出球窗口，横向落点可用')['text'])
        self.assertIn('先找', self.send('树下只有前方有出球窗口，横向落点可用')['text'])

    def test_putt_pace_and_optional_line(self):
        self.at_fairway()
        query = '长推12米，下坡，球会向右偏，怎么推？'
        self.send('长推我通常只听距离和速度')
        self.assertNotIn('瞄洞口偏左', self.send(query)['text'])
        self.send('长推我通常也听路线')
        self.assertIn('瞄洞口偏左', self.send(query)['text'])
        self.assertEqual(self.e.state('j'), self.e.replay('j'))

    def test_shot_clearance_and_side_miss_override_preference(self):
        self.at_fairway()
        self.send('两支杆之间我通常短一号正常挥')
        reply = self.send('攻果岭，短杆Carry130，长杆收挥Carry138，飞越至少132，可用落点133到145码，怎么选？')
        self.assertIn('考虑长一号收着打', reply['text'])
        self.send('靠边旗我通常攻旗')
        reply = self.send('靠边旗，旗在右侧，旗侧有足够落点且飞越有余量，怎么打？')
        self.assertIn('移向果岭中央', reply['text'])

    def test_five_par_layup_compares_two_reported_areas(self):
        point = {'kind': 'green_center'}
        state = {'evidence': {'map': {'data': {'holes': [{'number': 1, 'par': 5, 'objects': [point]}]}}}}
        saved = {'leave_distance': {'value': 90, 'unit': '码'}}
        with patch('on_course_preferences.fact_value', side_effect=lambda s,k: 'map' if k.endswith('snapshot') else 1), patch(
            'on_course_preferences.fresh_position', return_value={'value': {}}
        ), patch('on_course_preferences.haversine', return_value=250*.9144):
            self.assertIn('推进约160码', layup(state, saved, 0))
            self.assertIn('推进160码更接近', layup(state, saved, 0, (160, 200, '码')))

    def test_five_par_rejects_both_routes_outside_preferred_leave_distance(self):
        state = {'evidence': {'map': {'data': {'holes': [
            {'number': 1, 'par': 5, 'objects': [{'kind': 'green_center'}]},
        ]}}}}
        saved = {'leave_distance': {'value': 90, 'unit': '码'}}
        with patch('on_course_preferences.fact_value', side_effect=lambda s, k: 'map' if k.endswith('snapshot') else 1), patch(
            'on_course_preferences.fresh_position', return_value={'value': {}}
        ), patch('on_course_preferences.haversine', return_value=163*.9144):
            for routes in ((160, 200, '码'), (180, 200, '码'), (140, 160, '码')):
                reply = layup(state, saved, 0, routes)
                self.assertIn('两条路线都留不出接近90码', reply)
                self.assertIn('大约推进73码', reply)

    def test_five_par_uses_inferred_leave_until_player_sets_a_preference(self):
        state = {'evidence': {'map': {'data': {'holes': [
            {'number': 1, 'par': 5, 'objects': [{'kind': 'green_center'}]},
        ]}}}}
        learned = {'value': 75, 'unit': '码'}
        with patch('on_course_preferences.fact_value', side_effect=lambda s, k: 'map' if k.endswith('snapshot') else 1), patch(
            'on_course_preferences.fresh_position', return_value={'value': {}}
        ), patch('on_course_preferences.haversine', return_value=163*.9144):
            reply = layup(state, {}, 0, learned_leave=learned)
            self.assertIn('按你的短杆实绩', reply)
            self.assertIn('推进约88码', reply)
            self.assertIn('推进约73码', layup(state, {'leave_distance': {'value': 90, 'unit': '码'}},
                                                  0, learned_leave=learned))
