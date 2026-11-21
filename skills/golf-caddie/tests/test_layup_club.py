import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tee_strategy import layup_club_text
class LayupClubTests(unittest.TestCase):
 def profile(self):
  return {'seven':{'value':{'distance':160,'units':'码','distance_type':'carry'}},'lofted_wedge_ranges':{'value':{'48':{'low':110,'high':110,'units':'码'},'52':{'low':0,'high':85,'units':'码'}}}}
 def test_105_yard_layup_uses_48_with_control(self):
  text=layup_club_text(self.profile(),105,'码')
  self.assertIn('48度杆',text);self.assertIn('控制到约105码',text);self.assertNotIn('52度杆',text)
 def test_reported_range_covers_target(self):
  text=layup_club_text(self.profile(),75,'码')
  self.assertIn('52度杆',text);self.assertIn('已知杆距范围',text)
 def test_estimated_pw_is_labelled(self):
  p=self.profile();p.pop('lofted_wedge_ranges')
  text=layup_club_text(p,125,'码')
  self.assertIn('P杆',text);self.assertIn('暂估',text)
 def test_units(self):
  self.assertIn('95米',layup_club_text(self.profile(),105,'米'))
 def test_unknown_bag_requests_carry(self):
  self.assertIn('请补充',layup_club_text({},105,'码'))
