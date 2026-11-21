import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from approach_dialogue import advise
class LongApproachRouteTests(unittest.TestCase):
 def test_no_crossing_hazard_still_evaluates_roll_and_iron_layup(self):
  s={'facts':{},'evidence':{},'journey':{'profile':{'seven':{'value':dict(distance=160,units='码',distance_type='carry')}}}}
  c=dict(ball_position_report='user_confirmed',lie_report='球道')
  with patch('approach_dialogue.detailed_advise',return_value=dict(text='没有Carry覆盖250码。',distance_m=250*.9144)),patch('short_pin_distance.estimate',return_value=None),patch('hazard_route.green_crossing_advice',return_value=None),patch('tee_strategy.actual_position_layup',return_value='过渡用杆可考虑7号铁。') as layup,patch('tee_strategy.actual_position_roll_in',side_effect=[None,dict(text='3号木Carry240码，需滚动10码，现场确认前沿通畅。')]) as attack:
   r=advise(s,c,0,carry_crossing=True,allow_roll_in=True,compare_safety=True,assess_lie=True)
  self.assertIn('3号木',r['text']);self.assertIn('7号铁',r['text']);self.assertEqual(attack.call_count,2)
  layup.assert_called_once_with(s,0,compare_safety=True,allow_other_par=True)
