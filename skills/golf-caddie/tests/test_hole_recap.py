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
  from hole_history import archive_current,assess
  s,f=self.state();j=s['journey'];j['memory_allowed']=True;j['round'].update(course='course',tee='蓝台',finished=True);j['history']=[dict(round=copy.deepcopy(j['round']))]
  archive_current(s);rows=j['history'][0]['hole_history']['1']['shots'];self.assertFalse(rows[1]['distance_valid'])
  j['round']=dict(j['round'],id='next',finished=False);a=assess(s,1,rows[1]['origin'],rows[1]['landing'],'一号木');self.assertEqual(a['samples'],0)

class ConcreteRecapOptionsTests(unittest.TestCase):
 def fixture(self):
  from unittest.mock import patch
  def point(y):return dict(latitude=y*.9144/111195,longitude=0,accuracy_m=0)
  hole=dict(number=1,par=5,objects=[dict(point(400),kind='green_center')])
  s=dict(facts={'context.course_snapshot':dict(valid=True,value='map')},evidence={'map':{'data':{'holes':[hole]}}},journey={'profile':{'seven':{'value':dict(distance=160,units='码',distance_type='carry')}}})
  shot=dict(id='second',stroke_number=2,club='52度杆',origin=point(100),landing=point(180),distance_m=80*.9144)
  return s,hole,[shot],point
 def test_names_shot_actual_distance_and_verified_alternative(self):
  from hole_recap_options import explain
  from unittest.mock import patch
  s,h,shots,p=self.fixture();target=dict(carry_yards=180,reference=None,offset=0,aim_point=p(280))
  route=dict(layup=target,leave_yards=120,risk_rank=(0,),layup_long_club=False)
  with patch('tee_strategy.par_five_routes',return_value=[route]):text=explain(s,h,shots,{},'码')
  self.assertIn('第2杆',text);self.assertIn('52度杆打了约80码',text);self.assertIn('还剩约220码',text);self.assertIn('5号铁',text);self.assertIn('下一杆到果岭参考点约120码',text);self.assertIn('不能认定当时一定适合',text)
 def test_no_verified_alternative_is_reported_without_generic_instruction(self):
  from hole_recap_options import explain
  from unittest.mock import patch
  s,h,shots,p=self.fixture()
  with patch('tee_strategy.par_five_routes',return_value=[]):text=explain(s,h,shots,{},'码')
  self.assertIn('第2杆',text);self.assertIn('不能认定这杆应该打得更远',text);self.assertNotIn('优先回看攻果岭前的推进过程',text)
 def test_missing_origin_does_not_invent_a_route(self):
  from hole_recap_options import explain
  s,h,shots,p=self.fixture();shots[0].pop('origin');self.assertIn('缺少',explain(s,h,shots,{},'码'))
