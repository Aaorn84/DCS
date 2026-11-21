import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tee_strategy import compare_par_routes,third_shot_text
class ParFiveDistanceBasisTests(unittest.TestCase):
 def fixture(self):
  yard=.9144;meter=111195
  origin=dict(latitude=0,longitude=0,accuracy_m=2)
  green=dict(kind='green_center',latitude=380*yard/meter,longitude=0)
  tee=dict(club_key='driver',club='一号木',carry_yards=260,width_m=30,offset=0,reference=None,crossing_m=None,aim_point=dict(latitude=260*yard/meter,longitude=0,accuracy_m=0))
  profile={'seven':{'value':{'distance':160,'units':'码','distance_type':'carry'}},'lofted_wedge_ranges':{'value':{'52':{'low':0,'high':85,'units':'码'}}}}
  state={'facts':{'context.device_position':{'valid':True,'value':origin}},'journey':{'profile':profile},'evidence':{'map':{'data':{'holes':[{'number':11,'published_yardage':570,'objects':[green]}]}}}}
  analysis=dict(course_evidence='map',hole=11,position_version=1,clubs={'driver':{'label':'一号木','carry_yards':260},'three_wood':{'label':'3号木','carry_yards':240},'seven':{'label':'7号铁','carry_yards':160}})
  option=dict(tee,id='g',hole=11,target='球道',course_evidence='map',position_version=1,strategy='mapped_carry_candidate')
  return state,analysis,tee,green,option
 def test_within_length_gate_still_evaluates_verified_geometry_candidate(self):
  state,a,tee,green,option=self.fixture()
  state['evidence']['map']['data']['holes'][0]['published_yardage']=490
  def targets(s,a,clubs,**kwargs):
   candidates=dict(clubs)
   if 'control-pitching_wedge' not in candidates:return []
   club=candidates['control-pitching_wedge']
   return [dict(club_key='control-pitching_wedge',club=club['label'],carry_yards=club['carry_yards'],width_m=20,offset=0,crossing_m=None,aim_point=green)]
  with patch('tee_geometry.tee_targets',side_effect=targets) as search:
   result=compare_par_routes(state,a,[tee],'三上候选',option,'码',evaluate_geometry=True)
  self.assertTrue(search.called);self.assertIn('两上方案',result['text']);self.assertIn('P杆',result['text'])
  self.assertIn('暂估',result['text']);self.assertIn('需要控制',result['text'])
  self.assertIn('公布490码',result['text']);self.assertIn('380码',result['text'])
  self.assertNotIn('低于球洞公布长度',result['text'])
 def test_legacy_event_keeps_historic_budget_rule(self):
  state,a,tee,green,option=self.fixture()
  with patch('tee_geometry.tee_targets') as search:
   result=compare_par_routes(state,a,[tee],'三上候选',option,'码')
  search.assert_not_called();self.assertIn('低于球洞公布长度570码',result['text'])
 def test_third_shot_identifies_origin_direction_distance_and_club(self):
  state,a,tee,green,option=self.fixture()
  text=third_shot_text(state['journey']['profile'],15,'码')
  for word in ('第三杆','预测落点','果岭参考方向','15码','52度杆'):self.assertIn(word,text)

class ParFiveLengthGateTests(ParFiveDistanceBasisTests):
 def test_570_yards_skips_all_green_searches(self):
  state,a,tee,green,option=self.fixture()
  with patch('tee_geometry.tee_targets',side_effect=AssertionError('two-on search must be skipped')):
   r=compare_par_routes(state,a,[tee],'过渡路线。',option,'码',evaluate_geometry=True,allow_roll_in=True)
  self.assertIn('三上方案',r['text']);self.assertIn('500码',r['text']);self.assertIn('560码',r['text']);self.assertIn('暂无法两上',r['text']);self.assertNotIn('两上方案',r['text']);self.assertEqual(r['options'][0]['par_plan'],'three')
 def test_exact_ten_yard_shortfall_does_not_skip_search(self):
  state,a,tee,green,option=self.fixture();state['evidence']['map']['data']['holes'][0]['published_yardage']=510
  with patch('tee_geometry.tee_targets',return_value=[]) as search:
   compare_par_routes(state,a,[tee],'过渡路线。',option,'码',evaluate_geometry=True)
  self.assertTrue(search.called)
 def test_one_yard_beyond_ten_yard_shortfall_skips(self):
  state,a,tee,green,option=self.fixture();state['evidence']['map']['data']['holes'][0]['published_yardage']=511
  with patch('tee_geometry.tee_targets') as search:
   compare_par_routes(state,a,[tee],'过渡路线。',option,'码',evaluate_geometry=True)
  search.assert_not_called()
 def test_unknown_length_does_not_claim_out_of_range(self):
  state,a,tee,green,option=self.fixture();state['evidence']['map']['data']['holes'][0]['published_yardage']=None
  with patch('tee_geometry.tee_targets',return_value=[]) as search:
   r=compare_par_routes(state,a,[tee],'过渡路线。',option,'码',evaluate_geometry=True)
  self.assertTrue(search.called);self.assertNotIn('暂无法两上',r['text'])
