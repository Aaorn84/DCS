import unittest

import test_journey_recovery as base
from journey_habits import DISABLE, ENABLE


class JourneyHabitsTests(unittest.TestCase):
    protocol_version = 53
    setUp = base.JourneyRecoveryTests.setUp
    tearDown = base.JourneyRecoveryTests.tearDown
    send = base.JourneyRecoveryTests.send
    gps = base.JourneyRecoveryTests.gps
    onboard = base.JourneyRecoveryTests.onboard
    at_fairway = base.JourneyRecoveryTests.at_fairway

    def ask_again(self):
        self.send(type='simulation_hole', hole=1)
        self.gps('fairway')
        return self.send('还有多少')['text']

    def test_three_explicit_skips_offer_and_user_can_reverse(self):
        self.at_fairway()
        self.assertNotIn(DISABLE, self.send('跳过')['text'])
        self.ask_again()
        self.assertNotIn(DISABLE, self.send('先不记')['text'])
        self.ask_again()
        self.assertIn(DISABLE, self.send('跳过。')['text'])
        self.assertIn('刚才那杆用的什么杆', self.ask_again())
        self.send(DISABLE)
        self.assertNotIn('刚才那杆用的什么杆', self.ask_again())
        self.send('结束球局')
        self.send('确认结束')
        self.send('先不聊')
        self.send(type='next_round')
        self.assertFalse(self.e.state('j')['journey']['profile']['shot_recording']['value'])
        for text in ('东莞凤凰山（A+B蓝台演示）', '蓝台', '1', '轻松打球', '开始球局'):
            self.send(text)
        self.send(ENABLE)
        self.assertIn('刚才那杆用的什么杆', self.ask_again())
        self.assertEqual(self.e.state('j'), self.e.replay('j'))

    def test_unknown_and_revoked_memory_do_not_count(self):
        self.at_fairway()
        self.send('不知道')
        self.ask_again()
        self.send('跳过')
        self.assertEqual(self.e.state('j')['journey']['previous_club_skip_count'], 1)
        self.send('关闭跨场记忆')
        self.ask_again()
        self.send('跳过')
        self.assertNotIn('previous_club_skip_count', self.e.state('j')['journey'])
