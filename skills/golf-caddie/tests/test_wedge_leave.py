import unittest
from unittest.mock import patch

from test_journey_style_preferences import StyleFixture
from wedge_leave import suggested_leave


class WedgeLeaveTests(StyleFixture, unittest.TestCase):
    protocol_version = 60

    def test_learns_across_rounds_and_manual_preference_wins(self):
        self.at_fairway()
        for round_id, hole, finish in [('one', 1, 6), ('one', 1, 5), ('one', 2, 9), ('two', 1, 4)]:
            with patch('wedge_leave.scope', return_value=[round_id, 'map', hole]):
                self.send(f'短杆实绩，起杆离旗75码，一杆后离旗{finish}码')
            if round_id == 'one':
                self.assertIsNone(suggested_leave(self.e.state('j')['journey']))
        self.assertIn('参考留75码', self.send('我擅长留多少码？')['text'])
        self.send('我喜欢下一杆留90码')
        self.assertIn('设定的留距是90码', self.send('我擅长留多少码？')['text'])
        self.send('关闭跨场记忆')
        self.assertNotIn('wedge_leave_reports', self.e.state('j')['journey'])

    def test_prefers_band_with_better_median_result(self):
        rows = [
            {'scope': [str(i % 2), 'map', i], 'start_yd': start, 'finish_yd': finish}
            for i, (start, finish) in enumerate([(75, 3), (75, 16), (75, 5), (90, 1), (90, 13), (90, 15)])
        ]
        self.assertEqual(suggested_leave({'wedge_leave_reports': rows}), {'value': 75, 'unit': '码'})


class WedgeCombinationTests(StyleFixture, unittest.TestCase):
    protocol_version = 61

    def test_reports_feed_approach_candidate(self):
        from iron_estimates import present_iron_option

        self.at_fairway()
        for round_id, hole, finish in [('one', 1, 6), ('one', 2, 9), ('two', 1, 4)]:
            with patch('wedge_leave.scope', return_value=[round_id, 'map', hole]):
                reply = self.send(f'短杆实绩，起杆离旗75码，一杆后离旗{finish}码，用54度杆，半挥杆')
            self.assertIn('54度杆半挥杆', reply['text'])
        state = self.e.state('j')
        state['journey']['consultation'] = {'lie_report': '球道'}
        source = '到旗位约75码。建议用熟悉的短杆控制距离。'
        with patch('iron_estimates.fresh_position', return_value={'value': {}}):
            text, candidate = present_iron_option(state, source, 0, pin={
                'min_m': 74*.9144, 'max_m': 76*.9144,
            })
        self.assertIn('54度杆半挥杆', text)
        self.assertIn('中位数约6码', text)
        self.assertEqual(candidate['samples'], 3)


class GreensidePerformanceTests(StyleFixture, unittest.TestCase):
    protocol_version = 62

    def test_compares_comparable_outcomes_and_clears_on_revocation(self):
        self.at_fairway()
        self.send('果岭边我通常高抛')
        query = '果岭边，离旗15码，球位果岭边短草，两种打法都可用，怎么选？'
        for style, finishes in [('切滚', (2, 4, 3)), ('高抛', (6, 8, 7))]:
            for index, finish in enumerate(finishes):
                with patch('wedge_leave.scope', return_value=[str(index % 2), 'map', 1 + index + (3 if style == '高抛' else 0)]):
                    reply = self.send(f'短杆实绩，起杆离旗15码，一杆后离旗{finish}码，球位果岭边短草，两种打法都可用，用{style}')
                self.assertIn('已记下', reply['text'])
        reply = self.send(query)['text']
        self.assertIn('你平时偏好高抛', reply)
        self.assertIn('先考虑切滚', reply)
        self.assertIn('实绩还不足', self.send(query.replace('15码', '30码'))['text'])
        self.assertIn('实绩还不足', self.send(query.replace('果岭边短草', '球道'))['text'])
        self.send('关闭跨场记忆')
        self.assertNotIn('greenside_reports', self.e.state('j')['journey'])
