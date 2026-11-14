import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_round_flow as base
from journey_carry_report import carry_report
from iron_estimates import iron_table
class CarryReportTests(unittest.TestCase):
 setUp=base.RoundFlowTests.setUp
 tearDown=base.RoundFlowTests.tearDown
 begin=base.RoundFlowTests.begin
 def send(self,text='',gps=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=44,type='gps' if gps else 'message',event_id='c'+str(self.n),observed_at=self.clock.isoformat(),**({'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_correction_keeps_route_and_updates_iron_baseline(self):
  self.begin();self.send('7铁220');before=self.e.state('j');out=self.send('7铁160');s=self.e.state('j');self.assertEqual(out['profile_updated'],'seven');self.assertEqual(s['journey']['profile']['seven']['value']['distance'],160);self.assertEqual(before['journey']['consultation'],s['journey']['consultation']);self.assertEqual(iron_table(s['journey']['profile'])[8]['carry_yards'],150);self.assertEqual(before.get('shot_chain'),s.get('shot_chain'));self.assertEqual(s,self.e.replay('j'))
 def test_execution_distance_not_profile_report(self):
  for text in ('刚才7铁打了160码','用了7铁160码','7铁160吗','上一杆7铁160'):self.assertIsNone(carry_report(text))
 def test_units_duplicate_and_quiet(self):
  self.begin();self.send('7号铁Carry145米');p=copy.deepcopy(self.last);self.assertTrue(self.e.command('j','retry','journey_event',p,now=self.clock.timestamp())['duplicate']);self.send('安静');out=self.send('7铁160码');self.assertEqual(out['text'],'');self.assertEqual(self.e.state('j')['journey']['profile']['seven']['value']['distance'],160)
