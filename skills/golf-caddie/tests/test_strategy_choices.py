import sys,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
class ChoiceTests(unittest.TestCase):
 def setUp(self):
  self.e=Engine(':memory:','choice');self.e.create('j');self.n=0;self.clock=1794000000
  for t in ['可以记住','球友','可以','不记录击球','240','150','偏右','演示球场（合成）','白台','1','轻松打球','状态不错','开始球局']:self.send(t)
  self.gps();self.send('到发球台了');self.send('应该怎么打');self.send('200');self.send('5铁190')
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',data=None,dt=0):
  self.clock+=dt;self.n+=1;p=dict(protocol_version=16,type=kind,event_id='e'+str(self.n),observed_at=datetime.fromtimestamp(self.clock,timezone.utc).isoformat())
  if kind=='message':p['text']=text
  else:p['data']=data
  return self.e.command('j',str(self.n),'journey_event',p,now=self.clock)
 def gps(self,dt=0):return self.send(kind='gps',data=dict(latitude=31,longitude=120.9992,accuracy_m=2),dt=dt)
 def state(self):return self.e.state('j')
 def test_accept_current_proposal(self):
  r=self.send('可以');self.assertNotIn('consultation',self.state()['journey']);self.assertEqual(self.state()['journey']['last_consultation']['decision']['club'],'5铁');self.assertNotIn('更想怎么处理',r['text']);self.assertEqual(self.state(),self.e.replay('j'))
 def test_choose_driver_not_preference_invention(self):
  r=self.send('我想用一号木');c=self.state()['journey']['consultation'];self.assertEqual(c['suggestion']['club'],'一号木');self.assertNotIn('player_intent',c);self.assertIn('沙坑',r['text']);self.assertNotIn('5铁',r['text']);self.send('OK');self.assertEqual(self.state()['journey']['last_consultation']['decision']['club'],'一号木')
 def test_stale_choice_retained_after_gps(self):
  self.send('我想用一号木',dt=61);self.assertEqual(self.state()['journey']['consultation']['selected_club']['key'],'driver');r=self.gps(dt=1);self.assertIn('一号木',r['text']);self.assertNotIn('5铁',r['text']);self.assertEqual(self.state()['journey']['consultation']['suggestion']['club'],'一号木');self.assertEqual(self.state(),self.e.replay('j'))
 def test_change_after_accept_and_stale(self):
  self.send('可以');self.send('我想用一号木',dt=61);self.gps(dt=1);self.assertEqual(self.state()['journey']['consultation']['suggestion']['club'],'一号木')
 def test_question_is_not_confirmation(self):
  self.send('可以吗？');self.assertNotIn('last_consultation',self.state()['journey'])
if __name__=='__main__':unittest.main()
