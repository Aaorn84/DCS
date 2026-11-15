import unittest,sys,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from short_pin_distance import estimate,present_short_pin
from round_state import canonical
class ShortPinTests(unittest.TestCase):
 def setUp(self):
  self.key=['round','map',1]
  self.state={'journey':{'pin_locations':{canonical(self.key):{'status':'complete','depth':'前','side':'中'}}},'evidence':{'map':{'data':{'holes':[{'number':1,'tee_bbox':[-.0001,-.0021,.0001,-.0019],'objects':[{'kind':'green_center','longitude':0,'latitude':0}],'surface_zones':[{'surface':'green','verified':True,'source':'fixture','geometry':{'type':'Polygon','coordinates':[[[-.0001,-.00015],[.0001,-.00015],[.0001,.00015],[-.0001,.00015],[-.0001,-.00015]]]}}]}]}}}}
  self.pos={'value':{'longitude':0,'latitude':-.0003,'accuracy_m':2}}
  self.patches=[patch('short_pin_distance.fresh_position',return_value=self.pos),patch('short_pin_distance.scope',return_value=self.key),patch('short_pin_distance.fact_value',side_effect=lambda s,k:'map' if k=='context.course_snapshot' else 1)]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def test_front_and_back_use_geometry_without_mutation(self):
  before=copy.deepcopy(self.state);front=estimate(self.state,0);self.assertEqual(self.state,before);self.state['journey']['pin_locations'][canonical(self.key)]['depth']='后';back=estimate(self.state,0);self.assertLess(front['max_m'],back['max_m']);self.assertLess(front['min_m'],back['min_m']);self.assertTrue(front['not_for_learning'])
 def test_reply_range_and_units(self):
  text,out=present_short_pin(self.state,'从当前设备位置到果岭参考点约35码，不是旗杆距离。',0);self.assertIn('前旗',text);self.assertNotIn('–',text);self.assertIn('到旗位约',text);self.assertIn('区域估算',text);self.assertNotIn('参考点约35',text)
  text,_=present_short_pin(self.state,'到果岭中心约30米。',0);self.assertIn('米',text)
 def test_missing_contour_or_unknown_pin_falls_back(self):
  self.state['journey']['pin_locations'][canonical(self.key)]['depth']='unknown';self.assertIsNone(estimate(self.state,0))
  self.state['journey']['pin_locations'][canonical(self.key)]['depth']='前';self.state['evidence']['map']['data']['holes'][0]['surface_zones']=[];self.assertIsNone(estimate(self.state,0))
 def test_not_applied_outside_short_game_or_other_hole(self):
  self.pos['value']['latitude']=-.001;self.assertIsNone(estimate(self.state,0));self.pos['value']['latitude']=-.0003;self.key[2]=2;self.assertIsNone(estimate(self.state,0))
