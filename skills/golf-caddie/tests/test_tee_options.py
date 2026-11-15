import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_projection as base
from round_state import fact_value
from journey import view
from journey_tee_options import build_routes
from tee_strategy import analyze
class TeeOptionsTests(unittest.TestCase):
 setUp=base.ProjectionTests.setUp
 tearDown=base.ProjectionTests.tearDown
 begin=base.ProjectionTests.begin
 def send(self,text='',gps=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=37,type='gps' if gps else 'message',event_id='t'+str(self.n),observed_at=self.clock.isoformat(),**({'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_offer_has_two_distinct_routes_without_player_choice(self):
  self.begin();s=self.e.state('j');routes=s['journey']['tee_route_options']['routes'];self.assertEqual([r['kind'] for r in routes],['conservative','aggressive']);self.assertEqual(routes[0]['club_key'],'long_iron');self.assertEqual(routes[1]['club_key'],'driver');self.assertNotEqual(routes[0]['zone_id'],routes[1]['zone_id']);self.assertNotIn('suggestion',s['journey']['consultation']);self.assertNotIn('selected_club',s['journey']['consultation']);self.assertNotIn('player_intent',s['journey']['consultation']);self.assertEqual(view(s)['choices'],['保守方案','进取方案','自己打']);self.assertEqual(s,self.e.replay('j'))
 def test_each_route_has_risk_target_and_estimated_remaining(self):
  self.begin();out=self.send('怎么打');self.assertIn('保守：',out['text']);self.assertIn('进取：',out['text']);self.assertEqual(out['text'].count('？'),1)
  for r in out['tee_routes']:self.assertTrue(r['risk']);self.assertTrue(r['target']);self.assertGreater(r['remaining_yards'],0)
 def test_conservative_choice_then_confirmation_not_execution(self):
  self.begin();self.send('保守方案');s=self.e.state('j');self.assertEqual(s['journey']['consultation']['selected_club']['key'],'long_iron');self.assertEqual(s['journey']['response_context']['question_owner'],'plan.confirm');out=self.send('可以');self.assertIn('确认',out['text']);self.assertNotIn('consultation',self.e.state('j')['journey']);self.assertFalse(self.e.state('j')['journey'].get('execution_reports'));self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_aggressive_choice_uses_driver(self):
  self.begin();self.send('我选进取方案');self.assertEqual(self.e.state('j')['journey']['consultation']['selected_club']['key'],'driver')
 def test_generic_yes_does_not_choose_a_route(self):
  self.begin();self.send('好');c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['phase'],'tee_options');self.assertNotIn('selected_club',c)
 def test_bare_next_distance_reports_both_while_unselected(self):
  self.begin();out=self.send('下一杆还剩多少');self.assertIn('保守方案',out['text']);self.assertIn('进取方案',out['text']);self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'tee_options')
 def test_explicit_distance_comparison_does_not_choose(self):
  self.begin();out=self.send('用3号木，下一杆还剩多少');self.assertEqual(out['projection']['club_key'],'three_wood');self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'tee_options');out=self.send('下一杆还剩多少');self.assertEqual(out['projection']['club_key'],'three_wood')
 def test_missing_data_stays_one_question_at_a_time(self):
  self.begin(False);out=self.send('怎么打');self.assertEqual(out['text'].count('？'),1);self.assertIn('一号木',out['text']);out=self.send('260');self.assertEqual(out['text'].count('？'),1);self.assertIn('3号木',out['text'])
 def test_no_fake_second_route_when_no_safer_evidence(self):
  self.begin();s=self.e.state('j');a=analyze(s,self.clock.timestamp());a['candidates']=[a['candidates'][0]];self.assertIsNone(build_routes(s,a,self.clock.timestamp()))
 def test_shorter_and_narrower_without_hazard_reduction_is_not_conservative(self):
  self.begin();s=self.e.state('j');a=copy.deepcopy(analyze(s,self.clock.timestamp()))
  for c in a['candidates']:c['zone']['hazards']=[];c['zone']['width_yards']=50 if c['club_key']=='driver' else 30
  self.assertIsNone(build_routes(s,a,self.clock.timestamp()))
 def test_stale_position_does_not_commit_route(self):
  self.begin();self.clock+=timedelta(minutes=5);out=self.send('进取方案');self.assertIn('定位',out['text']);self.assertNotIn('selected_club',self.e.state('j')['journey']['consultation'])
 def test_resuming_after_fact_returns_options(self):
  self.begin();self.send('还有多远');out=self.send('继续刚才的问题');self.assertIn('保守：',out['text']);self.assertIn('进取：',out['text'])
 def test_reconsidering_restores_both_unselected_routes(self):
  self.begin();self.send('进取方案');self.send('再想想');c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['phase'],'tee_options');self.assertNotIn('selected_club',c);self.assertNotIn('suggestion',c)
 def test_score_recording_keeps_priority(self):
  self.begin();self.send('这洞6杆，2推，0罚杆');self.send('确认记录');self.assertEqual(fact_value(self.e.state('j'),'holes.1.total'),6)
 def test_duplicate_and_changed_event_payload(self):
  self.begin();self.send('怎么打');p=copy.deepcopy(self.last);out=self.e.command('j','retry','journey_event',p,now=self.clock.timestamp());self.assertTrue(out['duplicate']);p['text']='保守方案'
  with self.assertRaises(ValueError):self.e.command('j','bad','journey_event',p,now=self.clock.timestamp())
if __name__=='__main__':unittest.main()
