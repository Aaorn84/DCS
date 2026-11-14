import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_round_flow as base
from phoenix_demo import preview
from journey_current_distance import current_distance
class CurrentDistanceTests(unittest.TestCase):
 setUp=base.RoundFlowTests.setUp
 tearDown=base.RoundFlowTests.tearDown
 begin=base.RoundFlowTests.begin
 def send(self,text='',gps=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=39,type='gps' if gps else 'message',event_id='d'+str(self.n),observed_at=self.clock.isoformat(),**({'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_current_position_after_map_click(self):
  self.begin();self.send(gps=dict(preview(1)['positions']['fairway'],simulation_source='map_click'))
  for text in ('打多少？','这杆打多少','现在打多远'):
   out=self.send(text);self.assertIn('果岭',out['text']);self.assertNotIn('发球台',out['text']);self.assertNotIn('估算剩余',out['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_hypothetical_and_previous_queries_not_changed(self):
  for text in ('打完后还剩多少','用一号木下一杆还剩多少','上一杆打了多少','下一杆还剩多少'):self.assertFalse(current_distance(text))
 def test_dedup_and_reused_id(self):
  self.begin();self.send('打多少');p=copy.deepcopy(self.last);self.assertTrue(self.e.command('j','retry','journey_event',p,now=self.clock.timestamp())['duplicate']);p['text']='打多远'
  with self.assertRaises(ValueError):self.e.command('j','bad','journey_event',p,now=self.clock.timestamp())
