import sys,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
class ContinuityTests(unittest.TestCase):
 def setUp(self):
  self.e=Engine(':memory:','c');self.e.create('j');self.n=0;self.clock=1794000000
  for t in ['可以记住','球友','可以','不记录击球','240','140','偏右','演示球场（合成）','白台','1','轻松打球','状态不错','开始球局']:self.send(t)
  self.gps();self.send('到发球台了');self.send('这杆怎么打')
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',data=None,dt=0):
  self.clock+=dt;self.n+=1;p=dict(protocol_version=9,type=kind,event_id='e'+str(self.n),observed_at=datetime.fromtimestamp(self.clock,timezone.utc).isoformat())
  if kind=='message':p['text']=text
  else:p['data']=data
  return self.e.command('j',str(self.n),'journey_event',p,now=self.clock)
 def gps(self,lon=120.9992,dt=0):return self.send(kind='gps',data=dict(latitude=31,longitude=lon,accuracy_m=2),dt=dt)
 def state(self):return self.e.state('j')
 def test_only_incremental_info(self):
  r=self.send('200');self.assertNotIn('一号木Carry',r['text']);self.assertNotIn('你还没表达',r['text']);self.assertEqual(r['text'].count('？'),1)
 def test_stale_club_saved_and_resumed(self):
  self.send('200');r=self.send('5铁180码',dt=61);self.assertIn('不用重报',r['text']);self.assertEqual(self.state()['journey']['profile']['long_iron']['value']['club_name'],'5铁');self.assertEqual(self.state()['journey']['consultation']['phase'],'tee_refresh')
  r=self.gps(dt=1);self.assertIn('5铁',r['text']);self.assertNotIn('Carry大概多少',r['text']);self.assertEqual(self.state()['journey']['consultation']['phase'],'tee_commit');self.assertEqual(self.state(),self.e.replay('j'))
 def test_fresh_fix_version_not_cancellation(self):
  self.send('200');self.gps(dt=8);r=self.send('5铁180');self.assertIn('5铁',r['text']);self.assertNotIn('重新讨论',r['text']);self.send('按这个打');self.assertEqual(self.state()['journey']['last_consultation']['decision']['club'],'5铁')
 def test_no_stale_commit(self):
  self.send('200');self.send('5铁180');r=self.send('按这个打',dt=61);self.assertEqual(self.state()['journey']['consultation']['phase'],'tee_refresh');self.assertNotIn('last_consultation',self.state()['journey'])
 def test_no_duplicate_manual_brief(self):
  self.send('200');self.send('5铁180',dt=61);self.gps(dt=1);r=self.send('到发球台了');self.assertNotIn('第1洞',r['text']);self.assertEqual(self.state()['journey']['consultation']['phase'],'tee_commit')
if __name__=='__main__':unittest.main()
