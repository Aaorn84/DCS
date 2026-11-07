import sys,unittest,time,copy
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from journey import reduce_journey
from phoenix_demo import preview
from decision_queries import approach_selection,previous_distance,distance_answer
import test_shot_chain
class DecisionRoutingTests(unittest.TestCase):
 def test_prospective_not_execution(self):
  self.assertEqual(approach_selection('七号铁攻果岭')['club'],'7号铁')
  for t in ['刚才用了七号铁攻果岭','七号铁攻果岭可以吗？','你觉得用哪支杆']:self.assertIsNone(approach_selection(t))
 def test_fact_request_variants(self):
  for t in ['上一杆打了多少？','上一杆距离多少米','刚才那杆有多远']:self.assertTrue(previous_distance(t))
 def test_old_ball_prompt_cannot_swallow_decision_or_query(self):
  e=Engine(':memory:','a');e.create('j');n=0
  def send(text=None):
   nonlocal n;n+=1;p=dict(protocol_version=27,type='gps' if text is None else 'message',event_id='p'+str(n),observed_at=datetime.now().astimezone().isoformat())
   if text is None:p['data']=dict(preview(1)['positions']['fairway'],simulation_source='map_click')
   else:p['text']=text
   return e.command('j',str(n),'journey_event',p)
  try:
   for t in ['先打球','东莞凤凰山（A+B蓝台演示）','蓝台','1','轻松打球','开始球局',None,'用哪支杆','160']:send(t)
   s=e.state('j');s['journey']['consultation']['phase']='ball'
   p=dict(protocol_version=27,type='message',event_id='direct',observed_at=datetime.now().astimezone().isoformat(),text='上一杆打了多少？')
   r=reduce_journey(s,p,s['version']+1,time.time());self.assertIn('暂时算不出',r['text']);self.assertEqual(s['journey']['consultation']['phase'],'ball')
   p.update(event_id='direct2',text='七号铁攻果岭');r=reduce_journey(s,p,s['version']+2,time.time());self.assertNotIn('球旁',r['text']);self.assertNotIn('consultation',s['journey']);self.assertFalse(s['journey']['player_decisions'][-1]['execution_confirmed'])
   r=send('七号铁攻果岭');self.assertIn('7号铁',r['text']);send(None);r=send('上一杆打了多少？');self.assertIn('暂时算不出',r['text']);self.assertNotIn('shot_chain',e.state('j'));self.assertEqual(e.state('j'),e.replay('j'))
  finally:e.close()
 def test_valid_chain_distance_and_invalidated_record(self):
  chain=test_shot_chain.ChainTests();chain.setUp()
  try:
   chain.setup_shot();chain.stage('execution_report',dict(club='7i'));chain.gps();s=chain.e.state('r');s['facts']['context.active_hole']={'value':1,'valid':True}
   self.assertIn('水平总距离',distance_answer(s,'上一杆打了多少'))
   for d in s['derived'].values():d['valid']=False
   self.assertIn('暂时算不出',distance_answer(s,'上一杆打了多少'))
  finally:chain.tearDown()
if __name__=='__main__':unittest.main()
