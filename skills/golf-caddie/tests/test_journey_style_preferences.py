import unittest

import test_journey_recovery as base


class StyleFixture:

    protocol_version = 54
    setUp = base.JourneyRecoveryTests.setUp
    tearDown = base.JourneyRecoveryTests.tearDown
    send = base.JourneyRecoveryTests.send
    gps = base.JourneyRecoveryTests.gps
    onboard = base.JourneyRecoveryTests.onboard
    at_fairway = base.JourneyRecoveryTests.at_fairway


class ShotStyleTests(StyleFixture, unittest.TestCase):
    def test_water_requires_three_distinct_comparable_choices(self):
        self.at_fairway()
        choice = '确认能过水也能打到水前，我选先打到水前'
        for _ in range(3):
            self.assertNotIn('最近几次', self.send(choice)['text'])
        for hole in (2, 3):
            self.send(type='simulation_hole', hole=hole)
            result = self.send(choice)
        self.assertIn('最近几次', result['text'])
        ask = '确认能过水也能打到水前，怎么选？'
        self.assertIn('优先考虑先打到水前', self.send(ask)['text'])
        self.send('结束球局')
        self.send('确认结束')
        self.send('先不聊')
        self.send(type='next_round')
        profile = self.e.state('j')['journey']['profile']
        self.assertEqual(profile['shot_style_preferences']['water']['value'], '先打到水前')
        self.assertEqual(self.e.state('j'), self.e.replay('j'))

    def test_explicit_green_preference_and_revocation(self):
        self.at_fairway()
        self.send('果岭边我通常切滚')
        self.send('果岭边我通常高抛')
        ask = '确认切滚和高抛都能打，怎么选？'
        self.assertIn('优先考虑高抛', self.send(ask)['text'])
        self.send('忘记果岭边打法偏好')
        self.assertNotIn('优先考虑高抛', self.send(ask)['text'])
        self.send('果岭边我通常高抛')
        self.send('关闭跨场记忆')
        self.assertNotIn('优先考虑高抛', self.send(ask)['text'])


class TeePreferenceTests(StyleFixture, unittest.TestCase):
    protocol_version = 55

    def test_declared_leave_distance_changes_offer_without_choosing(self):
        self.onboard()
        for text in ('1', '轻松打球', '开始球局'):
            self.send(text)
        self.gps('tee')
        for text in ('怎么打', '220', '200'):
            result = self.send(text)
        self.assertEqual(len(result['tee_routes']), 2)
        conservative = result['tee_routes'][0]
        target = round(conservative['remaining_yards'] * .9144)
        self.send(f'我喜欢下一杆留{target}米')
        result = self.send('怎么打')
        self.assertIn(f'{target}米', result['tee_preference_note'])
        self.assertIn('保守方案', result['tee_preference_note'])
        self.assertEqual(self.e.state('j')['journey']['consultation']['phase'], 'tee_options')
        self.send('忘记下一杆距离偏好')
        self.send('开球我通常选保守路线')
        self.gps('tee')
        self.assertIn('开球习惯', self.send('怎么打')['tee_preference_note'])
        self.assertEqual(self.e.state('j'), self.e.replay('j'))

    def test_preference_does_not_promote_route_with_known_hazard(self):
        from journey_style_preferences import tee_note

        journey = {'profile': {'shot_style_preferences': {
            'tee': {'value': 'aggressive'},
            'leave_distance': {'value': 90, 'unit': '码'},
        }}}
        routes = [
            {'kind': 'conservative', 'remaining_yards': 150, 'risk': '落区更宽'},
            {'kind': 'aggressive', 'remaining_yards': 90, 'risk': '水体，要留意偏向障碍的失误'},
        ]
        self.assertIsNone(tee_note(journey, routes))


class SwingPreferenceTests(StyleFixture, unittest.TestCase):
    protocol_version = 57

    def test_declaration_change_and_clear(self):
        self.at_fairway()
        for method in ('短一号正常挥', '长一号收着打'):
            self.assertIn(method, self.send('两支杆之间我通常'+method)['text'])
            profile = self.e.state('j')['journey']['profile']
            self.assertEqual(profile['shot_style_preferences']['between_clubs']['value'], method)
        self.send('忘记两支杆之间的偏好')
        self.assertNotIn('between_clubs', self.e.state('j')['journey']['profile']['shot_style_preferences'])
        self.assertEqual(self.e.state('j'), self.e.replay('j'))
