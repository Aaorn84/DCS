import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hazard_route import green_crossing_advice
class UnreachableAttackTests(unittest.TestCase):
 def test_driver_cannot_cover_fairway_attack(self):
  state={'journey':{'profile':{'seven':{'value':dict(distance=160,units='码',distance_type='carry')},'driver':{'value':dict(distance=260,units='码',distance_type='carry')},'three_wood':{'value':dict(distance=240,units='码',distance_type='carry')}}}}
  line=dict(front_m=250*.9144,back_m=270*.9144,target_m=260*.9144,accuracy_m=1,hazards={'bunker':244*.9144,'water':None,'ob':None})
  with patch('hazard_route.landing_line',return_value=line),patch('tee_strategy.actual_position_roll_in',return_value=None),patch('tee_strategy.actual_position_layup') as layup:
   result=green_crossing_advice(state,0,lie='球道',verify_playability=True,assess_lie=True,compare_safety=True)
  self.assertTrue(result['attack_unreachable']);self.assertFalse(result.get('attack_candidate'));self.assertNotIn('需要Carry',result['text']);self.assertNotIn('option',result);layup.assert_not_called()
