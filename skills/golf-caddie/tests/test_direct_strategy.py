from test_approach_strategy import ApproachTests
class DirectTests(ApproachTests):
 def send(self,text='',kind='message',data=None):
  from datetime import datetime,timezone
  self.n+=1;p=dict(protocol_version=6,type=kind,event_id='e'+str(self.n),observed_at=datetime.fromtimestamp(self.now,timezone.utc).isoformat())
  if kind=='message':p['text']=text
  else:p['data']=data
  return self.e.command('j',str(self.n),'journey_event',p,now=self.now)
 def test_direct_answer_before_question(self):
  self.gps();r=self.send('这杆怎么打');self.assertIn('7铁可以作为',r['text']);self.assertIn('障碍',r['text']);self.assertNotIn('你想怎么处理',r['text']);self.assertEqual(r['text'].count('？'),1);self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'ball')
 def test_distance_followup_risk(self):
  self.gps();r=self.send('下一杆有什么风险');self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'ball');self.assertIn('Carry',r['text'])
 def test_candidate_after_ball_confirmation(self):
  self.gps();self.send('这杆怎么打');r=self.send('就在球旁');self.assertIn('7铁可以作为',r['text'])
 def test_risk_not_a_plan_or_decision(self):
  self.gps();self.send('这杆怎么打');self.send('就在球旁');self.send('有什么风险');c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['phase'],'plan');self.assertNotIn('decision',c);self.assertEqual(self.e.state('j'),self.e.replay('j'))
