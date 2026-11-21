import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_stroke_consistency as support
from journey import view
from ball_rules import current
class ScoreGapTests(unittest.TestCase):
 protocol_version=111
 setUp=support.StrokeConsistencyTests.setUp
 tearDown=support.StrokeConsistencyTests.tearDown
 send=support.StrokeConsistencyTests.send
 onboard=support.StrokeConsistencyTests.onboard
 start=support.StrokeConsistencyTests.start
 point=support.StrokeConsistencyTests.point
 def test_four_strokes_two_putts_keeps_two_unknown_strokes(self):
  self.start();self.send('第4洞4杆，2推，0罚杆')
  state=self.e.state('j');rows=view(state)['round_records']['clubs']
  self.assertEqual([1,2,3,4],[row['stroke_number'] for row in rows])
  self.assertEqual([None,None,'推杆','推杆'],[row['club'] for row in rows])
  self.assertTrue(all(row['total_horizontal_m'] is None for row in rows))
  self.assertEqual([],current(state)['sequence'])
  self.assertEqual(state,self.e.replay('j'))
 def test_known_stroke_does_not_get_a_duplicate_placeholder(self):
  self.start();self.point();self.send('第4洞4杆，2推，0罚杆')
  rows=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual([1,2,3,4],[row['stroke_number'] for row in rows])
  self.assertEqual(1,sum(row['source']=='score_placeholder' for row in rows))
 def test_unknown_penalty_order_does_not_invent_ordinal(self):
  self.start()
  state=self.e.state('j');state['session']['draft']=dict(hole=4,total=5,putts=2,penalties=1,awaiting='penalties')
  rows=view(state)['round_records']['clubs']
  gaps=[row for row in rows if row['source']=='score_placeholder']
  self.assertEqual(2,len(gaps));self.assertTrue(all(row['stroke_number'] is None for row in gaps))
