import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_simulation_navigation as base
from phoenix_demo import preview
class ParThreeTests(unittest.TestCase):
 setUp=base.SimulationNavigationTests.setUp
 tearDown=base.SimulationNavigationTests.tearDown
 begin=base.SimulationNavigationTests.begin
 def send(self,text='',gps=None,hole=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=43,type='simulation_hole' if hole is not None else 'gps' if gps else 'message',event_id='t'+str(self.n),observed_at=self.clock.isoformat(),**({'hole':hole} if hole is not None else {'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_par3_tee_not_fairway_question(self):
  self.begin(False);self.send(hole=2);out=self.send('怎么打');self.assertIn('7号铁',out['text']);out=self.send('160');self.assertIn('旗',out['text']);c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['lie_report'],'发球台');self.assertEqual(c['ball_position_report'],'simulation_selected');self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_preset_gps_does_not_lose_tee_context(self):
  self.begin(False);self.send(hole=2);self.send(gps=preview(2)['positions']['tee']);out=self.send('怎么打');self.assertNotIn('球旁',out['text']);self.assertNotIn('球道、长草',out['text'])
 def test_stale_location_not_falsely_accepted(self):
  self.begin(False);self.send(hole=2);self.clock+=timedelta(minutes=2);self.send('怎么打');self.assertNotEqual(self.e.state('j')['journey'].get('consultation',{}).get('lie_report'),'发球台')
