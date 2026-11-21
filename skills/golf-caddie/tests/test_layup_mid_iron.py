import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tee_strategy import layup_club_policy,layup_club_text
class MidIronLayupTests(unittest.TestCase):
 def policy(self,carry,width=45,hazards=(),crossing=None):
  profile={'seven':{'value':dict(distance=160,units='码',distance_type='carry')}}
  s={'journey':{'profile':profile},'evidence':{'map':{'data':{'holes':[{'number':1}]}}}}
  a=dict(course_evidence='map',hole=1,clubs={'seven':{'carry_yards':160},'three_wood':{'carry_yards':240}})
  r=dict(aim_point={},layup=dict(aim_point={},carry_yards=carry,crossing_m=crossing))
  with patch('tee_geometry.landing_space',return_value=dict(width_m=width*.9144,depth_m=30*.9144,hazards=list(hazards))):return layup_club_policy(s,a,r)
 def test_mid_iron_needs_no_wood_exception(self):
  self.assertEqual(self.policy(160),dict(allow_woods=False,long_club=False))
 def test_wood_requires_wide_deep_unobstructed_landing(self):
  self.assertTrue(self.policy(230)['allow_woods'])
  self.assertIsNone(self.policy(230,width=30))
  self.assertIsNone(self.policy(230,hazards=[dict(kind='bunker',distance_m=10)]))
  self.assertIsNone(self.policy(230,crossing=100))
 def test_wording_does_not_silently_select_wood(self):
  p={'three_wood':{'value':dict(distance=240,units='码',distance_type='carry')}}
  self.assertNotIn('3号木',layup_club_text(p,230,'码'))
  self.assertIn('3号木',layup_club_text(p,230,'码',allow_woods=True))
