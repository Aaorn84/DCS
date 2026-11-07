import unittest,sys,time,copy
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from green_context import answer,resolve,remember
import test_green_space
from round_state import Engine
from phoenix_demo import preview
class GreenContextTests(unittest.TestCase):
 def test_left_and_right_measure_from_their_own_edges(self):
  s=test_green_space.GreenSpaceTests().scene()
  for q,side in [('果岭左侧有多少空间','左'),('果岭右侧有多少空间','右')]:
   r=answer(s,q,time.time());self.assertIn('果岭'+side+'沿到球洞图示边界约35码',r)
 def test_context_inherits_but_not_across_hole_map_or_timeout(self):
  s=test_green_space.GreenSpaceTests().scene();now=time.time();remember(s,now)
  self.assertEqual(resolve(s,'左侧有多少空间？',now+1),'果岭左侧有多少空间？')
  self.assertIn('果岭右侧',resolve(s,'右侧呢',now+2))
  self.assertEqual(resolve(s,'左侧有多少空间',now+301),'')
  s['facts']['context.active_hole']['value']=2;self.assertEqual(resolve(s,'左侧有多少空间',now+1),'')
 def test_no_unrelated_entity_inheritance(self):
  s=test_green_space.GreenSpaceTests().scene();now=time.time();remember(s,now)
  self.assertIsNone(resolve(s,'球道左侧有多少空间',now+1))
 def test_whole_conversation_preserves_plan_and_replays(self):
  e=Engine(':memory:','a');e.create('j');n=0
  def send(text=None):
   nonlocal n;n+=1
   p=dict(protocol_version=26,type='gps' if text is None else 'message',event_id='p'+str(n),observed_at=datetime.now().astimezone().isoformat())
   if text is None:p['data']=dict(preview(1)['positions']['fairway'],simulation_source='map_click')
   else:p['text']=text
   return e.command('j',str(n),'journey_event',p)
  try:
   for t in ['先打球','东莞凤凰山（A+B蓝台演示）','蓝台','1','轻松打球','开始球局',None,'用哪支杆','160']:send(t)
   c=copy.deepcopy(e.state('j')['journey']['consultation'])
   for t in ['果岭后面有多少空间','左侧有多少空间？','右侧有多少空间？']:
    r=send(t);self.assertNotIn('球旁',r['text']);self.assertNotIn('你是问',r['text']);self.assertIn('果岭',r['text']);self.assertEqual(c,e.state('j')['journey']['consultation'])
   send(None);self.assertIn('果岭',send('左侧呢')['text'])
   send('今天只想放松');self.assertNotIn('green_query_context',e.state('j')['journey'])
   self.assertEqual(e.state('j'),e.replay('j'))
  finally:e.close()
if __name__=='__main__':unittest.main()
