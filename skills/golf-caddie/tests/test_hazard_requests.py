import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hazard_requests import parse,answer
from test_strategy_choices import ChoiceTests
class HazardTests(ChoiceTests):
 def send(self,text='',kind='message',data=None,dt=0):
  from datetime import datetime,timezone
  self.clock+=dt;self.n+=1;p=dict(protocol_version=17,type=kind,event_id='e'+str(self.n),observed_at=datetime.fromtimestamp(self.clock,timezone.utc).isoformat())
  if kind=='message':p['text']=text
  else:p['data']=data
  return self.e.command('j',str(self.n),'journey_event',p,now=self.clock)
 def test_over_bunker_not_a_strategy_answer(self):
  before=copy.deepcopy(self.state()['journey']['consultation']);r=self.send('过沙需要多少？');self.assertIn('远沿',r['text']);self.assertNotIn('更想怎么处理',r['text']);self.assertEqual(before,self.state()['journey']['consultation']);self.assertEqual(self.state(),self.e.replay('j'))
 def test_measured_far_edge_only(self):
  s=self.state();eid=s['facts']['context.course_snapshot']['value'];h=s['evidence'][eid]['data']['holes'][0]['tee_strategy']['landing_zones'][0]['hazards'][0]
  h.update(id='bunker1',far_edge=dict(latitude=31,longitude=121.001,verified=True,source='survey'))
  r=answer(s,parse('过沙需要多少'),self.clock);self.assertIn('约',r);self.assertIn('远沿',r)
  h['far_edge']['verified']=False;self.assertIn('没有可靠数据',answer(s,parse('过沙需要多少'),self.clock))
 def test_bare_reference_never_far_edge(self):
  r=self.send('过沙需要多少');self.assertNotIn('约',r['text']);self.assertIn('没有可靠数据',r['text'])
 def test_bunker_and_water_forms(self):
  for q in ('过沙需要多少','飞过右侧沙坑多少码','过水多远','越过水需要多少米'):self.assertIsNotNone(parse(q))
  self.assertIsNone(parse('我上杆打进沙坑'))
