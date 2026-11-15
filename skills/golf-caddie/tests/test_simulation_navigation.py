import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_round_flow as base
from journey import view
from round_state import fact_value
class SimulationNavigationTests(unittest.TestCase):
 setUp=base.RoundFlowTests.setUp
 tearDown=base.RoundFlowTests.tearDown
 begin=base.RoundFlowTests.begin
 def send(self,text='',gps=None,hole=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=41,type='simulation_hole' if hole is not None else 'gps' if gps else 'message',event_id='h'+str(self.n),observed_at=self.clock.isoformat(),**({'hole':hole} if hole is not None else {'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_switch_arbitrary_hole_without_score_or_shot(self):
  self.begin();before=self.e.state('j');self.send(hole=8);s=self.e.state('j');self.assertEqual(fact_value(s,'context.active_hole'),8);self.assertEqual(view(s)['simulation']['hole'],8);self.assertNotIn('consultation',s['journey']);self.assertEqual(before.get('shot_chain'),s.get('shot_chain'));self.assertEqual(before['session']['draft'],s['session']['draft']);self.assertEqual(view(before)['score_summary'],view(s)['score_summary']);self.assertEqual(s,self.e.replay('j'));self.send(hole=1);self.assertEqual(fact_value(self.e.state('j'),'context.active_hole'),1)
 def test_invalid_hole_and_dedup(self):
  self.begin();self.send(hole=18);p=copy.deepcopy(self.last);self.assertTrue(self.e.command('j','retry','journey_event',p,now=self.clock.timestamp())['duplicate'])
  with self.assertRaises(ValueError):self.send(hole=19)
 def test_rejected_outside_active_round(self):
  self.send('先打球')
  with self.assertRaises(ValueError):self.send(hole=2)
