import sys,unittest,copy
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from lie_position import infer,polygon_contains
class LieTests(unittest.TestCase):
 def setUp(self):
  self.e=Engine(':memory:','lie');self.e.create('j');self.n=0;self.clock=1794000000
  for t in ['先打球','演示球场（合成）','白台','1','轻松打球','状态不错','开始球局']:self.send(t)
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',data=None,dt=0):
  self.n+=1;self.clock+=dt;p=dict(protocol_version=5,type=kind,event_id='e'+str(self.n),observed_at=datetime.fromtimestamp(self.clock,timezone.utc).isoformat())
  if kind=='message':p['text']=text
  else:p['data']=data
  return self.e.command('j',str(self.n),'journey_event',p,now=self.clock)
 def gps(self,lon=121.001,accuracy=2):return self.send(kind='gps',data=dict(latitude=31,longitude=lon,accuracy_m=accuracy))
 def consult(self):
  self.send('这杆怎么打');self.send('稳一点');return self.send('就在球旁')
 def test_map_skips_lie_question(self):
  self.gps();r=self.consult();c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['phase'],'plan');self.assertEqual(c['lie_report'],'球道');self.assertEqual(c['lie_evidence']['source'],'gps_course_surface');self.assertEqual(r['text'].count('？'),1)
 def test_no_gps_answer_advances_without_loop(self):
  self.consult();r=self.send('长草');self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'plan');self.assertNotIn('再确认球位',r['text']);self.send('用熟悉的短杆过渡');self.send('按这个打');self.assertEqual(self.e.state('j')['journey']['last_consultation']['lie_report'],'长草');self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_boundary_asks(self):
  self.gps(lon=121.0005);self.consult();self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'lie')
 def test_stale_asks(self):
  self.gps();self.clock+=61;self.consult();self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'lie')
 def test_inaccurate_asks(self):
  self.gps(accuracy=25);self.consult();self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'lie')
 def test_user_correction_preserved(self):
  self.gps();self.consult();self.send('沙坑');c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['lie_report'],'沙坑');self.assertEqual(c['lie_evidence']['source'],'user_report')
 def test_overlap_or_absent_map_asks(self):
  self.gps();s=self.e.state('j');eid=s['facts']['context.course_snapshot']['value'];h=s['evidence'][eid]['data']['holes'][0];h['surface_zones'].append(dict(h['surface_zones'][0],surface='rough'));self.assertIsNone(infer(s,self.clock));h.pop('surface_zones');self.assertIsNone(infer(s,self.clock))
 def test_polygon_boundary_hole(self):
  outer=[[120.999,30.999],[121.002,30.999],[121.002,31.002],[120.999,31.002],[120.999,30.999]]
  hole=[[121,31],[121.001,31],[121.001,31.001],[121,31.001],[121,31]]
  self.assertTrue(polygon_contains([outer],dict(latitude=31.0005,longitude=121.0005,accuracy_m=2)))
  self.assertFalse(polygon_contains([outer,hole],dict(latitude=31.0005,longitude=121.0005,accuracy_m=2)))
 def test_v3_replay_unchanged(self):
  e=Engine(':memory:','old');e.create('j');p=dict(protocol_version=3,type='message',event_id='old',observed_at=datetime.fromtimestamp(self.clock,timezone.utc).isoformat(),text='可以记住');e.command('j','o','journey_event',p,now=self.clock);self.assertEqual(e.state('j'),e.replay('j'));e.close()
if __name__=='__main__':unittest.main()
