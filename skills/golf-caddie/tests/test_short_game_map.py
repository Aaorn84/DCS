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
if __name__=='__main__':unittest.main()
