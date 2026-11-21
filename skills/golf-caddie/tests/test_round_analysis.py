import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_analysis import analyze,describe
class RoundAnalysisTests(unittest.TestCase):
 def state(self):
  s={'facts':{'context.course_snapshot':{'value':'map','valid':True}},'evidence':{'map':{'data':{'holes':[]}}}}
  for hole,par,total,putts in [(1,3,1,0),(2,4,3,1),(3,5,5,2),(4,4,5,3),(5,3,5,None)]:
   s['evidence']['map']['data']['holes'].append(dict(number=hole,par=par))
   for k,v in dict(total=total,putts=putts,penalties=0).items():s['facts'][f'holes.{hole}.{k}']={'value':v,'valid':True}
  return s
 def test_score_distribution_and_actual_par(self):
  a=analyze(self.state());self.assertEqual(a['to_par'],0);self.assertEqual(a['par_coverage'],5)
  self.assertEqual(a['distribution'],dict(albatross_or_better=0,eagle=1,birdie=1,par=1,bogey=1,double_bogey_plus=1))
  self.assertEqual(a['hole_types'][0]['average'],3);self.assertEqual(a['hole_types'][1]['average'],4);self.assertEqual(a['hole_types'][2]['average'],5)
 def test_putt_average_excludes_unknown_not_zero(self):
  a=analyze(self.state());self.assertEqual(a['putting']['known_holes'],4);self.assertEqual(a['putting']['average'],1.5);self.assertEqual(a['putting']['three_putt_holes'],1)
 def test_scorecard_does_not_invent_technical_metrics_or_sg(self):
  a=analyze(self.state());self.assertIsNone(a['technical']['gir']['value']);self.assertIsNone(a['technical']['fir']['value']);self.assertNotIn('strokes_gained',a);self.assertNotIn('SG',describe(self.state()));self.assertNotIn('期望杆数基准',describe(self.state()))
 def test_unknown_par_uses_only_matched_holes(self):
  s=self.state();s['evidence']['map']['data']['holes']=[];a=analyze(s);self.assertIsNone(a['to_par']);self.assertEqual(a['par_coverage'],0)
 def test_unconfirmed_score_is_excluded(self):
  s=self.state();s['facts']['holes.5.total']['valid']=False;self.assertEqual(analyze(s)['confirmed_holes'],4)
