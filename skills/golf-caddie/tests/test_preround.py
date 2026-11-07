import sys,unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from journey import view
class Tests(unittest.TestCase):
 def setUp(self):self.e=Engine(':memory:','a');self.e.create('j');self.n=0;self.t=datetime.now().astimezone()-timedelta(seconds=16)
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',**kw):
  self.n+=1
  return self.e.command('j',str(self.n),'journey_event',dict(protocol_version=22,type=kind,event_id='p'+str(self.n),observed_at=self.t.isoformat(),**({'text':text} if kind=='message' else {}),**kw))
 def start(self):
  for t in ['先打球','演示球场（合成）','蓝台']:self.send(t)
 def test_relax_skips_condition_and_replays(self):
  self.start();self.send('1');r=self.send('轻松打球');self.assertEqual(view(self.e.state('j'))['stage'],'ready');self.assertIn('轻松打',r['text']);self.send('开始球局');self.assertTrue(self.e.state('j')['journey']['round']['service_policy']['relaxed']);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_fatigue_reversible_not_carry(self):
  self.start();self.send('1');self.send('争取成绩');self.send('开始球局');self.send('今天有点累');self.assertTrue(self.e.state('j')['journey']['round']['service_policy']['fatigued']);self.send('状态恢复了');self.assertFalse(self.e.state('j')['journey']['round']['service_policy']['fatigued'])
 def test_gps_dwell_selects_start(self):
  self.start()
  for _ in range(3):
   self.send(kind='gps',data={'latitude':31,'longitude':120.9992,'accuracy_m':2});self.t+=timedelta(seconds=8)
  j=self.e.state('j')['journey'];self.assertEqual(j['round']['start_hole'],1);self.assertEqual(j['round']['start_hole_source'],'gps_tee_dwell');self.assertEqual(j['stage'],'goal');self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_bad_accuracy_does_not_select(self):
  self.start();self.send(kind='gps',data={'latitude':31,'longitude':120.9992,'accuracy_m':100});self.assertNotIn('start_hole',self.e.state('j')['journey']['round'])
if __name__=='__main__':unittest.main()
