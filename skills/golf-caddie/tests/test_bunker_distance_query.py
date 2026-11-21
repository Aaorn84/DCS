import sys,unittest,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from bunker_distance_query import handle
class BunkerQueryTests(unittest.TestCase):
 def test_queries_are_readonly_and_report_edges(self):
  s={'facts':{'context.course_snapshot':{'value':'m','valid':True},'context.active_hole':{'value':1,'valid':True}},'evidence':{'m':{'data':{'holes':[{'number':1}]}}},'journey':{}}
  before=copy.deepcopy(s)
  polygons={'bunker':{'b':[[[0,.001],[.0001,.001],[.0001,.002],[0,.002],[0,.001]]]}}
  with patch('lie_position.fresh_position',return_value={'value':{'latitude':0,'longitude':0}}),patch('tee_geometry.mapped_polygons',return_value=polygons):
   for q in ('到沙坑多少码？','到沙坑多少','沙坑多远'):
    answer=handle(s,q,0);self.assertIn('近沿约122码',answer);self.assertIn('远沿约',answer)
  self.assertEqual(before,s)
 def test_unrelated_is_not_a_distance_query(self):
  self.assertIsNone(handle({},'打进沙坑了',0))
 def test_stale_position_requests_update(self):
  with patch('lie_position.fresh_position',return_value=None):self.assertIn('更新当前球位',handle({},'到沙坑多少',0))
