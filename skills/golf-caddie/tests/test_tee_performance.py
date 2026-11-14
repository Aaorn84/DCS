import unittest
from unittest.mock import patch

from test_journey_style_preferences import StyleFixture
from tee_performance import comparison


class TeePerformanceTests(StyleFixture, unittest.TestCase):
    protocol_version = 63

    def test_comparison_uses_club_specific_reports_and_route_side(self):
        self.at_fairway()
        routes = [
            {'kind': 'conservative', 'club_key': 'three_wood', 'club': '3号木'},
            {'kind': 'aggressive', 'club_key': 'driver', 'club': '一号木'},
        ]
        details = {'aggressive': {'width_yards': 40, 'bunker': {'side': '右侧'}}}
        for index, (club, miss) in enumerate([
            ('一号木', '偏右25码'), ('一号木', '偏右30码'), ('一号木', '打直'),
            ('3号木', '偏左5码'), ('3号木', '打直'), ('3号木', '打直'),
        ]):
            with patch('tee_performance.scope', return_value=[str(index % 2), 'map', index+1]):
                self.assertIn('已记下', self.send(f'开球实绩，用{club}，{miss}')['text'])
        journey = self.e.state('j')['journey']
        note = comparison(journey, routes, details)
        self.assertIn('3号木，你报告的3次开球中，偏左1次', note)
        self.assertIn('一号木，你报告的3次开球中，偏右2次', note)
        self.assertIn('右侧有沙坑', note)
        self.assertIn('先看保守路线', note)
        self.assertNotIn('先看保守路线', comparison(journey, routes, {}))
        self.send('关闭跨场记忆')
        self.assertNotIn('tee_performance', self.e.state('j')['journey'])
