import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tee_strategy import layup_risk_rank
class LayupRouteBalanceTests(unittest.TestCase):
 def rank(self,leave,width,hazards=(),narrow=False):
  point=dict(latitude=0,longitude=0)
  s=dict(facts={},evidence={'map':{'data':{'reference_simulation':True,'holes':[dict(number=1,objects=[dict(kind='green_center',**point)])]}}})
  a=dict(course_evidence='map',hole=1,clubs={'three_wood':{'carry_yards':240}})
  row=dict(aim_point=point,crossing_m=None,layup=dict(aim_point=point,crossing_m=None),leave_yards=leave)
  spaces=[dict(width_m=50,depth_m=30,hazards=[]),dict(width_m=width*.9144,depth_m=30,hazards=list(hazards)),dict(width_m=10 if narrow else 30,depth_m=20,hazards=[])]
  with patch('tee_geometry.landing_space',side_effect=spaces):return layup_risk_rank(s,a,row)
 def test_usable_forward_landing_beats_extremely_wide_short_layup(self):
  for narrow in (False,True):
   self.assertLess(self.rank(100,35,narrow=narrow),self.rank(180,61,narrow=narrow))
 def test_penalty_risk_still_matters(self):
  self.assertLess(self.rank(180,61),self.rank(100,35,[dict(kind='water',distance_m=3)]))
 def test_tiny_landing_does_not_win_just_by_advancing(self):
  self.assertLess(self.rank(180,61),self.rank(100,5))
