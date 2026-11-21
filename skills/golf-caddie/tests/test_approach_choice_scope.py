import sys,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from approach_dialogue import advise
class ApproachChoiceScopeTests(unittest.TestCase):
 def advice(self,distance,unit='码',seven=160):
  state={'facts':{},'evidence':{},'journey':{'round':{'id':'r'},'profile':{'seven':{'value':{'distance':seven,'units':unit,'distance_type':'carry'}}}}}
  with patch('approach_dialogue.detailed_advise',return_value={'text':'到果岭参考点约125码。','distance_m':distance*.9144}),patch('short_pin_distance.estimate',return_value=None),patch('hazard_route.green_crossing_advice',return_value={'text':'可考虑P杆。','option':{'club':'P杆'}}),patch('tee_strategy.actual_position_layup',return_value='这杆目标Carry约65码，预计下一杆约65码。') as layup:
   result=advise(state,dict(ball_position_report='user_confirmed',lie_report='球道'),time.time(),carry_crossing=True,verify_playability=True,compare_safety=True,assess_lie=True)
   return result,layup.call_count
 def test_125_yards_only_direct_attack(self):
  result,calls=self.advice(125)
  self.assertEqual(0,calls);self.assertNotIn('route_choices',result)
  self.assertIn('P杆',result['text']);self.assertNotIn('三上',result['text'])
 def test_seven_iron_boundary_is_inclusive(self):
  self.assertEqual(0,self.advice(160)[1])
 def test_meter_carry_converts_for_comparison(self):
  self.assertEqual(0,self.advice(150,unit='米',seven=150)[1])
 def test_long_approach_uses_current_shot_labels(self):
  result,calls=self.advice(200)
  self.assertEqual(1,calls)
  self.assertIn('直接攻果岭候选',result['text']);self.assertIn('过渡后攻果岭候选',result['text'])
  self.assertNotIn('两上',result['text']);self.assertNotIn('三上',result['text'])
