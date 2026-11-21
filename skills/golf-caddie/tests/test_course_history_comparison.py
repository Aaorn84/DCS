import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from course_history_comparison import compare
class CourseHistoryComparisonTests(unittest.TestCase):
 def scores(self,total):return [dict(hole=i,total=4 if i<18 else total-68,putts=2,penalties=0) for i in range(1,19)]
 def state(self):
  s=dict(facts={},evidence={},journey=dict(round=dict(id='r3',course='course-a',tee='蓝台',finished=True),history=[],memory_allowed=True))
  for row in self.scores(82):s['facts'][f'holes.{row["hole"]}.total']=dict(value=row['total'],valid=True)
  return s
 def entry(self,id,total=80,course='course-a',tee='蓝Tee'):
  return dict(round=dict(id=id,course=course,tee=tee,finished=True),scores=self.scores(total))
 def test_best_average_and_self_exclusion_without_mutation(self):
  s=self.state();s['journey']['history']=[self.entry('r1',80),self.entry('r2',90),self.entry('r3',82)];before=copy.deepcopy(s);r=compare(s)
  self.assertEqual((r['best'],r['average'],r['rounds']),(80,85,2));self.assertIn('比最好成绩多2杆',r['text']);self.assertIn('比历史平均少3杆',r['text']);self.assertEqual(s,before)
 def test_no_history_excluding_current_means_first_record(self):
  s=self.state();s['journey']['history']=[self.entry('r3',82),self.entry('other',79,course='other')];self.assertEqual(compare(s)['status'],'first_record')
 def test_other_tee_and_incomplete_round_do_not_compare(self):
  s=self.state();short=self.entry('r1');short['scores'].pop();s['journey']['history']=[short,self.entry('r2',75,tee='红台')];self.assertEqual(compare(s)['status'],'no_comparable_rounds')
 def test_partial_current_round_does_not_compare_to_full_round(self):
  s=self.state();s['facts'].pop('holes.18.total');s['journey']['history']=[self.entry('r1')];self.assertEqual(compare(s)['status'],'incomplete_current')
 def test_changed_course_metadata_is_not_comparable(self):
  s=self.state();entry=self.entry('r1');entry['course_basis']={'1':{'par':5}};s['journey']['history']=[entry];self.assertEqual(compare(s)['status'],'no_comparable_rounds')
 def test_duplicate_historical_round_counted_once(self):
  s=self.state();s['journey']['history']=[self.entry('r1'),self.entry('r1')];self.assertEqual(compare(s)['rounds'],1)
 def test_memory_preference_respected(self):
  s=self.state();s['journey']['history']=[self.entry('r1')];s['journey']['memory_allowed']=False;self.assertEqual(compare(s)['status'],'memory_disabled')
