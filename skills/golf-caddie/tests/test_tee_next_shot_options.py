import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tee_next_shot_options import compare
class NextShotOptionsTests(unittest.TestCase):
 def fixture(self):
  unit=111195;yd=.9144
  profile={key:{'value':dict(distance=value,units='码',distance_type='carry')} for key,value in [('driver',260),('five_wood',220),('seven',160),('hybrid',200)]}
  a={'course_evidence':'map','hole':7,'position_version':1}
  state={'journey':{'profile':profile},'evidence':{'map':{'data':{'holes':[{'number':7,'objects':[dict(kind='green_center',latitude=415*yd/unit,longitude=0)]}]}}}}
  targets=[dict(club_key=key,club=label,carry_yards=carry,low_yards=carry-5,high_yards=carry+5,width_m=width*yd,offset=0,reference=None,crossing_m=None,aim_point=dict(latitude=carry*yd/unit,longitude=0,accuracy_m=0)) for key,label,carry,width in [('driver','一号木',260,28),('five_wood','5号木',220,40)]]
  return state,a,targets
 def test_both_clubs_include_landing_and_following_approach(self):
  state,a,targets=self.fixture()
  result=compare(state,a,targets,'码')
  text=result['text']
  for word in ('一号木方案','5号木方案','28码','40码','155码','195码','尚未计入滚动'):self.assertIn(word,text)
  for word in ('两种开球预计留下','按你更有把握','开球落定后重新确认','下一杆可先比较','已知Carry','实际目标Carry待','下一杆果岭入口','下一杆果岭参考落区','停球容错','落点附近有'):self.assertNotIn(word,text)
  self.assertEqual(['一号木','5号木'],[option['club'] for option in result['options']])
  self.assertNotIn('一号木',state['journey'])
 def test_does_not_invent_missing_club_candidate(self):
  state,a,targets=self.fixture()
  result=compare(state,a,targets[:1],'码')
  self.assertEqual(['一号木'],[option['club'] for option in result['options']])
 def test_either_club_selects_its_offer_without_two_on_question(self):
  from round_state import initial
  from journey import _apply_journey
  from tee_strategy import reported_carry_clubs
  for club in ('一号木','5号木'):
   with self.subTest(club=club):
    fixture,a,targets=self.fixture();state=initial()
    state['evidence'].update(fixture['evidence']);state['facts'].update({'context.active_hole':{'valid':True,'value':7},'context.course_snapshot':{'valid':True,'value':'map'},'context.device_position':{'valid':True,'value':dict(latitude=0,longitude=0,accuracy_m=2,observed_at='1970-01-01T00:00:00+00:00')}})
    a.update(par=4,distance_yards=415,candidates=[],clubs=reported_carry_clubs(fixture['journey']['profile']))
    space={'width_m':10,'depth_m':10,'hazards':[]}
    with patch('tee_strategy.green_landing_space',return_value=space):offer=compare(fixture,a,targets,'码')
    state['journey']={'stage':'active','quiet':False,'profile':fixture['journey']['profile'],'round':{'id':'r'},'consultation':{'phase':'tee_commit','analysis':a,'last_offer':offer}}
    with patch('tee_strategy.analyze',return_value=a),patch('tee_geometry.tee_targets',side_effect=lambda s,a,clubs,**kw:[t for t in targets if t['club_key'] in dict(clubs)]):
     reply=_apply_journey(state,dict(type='message',event_id='selected',text=club,observed_at='1970-01-01T00:00:00+00:00',_tee_geometry_v94=True,_par_five_v95=True,_par_five_bag_v101=True,_carry_crossing_v96=True,_stroke_consistency_v111=True),1,0)
    self.assertIn('好，开球用'+club,reply['text']);self.assertNotIn('两上还是三上',reply['text'])
    self.assertNotIn('consultation',state['journey'])
    self.assertEqual(club,state['journey']['player_decisions'][-1]['club'])

 def test_wider_and_shorter_next_shot_dominates_five_wood(self):
  state,a,targets=self.fixture();targets[1]['width_m']=21*.9144
  result=compare(state,a,targets,'码')
  self.assertEqual(['一号木'],[option['club'] for option in result['options']])
 def test_alternative_can_be_three_wood_instead_of_fixed_five_wood(self):
  import copy
  state,a,targets=self.fixture();third=copy.deepcopy(targets[1]);third.update(club_key='three_wood',club='3号木',carry_yards=240,width_m=45*.9144,aim_point=dict(latitude=240*.9144/111195,longitude=0,accuracy_m=0));targets.append(third)
  result=compare(state,a,targets,'码')
  self.assertEqual(['一号木','3号木'],[option['club'] for option in result['options']])
 def test_nearby_water_keeps_meaningful_shorter_alternative(self):
  state,a,targets=self.fixture();targets[1]['width_m']=21*.9144
  def space(hole,simulation,origin,target,surface,*args):
   risk=[dict(kind='water',side='右侧',distance_m=4)] if surface=='fairway' and target is targets[0]['aim_point'] else []
   return dict(width_m=30,depth_m=30,hazards=risk)
  with patch('tee_geometry.landing_space',side_effect=space):result=compare(state,a,targets,'码')
  self.assertEqual(2,len(result['options']));self.assertIn('水障碍',result['text'])
 def test_widest_iron_not_preferred_if_it_leaves_uncovered_approach(self):
  import copy
  state,a,targets=self.fixture();iron=copy.deepcopy(targets[1]);iron.update(club_key='seven',club='7号铁',carry_yards=160,width_m=70*.9144,aim_point=dict(latitude=160*.9144/111195,longitude=0,accuracy_m=0));targets.append(iron)
  result=compare(state,a,targets,'码')
  self.assertEqual(['一号木','5号木'],[option['club'] for option in result['options']])

 def test_carry_sand_overlap_offers_verified_shorter_candidate(self):
  state,a,targets=self.fixture();targets[1].update(carry_yards=180,high_yards=185,width_m=23*.9144)
  with patch('tee_next_shot_options.bunker_band',side_effect=lambda h,sim,o,t:(228*.9144,251*.9144) if t['club_key']=='driver' else None):
   result=compare(state,a,targets,'码')
  self.assertEqual(2,len(result['options']));self.assertIn('前后距离重叠',result['text']);self.assertIn('沙前保守候选',result['text'])
 def test_shorter_carry_without_roll_clearance_is_not_called_sand_front(self):
  state,a,targets=self.fixture()
  with patch('tee_next_shot_options.bunker_band',side_effect=lambda h,sim,o,t:(228*.9144,251*.9144) if t['club_key']=='driver' else None):result=compare(state,a,targets,'码')
  self.assertNotIn('沙前保守候选',result['text'])
 def test_sand_front_search_includes_longer_estimated_mid_iron(self):
  import copy
  state,a,targets=self.fixture();state['journey']['profile']['seven']={'value':{'distance':150,'distance_type':'carry','units':'码'}}
  iron=copy.deepcopy(targets[1]);iron.update(club_key='iron5',club='5号铁',carry_yards=170,high_yards=175,width_m=24*.9144)
  targets[1].update(width_m=15*.9144,carry_yards=150,high_yards=155)
  with patch('tee_next_shot_options.bunker_band',side_effect=lambda h,sim,o,t:(228*.9144,251*.9144) if t['club_key']=='driver' else None),patch('tee_geometry.tee_targets',return_value=[iron]):result=compare(state,a,targets,'码')
  self.assertEqual(['一号木','5号铁'],[o['club'] for o in result['options']]);self.assertIn('暂估',result['text']);self.assertIn('沙前保守候选',result['text'])
 def test_penalty_risk_can_override_distance_advantage(self):
  state,a,targets=self.fixture()
  def space(hole,simulation,origin,target,surface,*args):
   hazards=[dict(kind='ob',side='右侧',distance_m=3)] if surface=='fairway' and target is targets[0]['aim_point'] else []
   return dict(width_m=30,depth_m=30,hazards=hazards)
  with patch('tee_geometry.landing_space',side_effect=space):result=compare(state,a,targets,'码')
  self.assertEqual('5号木',result['options'][0]['club'])
 def test_equal_risk_alternative_prefers_more_progress_not_widest_shortest(self):
  import copy
  state,a,targets=self.fixture();mid=copy.deepcopy(targets[1]);mid.update(club_key='hybrid',club='铁木杆',carry_yards=190,width_m=60*.9144,aim_point=dict(latitude=190*.9144/111195,longitude=0,accuracy_m=0))
  def space(hole,simulation,origin,target,surface,*args):
   hazards=[dict(kind='water',side='右侧',distance_m=3)] if surface=='fairway' and target is targets[0]['aim_point'] else []
   return dict(width_m=30,depth_m=30,hazards=hazards)
  with patch('tee_geometry.landing_space',side_effect=space):result=compare(state,a,targets+[mid],'码')
  self.assertEqual('5号木',result['options'][0]['club'])

 def test_single_option_omits_scheme_heading(self):
  state,a,targets=self.fixture();result=compare(state,a,targets[:1],'码')
  self.assertTrue(result['text'].startswith('一号木Carry约'))
  self.assertNotIn('一号木方案：',result['text'])

 def test_clear_driver_only_unless_alternative_explicitly_requested(self):
  state,a,targets=self.fixture();targets[0]['crossing_m']=240*.9144
  result=compare(state,a,targets,'码');self.assertEqual(['一号木'],[o['club'] for o in result['options']]);self.assertTrue(result['text'].startswith('一号木Carry'))
  result=compare(state,a,targets,'码',requested_alternative=True);self.assertEqual(2,len(result['options']))
 def test_marginal_crossing_does_not_hide_alternative(self):
  state,a,targets=self.fixture();targets[0]['crossing_m']=258*.9144
  self.assertEqual(2,len(compare(state,a,targets,'码')['options']))
