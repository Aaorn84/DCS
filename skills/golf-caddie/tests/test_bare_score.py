import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_round_flow as base
from journey import view
from round_state import fact_value
class BareScoreTests(unittest.TestCase):
 setUp=base.RoundFlowTests.setUp
 tearDown=base.RoundFlowTests.tearDown
 begin=base.RoundFlowTests.begin
 def send(self,text='',gps=None,hole=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=45,type='simulation_hole' if hole is not None else 'gps' if gps else 'message',event_id='h'+str(self.n),observed_at=self.clock.isoformat(),**({'hole':hole} if hole is not None else {'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_bare_total_after_gps_and_tee_brief(self):
  from phoenix_demo import preview
  self.begin();self.send('换洞时提醒记分');self.send(hole=2);self.send(gps=dict(preview(2)['positions']['tee'],simulation_source='map_click'));self.send('到发球台了');out=self.send('5');self.assertIn('推',out['text']);draft=self.e.state('j')['session']['draft'];self.assertEqual(draft['hole'],1);self.assertEqual(draft['total'],5);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_chinese_number_and_idempotency(self):
  self.begin();self.send('换洞时提醒记分');self.send(hole=2);self.send('五');p=copy.deepcopy(self.last);self.assertTrue(self.e.command('j','retry','journey_event',p,now=self.clock.timestamp())['duplicate']);self.assertEqual(self.e.state('j')['session']['draft']['total'],5)
 def test_without_pending_score_not_recorded(self):
  self.begin(False);self.send('5');self.assertIsNone(self.e.state('j')['session']['draft'])
