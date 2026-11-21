import sys,copy,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tee_club_query import parse,handle
class TeeClubQueryTests(unittest.TestCase):
 def test_common_questions(self):
  for text in ('1号木可以过沙吗？','1号木开球可以吗？','一号木可以开球吗','用3号木能飞过沙坑吗','5号木可不可以开球'):
   with self.subTest(text=text):self.assertIsNotNone(parse(text))
  for text in ('一号木','好，1号木','上一杆用了1号木','1号木260码'):self.assertIsNone(parse(text))
 def state(self):
  return {'journey':{'profile':{},'consultation':{'phase':'tee_commit','suggestion':{'club':'5号木'}}}}
 def test_driver_feasibility_is_read_only(self):
  s=self.state();before=copy.deepcopy(s)
  a={'par':4,'clubs':{'driver':{'label':'一号木','carry_yards':260}}}
  target={'width_m':28*.9144,'crossing_m':200*.9144}
  with patch('tee_strategy.analyze',return_value=a),patch('tee_geometry.tee_targets',return_value=[target]),patch('tee_strategy.aiming_text',return_value='右侧沙坑左边的球道'),patch('tee_strategy.crossing_text',return_value='沙坑远沿约200码。'):
   text=handle(s,'1号木可以过沙吗？',0)
  self.assertIn('一号木',text);self.assertIn('28码',text);self.assertIn('60码',text)
  self.assertEqual(before,s)
 def test_unknown_carry_requests_data(self):
  with patch('tee_strategy.analyze',return_value={'par':4,'clubs':{}}):
   self.assertIn('已知Carry',handle(self.state(),'1号木开球可以吗？',0))
 def test_stale_position_does_not_commit(self):
  with patch('tee_strategy.analyze',return_value=None):
   self.assertIn('更新发球台位置',handle(self.state(),'1号木开球可以吗？',0))
 def test_no_candidate_does_not_claim_safe(self):
  with patch('tee_strategy.analyze',return_value={'par':4,'clubs':{'driver':{'label':'一号木','carry_yards':260}}}),patch('tee_geometry.tee_targets',return_value=[]):
   self.assertIn('没有匹配',handle(self.state(),'1号木开球可以吗？',0))
 def test_side_bunker_query_still_answers_clearance(self):
  s=self.state();a={'par':4,'clubs':{'driver':{'label':'一号木','carry_yards':260}}}
  target={'width_m':23*.9144,'crossing_m':None}
  with patch('tee_strategy.analyze',return_value=a),patch('tee_geometry.tee_targets',return_value=[target]),patch('tee_strategy.aiming_text',return_value='沙坑左边球道'),patch('tee_strategy.crossing_text',return_value=''),patch('tee_club_query.bunker_clearance',return_value='沙坑远沿约251码，余量约9码，不能保证过沙。'):
   text=handle(s,'1号木可以过沙吗',0)
  self.assertIn('251码',text);self.assertIn('9码',text);self.assertNotIn('这支杆被排除',text)
