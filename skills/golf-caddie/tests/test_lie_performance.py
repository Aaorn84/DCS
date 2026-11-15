import unittest
from unittest.mock import patch

from test_journey_style_preferences import StyleFixture
from lie_performance import approach_context


class LiePerformanceTests(StyleFixture, unittest.TestCase):
    protocol_version = 64

    def test_same_club_keeps_lies_separate(self):
        self.at_fairway()
        for index, (lie, carry) in enumerate([
            ('球道', 150), ('球道', 160), ('球道', 155),
            ('长草', 125), ('长草', 145), ('长草', 135),
        ]):
            with patch('lie_performance.scope', return_value=[str(index % 2), 'map', index+1]):
                self.assertIn('已记下', self.send(f'球位实绩，{lie}，用7铁，Carry{carry}码')['text'])
        reply = self.send('7号铁在球道和长草的Carry多少？')['text']
        self.assertIn('中位数约155码，记录范围150到160码', reply)
        self.assertIn('中位数约135码，记录范围125到145码', reply)
        journey = self.e.state('j')['journey']
        journey['consultation'] = {'phase': 'plan', 'lie_report': '长草',
                                   'strategy_assessment': {'distance_m': 140*.9144}}
        note = approach_context(journey, '到果岭中心约140码。')
        self.assertIn('长草', note)
        self.assertIn('先脱困', note)
        self.assertNotIn('155码', note)
        self.send('关闭跨场记忆')
        self.assertNotIn('lie_carry_reports', self.e.state('j')['journey'])
