import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_tee_options as base
from phoenix_demo import preview
class SpokenAssentTests(unittest.TestCase):
 setUp=base.TeeOptionsTests.setUp
 tearDown=base.TeeOptionsTests.tearDown
 begin=base.TeeOptionsTests.begin
 def send(self,text='',gps=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=46,type='gps' if gps else 'message',event_id='f'+str(self.n),observed_at=self.clock.isoformat(),**({'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_hmm_confirms_single_driver_proposal(self):
  self.begin();self.send('1号木');out=self.send('嗯');self.assertIn('确认',out['text']);self.assertNotIn('consultation',self.e.state('j')['journey']);self.assertFalse(self.e.state('j')['journey'].get('execution_reports'));self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_two_options_not_chosen_by_hmm(self):
  self.begin();out=self.send('嗯嗯');self.assertIn('保守方案还是进取方案',out['text']);self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'tee_options')
 def test_fact_interrupt_not_confirmed_by_hmm(self):
  self.begin();self.send('1号木');self.send('还有多少');self.send('嗯');self.assertIn('consultation',self.e.state('j')['journey'])
 def test_uncertain_or_negative_not_assent(self):
  from journey_spoken_assent import spoken_assent
  for text in ('嗯？','嗯不行','嗯再想想','嗯可能吧','嗯不要'):self.assertFalse(spoken_assent(text))
  for text in ('嗯','嗯嗯','嗯，好','嗯可以'):self.assertTrue(spoken_assent(text))
