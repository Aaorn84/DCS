import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from shot_club_advice import recommendation,supplement
from hazard_route import green_crossing_advice
class ShotClubAdviceTests(unittest.TestCase):
 def profile(self):
  return {'seven':{'value':{'distance':160,'units':'码','distance_type':'carry'}},'lofted_wedge_ranges':{'value':{'48':{'low':110,'high':110,'units':'码'},'52':{'low':0,'high':85,'units':'码'}}},'lofted_wedge_uses':{'value':{'58':'沙坑'}}}
 def test_short_pitch_matches_reported_range(self):
  self.assertIn('52度杆',recommendation(self.profile(),target_yards=15,lie='长草'))
 def test_controlled_layup_names_club_and_caveat(self):
  text=recommendation(self.profile(),target_yards=105)
  self.assertIn('48度杆',text);self.assertIn('熟悉这个挥幅',text)
 def test_recovery_uses_purpose_not_attack_distance(self):
  text=recommendation(self.profile(),lie='沙坑',target_yards=170)
  self.assertIn('58度杆',text);self.assertIn('先出沙',text);self.assertNotIn('170',text)
 def test_chip_and_recovery_without_carry_are_conditional(self):
  self.assertIn('P杆',recommendation(self.profile(),purpose='chip'))
  self.assertIn('52度杆',recommendation(self.profile(),lie='长草'))
  self.assertIn('请告诉我',recommendation({},lie='长草'))
 def test_supplement_preserves_question_and_existing_choice(self):
  s={'journey':{'profile':self.profile()}}
  for text in ('球埋得深吗？','可考虑48度杆，目标Carry105码。'):
   self.assertEqual(text,supplement(s,text,lie='长草'))
  self.assertIn('52度杆',supplement(s,'用熟悉的挖起杆抛切，Carry约15码。',lie='长草'))
 def test_bunker_use_not_applied_to_rough(self):
  self.assertNotIn('58度杆',recommendation(self.profile(),lie='长草'))
 def test_short_rough_crossing_names_club(self):
  s={'journey':{'profile':self.profile()}}
  line=dict(front_m=10*.9144,back_m=25*.9144,target_m=15*.9144,hazards={'bunker':5*.9144,'water':None,'ob':None},accuracy_m=1)
  with patch('hazard_route.landing_line',return_value=line):
   result=green_crossing_advice(s,0,lie='长草',verify_playability=True,assess_lie=True)
  self.assertIn('52度杆',result['text'])
