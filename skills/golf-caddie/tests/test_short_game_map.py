import unittest,sys,time,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from short_game_map import handle
from short_game_route import assess
import test_green_space
class MapFirstTests(unittest.TestCase):
 def scene(self):
  s=test_green_space.GreenSpaceTests().scene();s['facts']['context.device_position']['value']['latitude']=-.00025;s['journey']['round']={'id':'r'};s['journey']['consultation']={'phase':'plan','lie_report':'球道'}
  def zone(id,surface,w,a,e,n):return {'id':id,'surface':surface,'verified':True,'source':'test-survey','geometry':{'type':'Polygon','coordinates':[[[w,a],[e,a],[e,n],[w,n],[w,a]]]}}
  h=s['evidence']['map']['data']['holes'][0];h['surface_zones']=[zone('fairway','fairway',-.00008,-.0003,.00008,.00005),zone('green','green',-.0001,-.0001,.0001,.0001)]
  self.zone=zone;return s
 def test_clear_map_answers_without_asking(self):
  s=self.scene();r=handle(s,dict(text='打高飞还是切滚？',event_id='q'),time.time());self.assertIn('倾向切滚',r);self.assertNotIn('？',r);self.assertNotIn('short_game_question',s['journey']);self.assertEqual(s['journey']['last_short_game_advice']['route_assessment']['verdict'],'clear');self.assertTrue(s['journey']['last_short_game_advice']['not_player_decision'])
 def test_mapped_bunker_blocks_even_without_full_ground_coverage(self):
  s=self.scene();h=s['evidence']['map']['data']['holes'][0];h['surface_zones']=[self.zone('b','bunker',-.00005,-.00019,.00005,-.00018)]
  r=handle(s,dict(text='打高飞还是切滚？',event_id='q'),time.time());self.assertIn('沙坑',r);self.assertNotIn('？',r);self.assertNotIn('short_game_question',s['journey'])
 def test_missing_surface_coverage_asks_only_one_question(self):
  s=self.scene();s['evidence']['map']['data']['holes'][0]['surface_zones'].pop(0);r=handle(s,dict(text='打高飞还是切滚？',event_id='q'),time.time());self.assertEqual(r.count('？'),1);self.assertIn('地图还不能确认',r)
  r=handle(s,dict(text='没有障碍',event_id='a'),time.time());self.assertIn('倾向切滚',r)
 def test_unknown_obstacle_answer_and_wrong_yes_semantics(self):
  s=self.scene();s['evidence']['map']['data']['holes'][0]['surface_zones']=[];handle(s,dict(text='打高飞还是切滚？',event_id='q'),time.time());r=handle(s,dict(text='有',event_id='a'),time.time());self.assertIn('别走地面',r)
 def test_direct_club_request_uses_map_before_recommending(self):
  now=time.time()
  s=self.scene();self.assertIn('P杆切滚',handle(s,dict(text='用哪只杆？',event_id='q'),now))
  h=s['evidence']['map']['data']['holes'][0]
  h['surface_zones'].append(self.zone('b','bunker',-.00005,-.00019,.00005,-.00018))
  self.assertIn('沙杆（SW）抛切',handle(s,dict(text='用哪只杆？',event_id='q2'),now))
  h['surface_zones']=[]
  self.assertEqual(handle(s,dict(text='用哪只杆？',event_id='q3'),now).count('？'),1)
  self.assertIn('P杆切滚',handle(s,dict(text='没有障碍',event_id='a'),now))
  self.assertNotIn('player_decisions',s['journey'])
  s['facts']['context.device_position']['value']['latitude']=-.0013
  self.assertIsNone(handle(s,dict(text='用哪只杆？',event_id='q4'),now))

 def test_side_hazard_not_on_route_is_not_a_blocker(self):
  s=self.scene();s['evidence']['map']['data']['holes'][0]['surface_zones'].append(self.zone('side','bunker',.00012,-.0002,.00015,-.00015));self.assertEqual(assess(s,time.time())['verdict'],'clear')
 def test_thin_hazard_and_accuracy_overlap_are_detected(self):
  s=self.scene();s['evidence']['map']['data']['holes'][0]['surface_zones'].append(self.zone('thin','water',-.00002,-.000171,.00002,-.000170));self.assertEqual(assess(s,time.time())['verdict'],'blocked')
 def test_unverified_map_never_proves_clear(self):
  s=self.scene()
  for z in s['evidence']['map']['data']['holes'][0]['surface_zones']:z['verified']=False
  self.assertEqual(assess(s,time.time())['verdict'],'unknown')
 def test_explicit_lie_correction_has_priority(self):
  s=self.scene();s['journey']['consultation'].update(lie_report='沙坑',lie_evidence={'source':'user_report'});self.assertIn('脱困',handle(s,dict(text='打高飞还是切滚？',event_id='q'),time.time()))
 def test_mapped_sand_retains_a_flight_option_near_green(self):
  s=self.scene()
  h=s['evidence']['map']['data']['holes'][0]
  h['surface_zones'].append(self.zone('b','bunker',-.00005,-.00019,.00005,-.00018))
  out=handle(s,dict(text='打高飞还是切滚？',event_id='q',_carry_crossing_v96=True),time.time())
  self.assertIn('沙坑远沿约',out)
  self.assertIn('目标Carry',out)
  self.assertIn('抛切',out)

 def test_long_crossing_from_rough_is_not_a_pitch_recommendation(self):
  from unittest.mock import patch
  from approach_dialogue import advise
  s=self.scene()
  s['facts']['context.device_position']['value']['latitude']=-.0023
  c=dict(lie_report='长草',ball_position_report='user_confirmed')
  line=dict(front_m=250,back_m=269,target_m=258,accuracy_m=2,
            hazards={'bunker':248.7,'water':None,'ob':None})
  with patch('hazard_route.landing_line',return_value=line):
   text=advise(s,c,time.time(),carry_crossing=True,verify_playability=True)['text']
   self.assertIn('攻果岭线需要Carry约',text)
   self.assertIn('先把球送回看得见、较宽的球道',text)
   self.assertNotIn('抛切',text)
   c['lie_report']='球道'
   s['journey']['profile']={'driver':{'value':{'distance':278,'units':'码','distance_type':'carry'}}}
   with patch('tee_strategy.actual_position_layup',return_value='第二杆过渡，预计第三杆约90码。'):
    text=advise(s,c,time.time(),carry_crossing=True,verify_playability=True)['text']
   self.assertIn('第三杆约90码',text)
   self.assertNotIn('可考虑一号木',text)

 def test_hazard_behind_target_does_not_require_a_flyover(self):
  from hazard_route import green_crossing_advice
  s=self.scene()
  s['evidence']['map']['data']['holes'][0]['surface_zones'].append(
   self.zone('back','bunker',-.00005,.000025,.00005,.00007))
  self.assertIsNone(green_crossing_advice(s,time.time(),short_game=True))

 def test_fairway_approach_uses_carry_to_clear_water(self):
  from approach_dialogue import advise
  s=self.scene()
  s['facts']['context.device_position']['value']['latitude']=-.0013
  h=s['evidence']['map']['data']['holes'][0]
  h['surface_zones'].append(self.zone('w','water',-.00005,-.00033,.00005,-.0002))
  c=dict(lie_report='球道',ball_position_report='user_confirmed')
  out=advise(s,c,time.time(),carry_crossing=True)
  self.assertTrue(out['mapped_crossing'])
  self.assertIn('水障碍远沿约',out['text'])
  self.assertIn('目标Carry',out['text'])
  h['surface_zones'][-1]=self.zone('w','water',-.00005,-.00033,.00005,.000085)
  self.assertIn('停球空间不足',advise(s,c,time.time(),carry_crossing=True)['text'])

if __name__=='__main__':unittest.main()
