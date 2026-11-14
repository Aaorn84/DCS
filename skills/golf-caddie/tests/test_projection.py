import unittest,sys,copy
from pathlib import Path
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from journey_projection import projection_query
from round_state import Engine,fact_value
from phoenix_demo import preview
class ProjectionTests(unittest.TestCase):
 def setUp(self):self.e=Engine(':memory:','p');self.e.create('j');self.n=0;self.clock=datetime.fromisoformat('2026-11-08T00:00:00Z')
 def tearDown(self):self.e.close()
 def send(self,text='',gps=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=34,type='gps' if gps else 'message',event_id='p'+str(self.n),observed_at=self.clock.isoformat(),**({'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def begin(self,plan=True):
  for t in ['先打球','东莞凤凰山（A+B蓝台演示）','蓝台','1','轻松打球','开始球局']:self.send(t)
  self.send(gps=dict(preview(1)['positions']['tee'],simulation_source='map_click'))
  if plan:
   for t in ['怎么打','260','220','190']:self.send(t)
 def test_user_full_dialogue_and_read_only_estimate(self):
  self.begin();out=self.send('还有多远');self.assertIn('果岭',out['text']);self.assertNotIn('不能可靠判断',out['text'])
  self.send('还有多少？');self.send('好')
  before=copy.deepcopy(self.e.state('j'));out=self.send('长铁开球之后还剩多少？');self.assertIn('预计还剩',out['text']);self.assertIn('实际落点',out['text']);self.assertEqual(out['projection']['basis'],'mapped_landing_reference')
  after=self.e.state('j');self.assertEqual(before['facts'],after['facts']);self.assertEqual(before['journey']['profile'],after['journey']['profile']);self.assertEqual(before['journey']['consultation'],after['journey']['consultation']);self.assertEqual(after,self.e.replay('j'))
 def test_acknowledgement_after_estimate_does_not_commit_old_plan(self):
  self.begin();before=copy.deepcopy(self.e.state('j')['journey']['consultation']);self.send('长铁开球后还有多远');self.send('好');self.assertEqual(before,self.e.state('j')['journey']['consultation'])
 def test_anonymous_followup_uses_pending_club(self):
  self.begin();out=self.send('那打完还剩多少');self.assertEqual(out['projection']['club_key'],'long_iron')
 def test_named_club_is_not_replaced_by_suggestion(self):
  self.begin();out=self.send('一号木开球之后还剩多少');self.assertEqual(out['projection']['club_key'],'driver');self.assertEqual(out['projection']['carry_yards'],260)
 def test_missing_carry_is_asked_once_and_answer_used(self):
  self.begin(False);out=self.send('长铁开球之后还剩多少');self.assertEqual(out.get('missing_club'),'long_iron');self.assertEqual(out['text'].count('？'),1)
  out=self.send('190');self.assertEqual(out['projection']['carry_yards'],190);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_projection_requires_current_tee_location(self):
  self.begin();self.clock+=timedelta(minutes=5);out=self.send('长铁开球之后还剩多少');self.assertIsNone(out['projection']);self.assertIn('位置',out['text']);self.assertNotIn('预计还剩',out['text'])
 def test_no_fake_zero_when_club_would_overshoot(self):
  self.begin();s=self.e.state('j');# Query known club only; synthetic extreme carry provided through owned question.
  self.send('5铁开球之后还剩多少');out=self.send('400');self.assertIsNone(out['projection']);self.assertIn('超过',out['text'])
 def test_question_domains_are_distinct(self):
  for t in ['还有多远','还有多少','上一杆打了多少','刚才长铁开球后还剩多少','已经用长铁开球了','过沙需要多少']:self.assertIsNone(projection_query(t),t)
  for t in ['长铁开球之后还剩多少？','用3号木开球后还有多远','那打完还剩多少']:self.assertIsNotNone(projection_query(t),t)
 def test_quiet_suppresses_estimate_speech(self):
  self.begin();self.send('安静');out=self.send('长铁开球之后还剩多少');self.assertEqual(out['text'],'');self.assertFalse(out['speak_allowed'])
 def test_duplicate_and_changed_payload(self):
  self.begin();self.send('长铁开球之后还剩多少');p=copy.deepcopy(self.last);out=self.e.command('j','retry','journey_event',p,now=self.clock.timestamp());self.assertTrue(out['duplicate'])
  p['text']='一号木开球后还剩多少'
  with self.assertRaises(ValueError):self.e.command('j','bad','journey_event',p,now=self.clock.timestamp())
if __name__=='__main__':unittest.main()
