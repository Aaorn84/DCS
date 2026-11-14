import unittest

from test_journey_style_preferences import StyleFixture


class TeeClubFallbackTests(StyleFixture, unittest.TestCase):
    protocol_version = 66

    def test_tee_plan_fills_club_and_explicit_correction_wins(self):
        self.onboard()
        for text in ('1', '轻松打球', '开始球局'):
            self.send(text)
        self.gps('tee')
        for text in ('怎么打', '220', '200', '一号木'):
            self.send(text)
        self.gps('fairway')
        self.assertNotIn('刚才那杆用的什么杆', self.send('还有多少')['text'])
        journey = self.e.state('j')['journey']
        self.assertEqual(next(iter(journey['previous_club_reports'].values()))['source'], 'selected_tee_plan')
        self.assertFalse(journey.get('confirmed_shot_distances'))
        self.send('上一杆打了多少')
        self.send('是的')
        row = self.e.state('j')['journey']['confirmed_shot_distances'][-1]
        self.assertEqual(row['club_source'], 'selected_tee_plan')
        self.send('刚才换了3号木')
        row = self.e.state('j')['journey']['confirmed_shot_distances'][-1]
        self.assertEqual((row['club'], row['club_source']), ('3号木', 'user_report'))
        self.assertEqual(self.e.state('j'), self.e.replay('j'))
