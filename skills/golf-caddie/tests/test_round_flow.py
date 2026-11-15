import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_tee_options as base
from phoenix_demo import preview
class RoundFlowTests(unittest.TestCase):
 setUp=base.TeeOptionsTests.setUp
 tearDown=base.TeeOptionsTests.tearDown
 begin=base.TeeOptionsTests.begin
 def send(self,text='',gps=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=38,type='gps' if gps else 'message',event_id='f'+str(self.n),observed_at=self.clock.isoformat(),**({'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_player_driver_assent_and_map_reposition_distance(self):
  self.begin();self.send('一号木吧');out=self.send('好');self.assertNotIn('consultation',self.e.state('j')['journey']);self.assertIn('确认',out['text'])
  out=self.send(gps=dict(preview(1)['positions']['fairway'],simulation_source='map_click'));self.assertFalse(out.get('ignored'));self.assertTrue(out['simulation_reposition'])
  out=self.send('上一杆打了多少');self.assertIn('相距约',out['text']);self.assertIn('只打了一杆',out['text']);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_generic_yes_after_two_choices_does_not_select(self):
  self.begin();self.send('好');self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'tee_options')
 def test_fact_interrupt_does_not_confirm_plan(self):
  self.begin();self.send('一号木吧');self.send('还有多少');self.send('好');self.assertIn('consultation',self.e.state('j')['journey'])
 def test_real_gps_still_rejects_teleport(self):
  self.begin();out=self.send(gps=preview(1)['positions']['fairway']);self.assertTrue(out.get('ignored'));self.assertEqual(out['reason'],'implausible_jump')
 def test_duplicate_is_idempotent(self):
  self.begin();self.send('一号木吧');self.send('好');p=copy.deepcopy(self.last);out=self.e.command('j','retry','journey_event',p,now=self.clock.timestamp());self.assertTrue(out['duplicate'])
