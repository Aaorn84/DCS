import sys,unittest,copy
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from journey import demo_course
from tee_strategy_previous import analyze,proposal
class TeeTests(unittest.TestCase):
 def setUp(self):
  self.e=Engine(':memory:','tee');self.e.create('j');self.n=0;self.clock=1794000000
  for text in ['可以记住','球友','可以','可以','230','140','偏右','演示球场（合成）','白台','1','轻松打球','状态不错','开始球局']:self.send(text)
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',data=None,dt=0):
  self.n+=1;self.clock+=dt
  p=dict(protocol_version=5,type=kind,event_id='t'+str(self.n),observed_at=datetime.fromtimestamp(self.clock,timezone.utc).isoformat())
  if kind=='message':p['text']=text
  else:p['data']=data
  return self.e.command('j',str(self.n),'journey_event',p,now=self.clock)
 def gps(self,dt=0,accuracy=2,lon=120.9992):return self.send(kind='gps',data=dict(latitude=31,longitude=lon,accuracy_m=accuracy),dt=dt)
 def test_carry_and_intent_then_commit(self):
  self.assertEqual(self.e.state('j')['journey']['profile']['driver']['value']['distance_type'],'carry')
  self.gps();self.gps(8);r=self.gps(8);self.assertIn('果岭中心',r['text']);self.assertEqual(r['text'].count('？'),1)
  r=self.send('稳一点');self.assertIn('一号木',r['text']);self.assertIn('沙坑',r['text']);self.assertIn('偏右',r['text'])
  self.send('按这个打');self.assertIn('decision',self.e.state('j')['journey']['last_consultation']);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_arrival_dedup(self):
  self.gps();self.gps(8);self.gps(8);self.assertEqual(self.gps(8)['text'],'')
 def test_accuracy_resets_dwell(self):
  self.gps();self.gps(8,accuracy=40);self.assertEqual(self.gps(8)['text'],'');self.assertEqual(self.gps(8)['text'],'');self.assertIn('果岭中心',self.gps(8)['text'])
 def test_quiet(self):
  self.send('安静');self.gps();self.gps(8);self.assertEqual(self.gps(8)['text'],'')
 def test_missing_carry_not_inferred(self):
  self.gps();s=self.e.state('j');s['journey']['profile']['driver']['value']['distance_type']='total';s['journey']['profile'].pop('seven')
  a=analyze(s,self.clock);self.assertEqual(a['clubs'],{});self.assertEqual(proposal(a,'稳')['options'],[])
 def test_par_five_and_meters(self):
  self.gps();a=analyze(self.e.state('j'),self.clock);a['par']=5;r=proposal(a,'稳','米');self.assertIn('不默认两杆',r['text']);self.assertIn('米',r['text']);self.assertNotIn('码',r['text'])
 def test_map_missing_and_malformed(self):
  self.gps();s=self.e.state('j');eid=s['facts']['context.course_snapshot']['value'];s['evidence'][eid]['data']['holes'][0]['tee_strategy']['landing_zones']=[{}];self.assertEqual(analyze(s,self.clock)['candidates'],[])
 def test_position_change_invalidates(self):
  self.gps();self.send('到发球台了');self.gps(8,lon=120.99921);r=self.send('稳一点');self.assertIn('变化',r['text'])
 def test_disabled(self):
  self.send('不要发球台简报');self.gps();self.gps(8);self.assertEqual(self.gps(8)['text'],'')
if __name__=='__main__':unittest.main()
