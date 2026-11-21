"""A flag-front preference must not exclude a checked, deeper green landing."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hazard_route import green_crossing_advice


class CarryWindowTests(unittest.TestCase):
    def advice(self,deeper_hazard=None, middle=False, back=175, lie='球道'):
        yard=.9144
        line=dict(front_m=153*yard,back_m=back*yard,target_m=161*yard,
                  hazards=dict(bunker=149*yard,water=None,ob=None),accuracy_m=2)
        deeper={**line,'hazards':{**line['hazards'],'water':deeper_hazard}}
        state={'journey':{'profile':{
            'seven':{'value':{'distance':160,'units':'码','distance_type':'carry'}}}}}
        with patch('hazard_route.landing_line',side_effect=lambda *a,**kw:deeper if 'stop_distance_m' in kw else line),              patch('tee_strategy.actual_position_roll_in',return_value=None),              patch('tee_strategy.actual_position_layup',return_value=''):
            return green_crossing_advice(state,0,lie=lie,verify_playability=True,
                                         allow_roll_in=True,compare_safety=True,pin_depth='中' if middle else None)

    def test_reported_seven_iron_can_land_beyond_short_of_flag_window(self):
        advice=self.advice()
        self.assertEqual('7号铁',advice['option']['club'])
        self.assertIn('Carry约160码',advice['text'])
        self.assertNotIn('过渡',advice['text'])

    def test_deeper_hazard_requires_confirmation_instead_of_claiming_attack(self):
        advice=self.advice(deeper_hazard=165*.9144)
        self.assertNotIn('option',advice)
        self.assertEqual('7号铁',advice['nearby_club']['club'])
        self.assertIn('需要你确认',advice['text'])


    def test_middle_pin_includes_pin_high_and_slightly_longer_club(self):
        advice=self.advice(middle=True,back=190)
        self.assertEqual('7号铁',advice['option']['club'])
        self.assertIn('7号铁Carry约160码',advice['text'])
        self.assertIn('6号铁Carry约170码',advice['text'])
        self.assertIn('按7号铁杆距暂估',advice['text'])
        self.assertNotIn('156–158码',advice['text'])

    def test_middle_pin_works_from_par_three_tee(self):
        advice=self.advice(middle=True,lie='发球台')
        self.assertEqual('7号铁',advice['option']['club'])
        self.assertNotIn('过渡',advice['text'])

    def test_middle_pin_keeps_back_edge_margin(self):
        advice=self.advice(middle=True,back=165)
        self.assertNotIn('6号铁Carry约170码',advice['text'])
        self.assertNotIn('option',advice)


import test_journey_recovery as support
from phoenix_demo import preview


class MiddlePinJourneyTests(unittest.TestCase):
    protocol_version=108
    setUp=support.JourneyRecoveryTests.setUp
    tearDown=support.JourneyRecoveryTests.tearDown
    send=support.JourneyRecoveryTests.send
    onboard=support.JourneyRecoveryTests.onboard

    def test_middle_pin_from_tee_reaches_expanded_carry_window(self):
        self.onboard()
        for word in ('2','轻松打球','开始球局'):
            self.send(word)
        self.send(type='gps',data=dict(preview(2)['positions']['tee'],simulation_source='map_click'))
        yard=.9144
        line=dict(front_m=153*yard,back_m=190*yard,target_m=161*yard,
                  hazards=dict(bunker=149*yard,water=None,ob=None),accuracy_m=2)
        with patch('hazard_route.landing_line',return_value=line):
            self.send('这杆怎么打')
            advice=self.send('中旗偏左')['text']
            self.assertIn('中旗可把平旗和稍长的Carry纳入候选',advice)
            self.assertIn('7号铁Carry约160码',advice)
            self.assertIn('6号铁Carry约170码',advice)
            self.assertNotIn('现有杆距未匹配',advice)
            self.assertEqual(self.e.state('j'),self.e.replay('j'))
