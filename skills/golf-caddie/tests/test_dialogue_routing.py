import unittest,sys,copy,time
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine,fact_value
from journey import view
from dialogue_routing import classify,score_text,resume,execution_club
from phoenix_demo import preview
class DialogueRoutingTests(unittest.TestCase):
 def setUp(self):self.e=Engine(':memory:','a');self.e.create('j');self.n=0
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',**kw):
  self.n+=1;p=dict(protocol_version=32,type=kind,event_id='p'+str(self.n),observed_at=datetime.now().astimezone().isoformat(),**({'text':text} if kind=='message' else {}),**kw);self.last=p
  return self.e.command('j',str(self.n),'journey_event',p)
 def state(self):return self.e.state('j')
 def begin(self):
  for t in ['先打球','东莞凤凰山（A+B蓝台演示）','蓝台','1','轻松打球','开始球局']:self.send(t)
  self.send(kind='gps',data=dict(preview(1)['positions']['fairway'],simulation_source='map_click'))
 def plan(self):
  self.begin();self.send('这杆怎么打');self.send('150')
  if self.state()['journey']['consultation']['phase']=='lie':self.send('球道')
 def test_question_and_execution_have_distinct_taxonomy(self):
  self.begin();s=self.state()
  for text,expected in [('过沙需要多少','fact_request'),('高抛还是切滚','fact_request'),('上一杆用了什么杆？','fact_request'),('我还是用了7铁','execution_report'),('七号铁攻果岭','decision_commitment')]:self.assertEqual(classify(s,text,time.time())['type'],expected)
 def test_score_bypasses_old_plan_and_accepts_natural_confirmation(self):
  self.plan();r=self.send('这洞加二，两推，没有罚杆');self.assertIn('6杆',r['text']);self.assertEqual(self.state()['journey']['response_context']['question_owner'],'score.confirm');self.assertIsNone(fact_value(self.state(),'holes.1.total'))
  self.send('可以');self.assertEqual(fact_value(self.state(),'holes.1.total'),6);self.assertEqual(fact_value(self.state(),'holes.1.putts'),2);self.assertEqual(fact_value(self.state(),'holes.1.penalties'),0);self.assertEqual(self.state(),self.e.replay('j'))
 def test_partial_score_and_penalty_answers_bypass_consultation(self):
  self.plan();self.assertIn('几推',self.send('这洞六杆')['text']);self.assertEqual(view(self.state())['choices'],['一推','两推','三推','不清楚']);self.assertIn('罚杆',self.send('两推')['text']);self.assertIn('确认',self.send('没有')['text']);self.send('好');self.assertEqual(fact_value(self.state(),'holes.1.total'),6)
 def test_fact_interruption_cannot_confirm_score_with_generic_yes(self):
  self.begin();self.send('这洞六杆，两推，0罚杆');self.send('还有多少');self.send('好');self.assertIsNone(fact_value(self.state(),'holes.1.total'));self.assertEqual(view(self.state())['choices'],['继续刚才的问题']);self.assertIn('确认',self.send('继续刚才的问题')['text']);self.send('可以');self.send('确认记录');self.assertEqual(fact_value(self.state(),'holes.1.total'),6)
 def test_fact_interruption_cannot_confirm_old_strategy(self):
  self.plan();self.send('用熟悉的短杆过渡');self.assertEqual(self.state()['journey']['consultation']['phase'],'commit');self.send('还有多少');self.send('可以');self.assertNotIn('decision',self.state()['journey']['consultation']);self.assertIn('方案',self.send('继续刚才的问题')['text']);self.send('好');self.assertNotIn('consultation',self.state()['journey']);self.assertEqual(self.state(),self.e.replay('j'))
 def test_explicit_confirmation_remains_available(self):
  self.plan();self.send('用熟悉的短杆过渡');self.send('确认');self.assertNotIn('consultation',self.state()['journey'])
 def test_execution_is_unattributed_and_not_carry_or_score(self):
  self.plan();profile=copy.deepcopy(self.state()['journey']['profile']);r=self.send('我还是用了7铁');self.assertIn('实际用了7号铁',r['text']);row=self.state()['journey']['execution_reports'][-1];self.assertEqual(row['type'],'execution_report');self.assertIsNone(row['shot_id']);self.assertFalse(row['long_term_learning']);self.assertEqual(profile,self.state()['journey']['profile']);self.assertEqual(view(self.state())['score_summary']['confirmed_holes'],0)
 def test_execution_question_negation_and_future_are_not_reports(self):
  for text in ['我想用7铁','我没用7铁','刚才用的是7铁吗？','刚才不是7铁，是8铁']:self.assertIsNone(execution_club(text))
 def test_new_hole_cannot_resume_old_question(self):
  self.plan();self.send('用熟悉的短杆过渡');s=self.state();s['facts']['context.active_hole']['value']=2;self.assertIn('没有可恢复',resume(s,time.time()))
 def test_explicit_hole_and_default_penalty_normalization(self):
  self.begin();s=self.state();self.assertEqual(score_text(s,'第1洞六杆，两推，没有罚杆'),'1号洞六杆,两推,0罚杆');self.assertIsNone(score_text(s,'6'));self.assertIsNone(score_text(s,'我可能是六杆'))
 def test_duplicate_event_does_not_duplicate_audit(self):
  self.begin();self.send('还有多少');before=len(self.state()['journey']['dialogue_audit']);r=self.e.command('j','retry-other','journey_event',self.last);self.assertTrue(r['duplicate']);self.assertEqual(before,len(self.state()['journey']['dialogue_audit']))
 def test_background_gps_does_not_steal_confirmation(self):
  self.plan();self.send('用熟悉的短杆过渡');context=copy.deepcopy(self.state()['journey']['response_context']);self.send(kind='gps',data=dict(preview(1)['positions']['fairway'],simulation_source='map_click'));self.assertEqual(context,self.state()['journey']['response_context']);self.send('好');self.assertNotIn('consultation',self.state()['journey'])
 def test_thanks_and_smalltalk_are_not_player_plans(self):
  self.plan();before=copy.deepcopy(self.state()['journey']['consultation']);r=self.send('谢谢小鸟');self.assertEqual(r['text'],'不客气，需要时叫我。');self.assertEqual(before,self.state()['journey']['consultation']);r=self.send('今天风景真好');self.assertIn('享受',r['text']);self.assertEqual(before,self.state()['journey']['consultation'])
 def test_offline_whole_journey_demo(self):
  from dialogue_demo import run_demo
  result=run_demo(emit=None);self.assertTrue(result['replay_matches']);self.assertEqual(result['score'],6);self.assertEqual(result['execution_reports'],1);self.assertEqual(result['confirmed_distances'],1);self.assertFalse(result['coach_enabled']);self.assertEqual(result['stage'],'idle')
 def test_unrecognized_question_cannot_become_ball_reply_or_plan(self):
  self.plan();before=copy.deepcopy(self.state()['journey']['consultation']);r=self.send('到水边还有多少？');self.assertNotIn('球旁',r['text']);self.assertNotIn('你选的是',r['text']);self.assertEqual(before,self.state()['journey']['consultation'])
 def test_invalid_score_number_cannot_become_old_carry_answer(self):
  self.begin();self.send('这杆怎么打');self.assertEqual(self.state()['journey']['consultation']['phase'],'approach_club');self.send('这洞六杆');self.send('200');self.assertNotIn('seven',self.state()['journey']['profile']);self.assertEqual(self.state()['session']['draft']['awaiting'],'putts')
 def test_question_owner_follows_current_question_not_old_score(self):
  from dialogue_routing import response_owner,owner_live
  self.begin();self.send('这洞六杆');s=self.state();s['journey']['pending_hazard']={'kind':'bunker'};route={'type':'fact_request','domain':'hazard_distance'}
  self.assertEqual(response_owner(s,route),'hazard.identity');self.assertTrue(owner_live(s,'score.putts'));self.assertTrue(owner_live(s,'hazard.identity'))
if __name__=='__main__':unittest.main()
