import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hazard_route import green_crossing_advice
class BunkerClubTests(unittest.TestCase):
 def advice(self,lie,uses):
  state={'journey':{'profile':{'lofted_wedge_uses':{'value':uses}}}}
  line=dict(front_m=10*.9144,back_m=25*.9144,target_m=15*.9144,hazards={'bunker':5*.9144,'water':None,'ob':None},accuracy_m=1)
  with patch('hazard_route.landing_line',return_value=line):
   return green_crossing_advice(state,0,lie=lie,verify_playability=True,assess_lie=True)
 def test_short_bunker_uses_reported_58(self):
  result=self.advice('沙坑',{'58':'沙坑'})
  self.assertIn('58度杆',result['text']);self.assertIn('沙坑用途',result['text'])
  self.assertEqual('58度杆',result['option']['club'])
  self.assertNotIn('carry_yards',result['option'])
 def test_respects_other_reported_sand_club(self):
  self.assertEqual('56度杆',self.advice('沙坑',{'56':'沙坑'})['option']['club'])
 def test_rough_does_not_inherit_bunker_club(self):
  self.assertNotIn('58度杆',self.advice('长草',{'58':'沙坑'})['text'])
