import unittest,sys,copy
from pathlib import Path
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from journey_navigation_queries import distance_query
from round_state import Engine,fact_value
from phoenix_demo import preview
class NavigationQueriesTests(unittest.TestCase):
 def setUp(self):self.e=Engine(':memory:','test');self.e.create('j');self.n=0;self.clock=datetime.fromisoformat('2026-11-08T00:00:00Z')
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',protocol=33,**kw):
  self.n+=1;self.clock+=timedelta(seconds=1)
  p=dict(protocol_version=protocol,event_id='n'+str(self.n),type=kind,observed_at=self.clock.isoformat(),**({'text':text} if kind=='message' else {}),**kw);self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def begin(self):
  for t in ['先打球','东莞凤凰山（A+B蓝台演示）','蓝台','1','轻松打球','开始球局']:self.send(t)
  self.send(kind='gps',data=dict(preview(1)['positions']['fairway'],simulation_source='map_click'))
 def test_distance_synonyms_and_units(self):
  for t in ['还有多远','还有多远？','还剩多远','多远','还有多少','还剩多少','距离','离果岭多远','距离果岭还有多远','到果岭中心还有多少码']:
   self.assertEqual(distance_query(t),'码',t)
  self.assertEqual(distance_query('还有多远','米'),'米');self.assertEqual(distance_query('距离果岭还有多少米'),'米')
 def test_other_distance_domains_not_intercepted(self):
  for t in ['上一杆打了多远','过沙需要多少','右侧有多少空间','这洞几杆','还要罚多少杆','7铁190','190','没有','5铁打向果岭']:self.assertIsNone(distance_query(t),t)
 def test_query_during_plan_preserves_discussion(self):
  self.begin();self.send('这杆怎么打');self.send('150')
  before=copy.deepcopy(self.e.state('j')['journey'].get('consultation'))
  result=self.send('还有多远');self.assertIn('果岭',result['text']);self.assertNotIn('不能可靠判断',result['text']);self.assertEqual(before,self.e.state('j')['journey'].get('consultation'))
  self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_rejected_map_jump_uses_previous_valid_fix(self):
  self.begin();before=copy.deepcopy(fact_value(self.e.state('j'),'context.device_position'))
  gps=dict(preview(1)['positions']['green'],simulation_source='map_click')
  out=self.send(kind='gps',data=gps);self.assertTrue(out.get('ignored'),out);self.assertEqual(out['reason'],'implausible_jump')
  self.assertEqual(before,fact_value(self.e.state('j'),'context.device_position'))
  out=self.send('还有多远');self.assertIn('果岭',out['text']);self.assertIn('上一处有效位置',out['text']);self.assertNotIn('不能可靠判断',out['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_real_gps_jump_is_still_invalidated(self):
  self.begin();out=self.send(kind='gps',data=dict(preview(1)['positions']['green']))
  self.assertTrue(out.get('ignored'));self.assertIsNone(fact_value(self.e.state('j'),'context.device_position'))
  out=self.send('还有多远');self.assertIn('定位',out['text']);self.assertNotIn('上一处有效位置',out['text'])
 def test_stale_location_is_not_reported_as_language_failure(self):
  self.begin();self.clock+=timedelta(minutes=5);out=self.send('还有多远')
  self.assertIn('定位',out['text']);self.assertNotIn('不能可靠判断',out['text'])
 def test_raw_event_dedup_survives_normalization(self):
  self.begin();self.send('还有多远');p=copy.deepcopy(self.last)
  r=self.e.command('j','retry','journey_event',p,now=self.clock.timestamp());self.assertTrue(r['duplicate'])
  p['text']='还有多少'
  with self.assertRaises(ValueError):self.e.command('j','reuse','journey_event',p,now=self.clock.timestamp())
 def test_old_protocol_keeps_previous_meaning_and_replay(self):
  self.begin();out=self.send('还有多远',protocol=32);self.assertIn('不能可靠判断',out['text']);self.assertEqual(self.e.state('j'),self.e.replay('j'))
if __name__=='__main__':unittest.main()
