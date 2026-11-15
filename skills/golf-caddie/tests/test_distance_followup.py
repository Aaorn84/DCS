import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_projection as projection_tests
from journey_distance_followup import followup_query
class DistanceFollowupTests(unittest.TestCase):
 setUp=projection_tests.ProjectionTests.setUp
 tearDown=projection_tests.ProjectionTests.tearDown
 begin=projection_tests.ProjectionTests.begin
 def send(self,text='',gps=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=35,type='gps' if gps else 'message',event_id='f'+str(self.n),observed_at=self.clock.isoformat(),**({'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_exact_user_followup_uses_long_iron_plan(self):
  self.begin();before=copy.deepcopy(self.e.state('j'));r=self.send('下一杆还剩多少');self.assertEqual(r['projection']['club_key'],'long_iron');self.assertIn('预计还剩',r['text'])
  after=self.e.state('j');self.assertEqual(before['facts'],after['facts']);self.assertEqual(before['journey']['consultation'],after['journey']['consultation']);self.assertEqual(before['journey']['profile'],after['journey']['profile']);self.assertEqual(after,self.e.replay('j'))
 def test_variants_are_contextual_queries(self):
  for t in ['下一杆还剩多少','下一杆还有多远？','那么下一杆大概还剩多少','下一杆到果岭还剩多少米']:self.assertIsNotNone(followup_query(t),t)
  for t in ['还有多远','上一杆打了多少','下一杆用几号铁','过沙需要多少']:self.assertIsNone(followup_query(t),t)
 def test_no_proposal_asks_single_scope_question(self):
  self.begin(False);r=self.send('下一杆还剩多少');self.assertNotIn('projection',r);self.assertEqual(r['text'].count('？'),1);self.assertNotIn('不能可靠判断',r['text'])
  r=self.send('现在');self.assertIn('果岭',r['text']);self.assertNotIn('预计',r['text'])
 def test_club_reply_then_carry_reply_completes_estimate(self):
  self.begin(False);self.send('下一杆还剩多少');r=self.send('长铁');self.assertEqual(r.get('missing_club'),'long_iron');r=self.send('190');self.assertIn('预计还剩',r['text']);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_estimate_choice_keeps_club_question_owned(self):
  self.begin(False);self.send('下一杆还剩多少');r=self.send('预计剩余距离');self.assertEqual(r['text'].count('？'),1);self.assertIn('哪支杆',r['text']);self.send('长铁');r=self.send('190');self.assertIn('预计还剩',r['text'])
 def test_followup_does_not_confirm_plan(self):
  self.begin();before=copy.deepcopy(self.e.state('j')['journey']['consultation']);self.send('下一杆还剩多少');self.send('好');self.assertEqual(before,self.e.state('j')['journey']['consultation'])
 def test_stale_fix_does_not_create_estimated_distance(self):
  self.begin();self.clock+=timedelta(minutes=5);r=self.send('下一杆还剩多少');self.assertIsNone(r['projection']);self.assertIn('位置',r['text'])
 def test_raw_event_id_is_still_idempotent(self):
  self.begin();self.send('下一杆还剩多少');p=copy.deepcopy(self.last);r=self.e.command('j','retry','journey_event',p,now=self.clock.timestamp());self.assertTrue(r['duplicate']);p['text']='还有多少'
  with self.assertRaises(ValueError):self.e.command('j','bad','journey_event',p,now=self.clock.timestamp())
 def test_old_protocol_keeps_previous_followup_behavior(self):
  self.begin();self.n+=1;self.clock+=timedelta(seconds=1);r=self.e.command('j','legacy','journey_event',dict(protocol_version=34,type='message',event_id='old-followup',observed_at=self.clock.isoformat(),text='下一杆还剩多少'),now=self.clock.timestamp());self.assertIn('不能可靠判断',r['text']);self.assertEqual(self.e.state('j'),self.e.replay('j'))
if __name__=='__main__':unittest.main()
