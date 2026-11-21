"""Qualify rough and bunker approaches before selecting attack or recovery."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hazard_route import green_crossing_advice
from journey import view
from phoenix_demo import preview
import test_journey_recovery as support


class LieAdviceTests(unittest.TestCase):
    def advice(self,lie='长草',status=None,wedges=True):
        yard=.9144
        line=dict(front_m=109*yard,back_m=127*yard,target_m=120*yard,
                  hazards=dict(bunker=104*yard,water=None,ob=None),accuracy_m=2)
        profile={'seven':{'value':{'distance':160,'units':'码','distance_type':'carry'}}}
        if wedges:
            profile['lofted_wedge_ranges']={'value':{'52':{'low':110,'high':120,'units':'码'}}}
        with patch('hazard_route.landing_line',return_value=line):
            return green_crossing_advice({'journey':{'profile':profile}},0,lie=lie,
                verify_playability=True,assess_lie=True,lie_playability=status,pin_depth='中')

    def test_rough_asks_contact_before_deciding(self):
        advice=self.advice()
        self.assertIn('能干净触球',advice['text'])
        self.assertIn('lie_question',advice)
        self.assertNotIn('先把球送回',advice['text'])

    def test_clean_rough_can_attack_with_reported_wedge(self):
        advice=self.advice(status='clear')
        self.assertEqual('52度杆',advice['option']['club'])
        self.assertNotIn('先把球送回',advice['text'])

    def test_buried_rough_uses_recovery(self):
        advice=self.advice(status='blocked')
        self.assertIn('球埋得深',advice['text'])
        self.assertNotIn('option',advice)

    def test_clean_rough_missing_carry_asks_for_club(self):
        advice=self.advice(status='clear',wedges=False)
        self.assertIn('P杆',advice['text'])
        self.assertNotIn('missing_attack_carry',advice)
        self.assertNotIn('先找一段',advice['text'])

    def test_bunker_needs_lip_and_reliable_carry(self):
        self.assertIn('坑沿',self.advice(lie='沙坑')['text'])
        self.assertEqual('52度杆',self.advice(lie='沙坑',status='clear')['option']['club'])
        self.assertIn('58度杆',self.advice(lie='沙坑',status='blocked')['text'])

    def test_unknown_lie_asks_instead_of_ordering_recovery(self):
        advice=self.advice(lie='不清楚')
        self.assertIn('现场是球道',advice['text'])
        self.assertIn('lie_question',advice)
        self.assertNotIn('先把球送回',advice['text'])

    def test_unknown_contact_gives_conditional_choices(self):
        advice=self.advice(status='unknown')
        self.assertIn('若能干净触球',advice['text'])
        self.assertNotIn('lie_question',advice)


class LieJourneyTests(unittest.TestCase):
    protocol_version=109
    setUp=support.JourneyRecoveryTests.setUp
    tearDown=support.JourneyRecoveryTests.tearDown
    send=support.JourneyRecoveryTests.send
    onboard=support.JourneyRecoveryTests.onboard

    def start(self):
        self.onboard()
        for word in ('3','轻松打球','开始球局'):
            self.send(word)
        self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
        self.send(type='gps',data=dict(preview(3)['positions']['fairway'],simulation_source='map_click'))

    def test_rough_question_answer_reaches_attack_and_replay(self):
        self.start()
        self.send('52，110–120码')
        yard=.9144
        line=dict(front_m=109*yard,back_m=127*yard,target_m=120*yard,
                  hazards=dict(bunker=104*yard,water=None,ob=None),accuracy_m=2)
        with patch('hazard_route.landing_line',return_value=line):
            self.send('这杆怎么打')
            self.send('中旗偏左')
            question=self.send('长草')
            self.assertIn('能干净触球',question['text'])
            self.assertEqual('lie_detail',self.e.state('j')['journey']['consultation']['phase'])
            self.assertIn('浅草、能干净触球',view(self.e.state('j'))['choices'])
            self.assertIn('能干净触球',self.send('这杆怎么打')['text'])
            # A background fix does not discard the player's current-ball answer.
            self.send(type='gps',data=dict(preview(3)['positions']['fairway'],simulation_source='map_click',simulation_refresh=True))
            advice=self.send('浅草、能干净触球')['text']
            self.assertIn('52度杆',advice)
            self.assertNotIn('先把球送回',advice)
            self.assertEqual(self.e.state('j'),self.e.replay('j'))


    def test_clean_rough_can_supply_missing_single_wedge_carry(self):
        self.start()
        yard=.9144
        line=dict(front_m=109*yard,back_m=127*yard,target_m=120*yard,
                  hazards=dict(bunker=104*yard,water=None,ob=None),accuracy_m=2)
        with patch('hazard_route.landing_line',return_value=line):
            self.send('这杆怎么打')
            self.send('中旗偏左')
            self.send('长草')
            question=self.send('浅草、能干净触球')['text']
            self.assertIn('Carry',question)
            self.send(type='gps',data=dict(preview(3)['positions']['fairway'],simulation_source='map_click',simulation_refresh=True))
            self.send('52，115码')
            advice=self.send('这杆怎么打')['text']
            self.assertIn('52度杆',advice)
            ranges=self.e.state('j')['journey']['profile']['lofted_wedge_ranges']['value']
            self.assertEqual((115,115),(ranges['52']['low'],ranges['52']['high']))
            self.assertEqual(self.e.state('j'),self.e.replay('j'))


class WedgeUseJourneyTests(LieJourneyTests):
    protocol_version=111

    def test_sand_only_wedge_does_not_block_current_attack(self):
        self.start()
        yard=.9144
        line=dict(front_m=109*yard,back_m=127*yard,target_m=120*yard,
                  hazards=dict(bunker=108*yard,water=None,ob=None),accuracy_m=2)
        with patch('hazard_route.landing_line',return_value=line):
            self.send('这杆怎么打')
            self.send('中旗偏左')
            self.send('长草')
            self.send('浅草、能干净触球')
            reply=self.send('48，110码，52，0到85，58，沙坑')['text']
            self.assertIn('记下了',reply)
            reply=self.send('这杆怎么打')['text']
            self.assertIn('P杆',reply)
            self.assertNotIn('58度杆常用Carry范围是多少',reply)
            self.assertNotIn('可考虑48度杆',reply)
            profile=self.e.state('j')['journey']['profile']
            self.assertEqual('沙坑',profile['lofted_wedge_uses']['value']['58'])
            self.assertNotIn('58',profile['lofted_wedge_ranges']['value'])
            self.assertEqual(self.e.state('j'),self.e.replay('j'))
