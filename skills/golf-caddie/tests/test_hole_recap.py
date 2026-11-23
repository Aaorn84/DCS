import sys,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_round_technical_stats as support
from shot_review_evidence import replay_origin_conflicts
from hole_recap import review
class HoleRecapTests(unittest.TestCase):
 def state(self):
  s,rows,pars,f=support.RoundTechnicalStatsTests().fixture()
  s['journey']['profile']={};f['scope']=['r','map',1];f['pending']=None
  first,second=f['sequence'];first.update(club='一号木',distance_m=223.0);second.update(club='一号木',distance_m=61.0)
  f['sequence'].insert(1,dict(kind='penalty',id='penalty',incident_id='incident',ball_id='original',amount=1))
  f['incidents']=[dict(id='incident',shot_id='a',cause='water',status='active',phase='closed',option='stroke_distance',origin=copy.deepcopy(first['origin']),completed_sequence_count=2)]
  for key,value in dict(total=5,putts=2,penalties=1).items():s['facts'][f'holes.1.{key}']=dict(value=value,valid=True)
  return s,f
 def test_recap_names_real_incident_and_explains_record_conflict(self):
  s,f=self.state();old=copy.deepcopy(s);text=review(s,1)
  self.assertIn('第1杆使用一号木确认下水',text);self.assertIn('回上一杆位置重打',text);self.assertIn('第3杆的数据需要先核对',text);self.assertIn('暂不用于评价',text);self.assertIn('最后以2推收尾',text)
  self.assertNotIn('发生罚杆那一杆的球位',text);self.assertNotIn('确认出界',text);self.assertEqual(s,old)
 def test_correct_replay_origin_has_no_false_distance_conflict(self):
  s,f=self.state();f['sequence'][2]['origin']=copy.deepcopy(f['sequence'][0]['origin']);self.assertEqual(replay_origin_conflicts(f),{});self.assertNotIn('第3杆的数据需要先核对',review(s,1))
 def test_back_on_line_drop_is_not_treated_as_tee_replay(self):
  s,f=self.state();f['incidents'][0]['option']='back_on_line';self.assertEqual(replay_origin_conflicts(f),{});self.assertIn('向后延线救济',review(s,1))
 def test_cancelled_incident_is_not_reported_as_confirmed_water(self):
  s,f=self.state();f['incidents'][0]['status']='cancelled';self.assertNotIn('确认下水',review(s,1));self.assertIn('事故记录未能对应',review(s,1))
 def test_provisional_promotion_does_not_require_next_shot_back_at_tee(self):
  s,f=self.state();f['incidents'][0]['promoted']=True;self.assertEqual(replay_origin_conflicts(f),{})
 def test_bad_start_is_not_learned_as_future_strategy_evidence(self):
  from hole_history import archive_current,records
  s,f=self.state();j=s['journey'];j['memory_allowed']=True;j['round'].update(course='course',tee='蓝台',finished=True);j['history']=[dict(round=copy.deepcopy(j['round']))]
  archive_current(s);rows=j['history'][0]['hole_history']['1']['shots'];self.assertFalse(rows[1]['distance_valid'])
  j['round']=dict(j['round'],id='next',finished=False);history=records(s,1);invalid=next(row for row in history if row['id']==rows[1]['id']);self.assertFalse(invalid['distance_valid'])
