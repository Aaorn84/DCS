import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_round_flow as base
from journey import view
from round_state import fact_value
class SimulationScoreTests(unittest.TestCase):
 setUp=base.RoundFlowTests.setUp
 tearDown=base.RoundFlowTests.tearDown
 begin=base.RoundFlowTests.begin
 def send(self,text='',gps=None,hole=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=42,type='simulation_hole' if hole is not None else 'gps' if gps else 'message',event_id='h'+str(self.n),observed_at=self.clock.isoformat(),**({'hole':hole} if hole is not None else {'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_next_hole_prompts_and_score_belongs_to_previous(self):
  self.begin();self.send('换洞时提醒记分');out=self.send(hole=2);self.assertIn('第1洞',out['text']);self.assertEqual(out['text'].count('？'),1);self.assertEqual(self.e.state('j')['session']['score_target'],1)
  out=self.send('5杆');self.assertIn('推',out['text']);self.assertEqual(self.e.state('j')['session']['draft']['hole'],1);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_disabled_or_skip_hole_does_not_prompt(self):
  self.begin();self.send('不要主动提醒');self.assertEqual(self.send(hole=2)['text'],'');self.send('换洞时提醒记分');self.assertEqual(self.send(hole=5)['text'],'')
 def test_quiet_and_dedup(self):
  self.begin();self.send('换洞时提醒记分');self.send('安静');self.assertEqual(self.send(hole=2)['text'],'');p=copy.deepcopy(self.last);self.assertTrue(self.e.command('j','retry','journey_event',p,now=self.clock.timestamp())['duplicate'])
