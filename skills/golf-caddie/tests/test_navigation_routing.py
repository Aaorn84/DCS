import sys,unittest,copy
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from navigation_requests import distance_unit,selected_iron
class NavigationTests(unittest.TestCase):
 def setUp(self):
  self.e=Engine(':memory:','n');self.e.create('j');self.n=0;self.clock=1794000000
  for t in ['可以记住','球友','可以','不记录击球','240','140','偏右','演示球场（合成）','白台','1','轻松打球','状态不错','开始球局']:self.send(t)
  self.gps();self.send('到发球台了');self.send('这杆怎么打');self.send('200');self.send('5铁180')
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',data=None,dt=0):
  self.clock+=dt;self.n+=1;p=dict(protocol_version=10,type=kind,event_id='e'+str(self.n),observed_at=datetime.fromtimestamp(self.clock,timezone.utc).isoformat())
  if kind=='message':p['text']=text
  else:p['data']=data
  return self.e.command('j',str(self.n),'journey_event',p,now=self.clock)
 def gps(self,lon=120.9992,dt=0):return self.send(kind='gps',data=dict(latitude=31,longitude=lon,accuracy_m=2),dt=dt)
 def state(self):return self.e.state('j')
 def test_query_interrupts_commit(self):
  before=copy.deepcopy(self.state()['journey']['consultation']);r=self.send('距离果岭还有多少？');self.assertIn('distance',r);self.assertEqual(before,self.state()['journey']['consultation'])
 def test_expired_query_then_fairway_recovers(self):
  self.send('按这个打',dt=61);r=self.send('还有多少？');self.assertIn('更新位置',r['text']);self.gps(lon=121.001,dt=20);self.assertNotIn('consultation',self.state()['journey']);r=self.send('距离果岭还有多少？');self.assertIn('distance',r);self.assertEqual(self.state()['journey']['last_consultation']['status'],'superseded_by_location');self.assertEqual(self.state(),self.e.replay('j'))
 def test_natural_iron_selection(self):
  self.send('好，那就用5号铁');self.assertEqual(self.state()['journey']['last_consultation']['decision']['club'],'5铁');self.assertNotIn('consultation',self.state()['journey'])
 def test_stale_natural_selection_not_execution(self):
  self.send('好，那就用5号铁',dt=61);c=self.state()['journey']['consultation'];self.assertEqual(c['selection_report']['club'],'5号铁');self.assertEqual(c['phase'],'tee_refresh');self.assertNotIn('decision',c)
 def test_rejected_gps_cannot_clear_consultation(self):
  r=self.gps(lon=121.001,dt=1);self.assertTrue(r.get('ignored'));self.assertIn('consultation',self.state()['journey']);r=self.send('还有多少？');self.assertNotIn('distance',r)
 def test_current_distance_grammar(self):
  for q in ['还有多少？','距离果岭还有多少？','到果岭还有多少码','果岭中心还有多少米']:self.assertIn(distance_unit(q),('码','米'))
  for q in ['上一杆打了多少码','这一洞多少杆','还有多少罚杆']:self.assertIsNone(distance_unit(q))
 def test_current_club_grammar(self):
  self.assertEqual(selected_iron('好，那就用5号铁'),5);self.assertIsNone(selected_iron('刚才用了5号铁'))
if __name__=='__main__':unittest.main()
