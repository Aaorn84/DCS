import unittest
from unittest.mock import patch

from test_journey_style_preferences import StyleFixture


class PerformanceFollowupTests(StyleFixture, unittest.TestCase):
    protocol_version = 65

    def test_putt_same_grade_only(self):
        self.at_fairway()
        for index, outcome in enumerate(('推短2米', '推短1米', '推过1米')):
            with patch('putt_performance.scope', return_value=[str(index % 2), 'map', index+1]):
                self.assertIn('已记下', self.send('长推实绩，起推12米，上坡，'+outcome)['text'])
        self.assertIn('有2次推短', self.send('长推12米，上坡，怎么推？')['text'])
        self.assertNotIn('有2次推短', self.send('长推12米，下坡，怎么推？')['text'])

    def test_flight_uses_low_end_for_current_lie(self):
        self.at_fairway()
        for club, values in [('7铁', (125, 135, 145)), ('6铁', (142, 150, 155))]:
            for index, carry in enumerate(values):
                with patch('lie_performance.scope', return_value=[str(index % 2), 'map', index+1]):
                    self.send(f'球位实绩，长草，用{club}，Carry{carry}码')
        text = self.send('飞越比较，长草，飞越至少132码，用7铁或6铁，怎么选？')['text']
        self.assertIn('记录中有球未留出飞越余量', text)
        self.assertIn('先考虑6号铁', text)
        self.assertIn('实绩不足', self.send('飞越比较，球道，飞越至少132码，用7铁或6铁，怎么选？')['text'])
