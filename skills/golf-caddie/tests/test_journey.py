import sys,unittest,copy,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine,StateError,Conflict
from journey import view,compare
STAMP='2026-11-07T00:00:00+08:00'
class JourneyTests(unittest.TestCase):
 def setUp(self):self.e=Engine(':memory:','a');self.e.create('j');self.n=0
 def tearDown(self):self.e.close()
 def send(self,text='',type='message',**kw):
  self.n+=1
  return self.e.command('j',str(self.n),'journey_event',dict(protocol_version=5,type=type,event_id='e'+str(self.n),observed_at=STAMP,**({'text':text} if type=='message' else {}),**kw))
 def state(self):return self.e.state('j')
 def onboarding(self,memory='可以记住'):
  for t in [memory,'阿明','可以提醒','不记录击球','230','140','偏右']:self.send(t)
  self.assertEqual(view(self.state())['stage'],'course')
 def begin(self):
  for t in ['演示球场（合成）','蓝台','1','轻松打球','状态不错','开始球局']:self.send(t)
  self.assertEqual(view(self.state())['stage'],'active')
 def finish(self):
  for t in ['结束球局','确认结束','挺开心']:self.send(t)
 def test_whole_journey_and_return(self):
  self.send(type='resume');self.onboarding();self.begin()
  for t in ['这洞六杆','两推','没有罚杆','确认']:self.send(t)
  self.finish();self.assertEqual(view(self.state())['score_summary']['confirmed_subtotal'],6)
  self.send('下一场');self.assertEqual(view(self.state())['stage'],'course')
  self.assertEqual(view(self.state())['profile']['seven']['value']['distance_type'],'carry')
  self.begin();self.assertEqual(view(self.state())['score_summary']['confirmed_holes'],0)
  self.assertEqual(len(view(self.state())['history']),1)
  self.assertEqual(self.state(),self.e.replay('j'))
 def test_skip_does_not_block(self):
  for t in ['仅本场','跳过','跳过','跳过','跳过','跳过','跳过']:self.send(t)
  self.assertEqual(view(self.state())['stage'],'course')
 def test_no_memory_clears_on_return(self):
  self.onboarding('仅本场');self.begin();self.finish();self.send('下一场')
  self.assertEqual(view(self.state())['profile'],{})
  self.assertEqual(view(self.state())['stage'],'proactive')
 def test_coach_not_enabled_by_score(self):
  self.onboarding();self.begin();self.finish();self.assertFalse(view(self.state())['coach']['enabled'])
 def test_one_focus_and_next_round_practice(self):
  self.onboarding();self.begin();self.finish()
  for t in ['我想改善','愿意跟踪','减少三推','接受计划']:self.send(t)
  self.assertEqual(view(self.state())['coach']['plan']['focus'],'减少三推')
  self.send('下一场');self.assertEqual(view(self.state())['stage'],'practice')
  self.send('没练');self.begin();self.finish()
  checks=view(self.state())['coach']['plan']['checks'];self.assertEqual(checks[0]['decision'],'evidence_insufficient')
 def test_coach_closes_and_stays_closed(self):
  self.onboarding();self.begin();self.finish();self.send('我想改善');self.send('不想提升')
  self.send('下一场');self.assertEqual(view(self.state())['stage'],'course');self.assertFalse(view(self.state())['coach']['enabled'])
 def test_quiet_and_resume_do_not_advance(self):
  self.send('可以记住');self.send('安静');self.assertEqual(self.send('阿明')['text'],'')
  self.assertEqual(view(self.state())['stage'],'name');self.send('继续');self.send('阿明')
  self.assertEqual(view(self.state())['stage'],'proactive')
 def test_journal_operation_retry(self):
  p=dict(protocol_version=5,type='message',event_id='retry',observed_at=STAMP,text='可以记住')
  a=self.e.command('j','retry','journey_event',p);b=self.e.command('j','retry','journey_event',p)
  self.assertEqual(a,b);self.assertEqual(self.state()['version'],1)
 def test_event_retry_new_operation(self):
  p=dict(protocol_version=5,type='message',event_id='retry',observed_at=STAMP,text='可以记住')
  self.e.command('j','a','journey_event',p);b=self.e.command('j','b','journey_event',p)
  self.assertTrue(b['duplicate']);self.assertEqual(view(self.state())['stage'],'name')
 def test_invalid_event_rolls_back(self):
  before=self.state()
  with self.assertRaises(StateError):self.send(type='gps',data={})
  self.assertEqual(self.state(),before)
 def test_no_companion_pollution(self):
  self.onboarding();self.begin();self.send('今天风景不错')
  self.assertEqual(view(self.state())['score_summary']['confirmed_holes'],0)
 def test_memory_explicit_only(self):
  self.send('仅本场')
  with self.assertRaises(StateError):self.send('记住：喜欢早场')
  self.assertNotIn('personal_note',view(self.state())['profile'])
 def test_late_score_requires_confirmation(self):
  self.onboarding();self.begin();self.send('这洞五杆');self.send('两推')
  with self.assertRaises(StateError):self.finish()
  self.send('继续打球');self.send('确认');self.send('确认');self.finish()
 def test_owner_isolation(self):
  self.onboarding()
  with tempfile.TemporaryDirectory() as d:
   a=Engine(d+'/db','a');b=Engine(d+'/db','b');a.create('j');b.create('j')
   a.command('j','1','journey_event',dict(protocol_version=5,type='message',event_id='e',observed_at=STAMP,text='可以记住'))
   self.assertNotIn('journey',b.state('j'));a.close();b.close()
 def test_restart_restores(self):
  with tempfile.TemporaryDirectory() as d:
   a=Engine(d+'/db','a');a.create('j');a.command('j','1','journey_event',dict(protocol_version=5,type='message',event_id='e',observed_at=STAMP,text='可以记住'));a.close()
   b=Engine(d+'/db','a');self.assertEqual(view(b.state('j'))['stage'],'name');self.assertEqual(b.state('j'),b.replay('j'));b.close()
 def test_one_question_per_turn(self):
  r=self.send(type='resume');self.assertEqual(r['text'].count('？'),1)
  for t in ['可以记住','阿明','可以提醒','可以记录','230','140','偏右']:
   self.assertLessEqual(self.send(t)['text'].count('？'),1)
 def test_no_autograduation(self):
  b={'putt_opportunities':8,'three_putts':4};n={'putt_opportunities':8,'three_putts':1}
  self.assertEqual(compare({'focus':'减少三推','baseline':b},n)['decision'],'consolidate')
 def test_quick_start_defers_onboarding(self):
  self.send('先打球，稍后了解');self.assertEqual(view(self.state())['stage'],'course')
  self.begin();self.assertFalse(view(self.state())['coach']['enabled'])
 def test_one_time_advice_does_not_enable_tracking(self):
  self.onboarding();self.begin();self.finish()
  for t in ['我想改善','只聊这一次','减少三推','接受计划']:self.send(t)
  self.assertFalse(view(self.state())['coach']['enabled']);self.assertIsNone(view(self.state())['coach']['plan'])
 def test_memory_revocation_disables_coaching(self):
  self.onboarding();self.send('关闭跨场记忆');self.begin();self.finish();self.send('下一场')
  self.assertEqual(view(self.state())['profile'],{})
 def test_strategy_respects_intent_and_position(self):
  from datetime import datetime,timezone
  self.onboarding();self.begin();self.send('这杆怎么打');self.send('稳一点');self.send('还在走过去')
  self.assertNotIn('last_consultation',self.state()['journey'])
  self.send('就在球旁')
  now=datetime.now(timezone.utc).isoformat();self.n+=1
  self.e.command('j',str(self.n),'journey_event',dict(protocol_version=5,type='gps',event_id='gps',observed_at=now,data={'latitude':31,'longitude':121.001,'accuracy_m':2}))
  self.send('球道');self.send('7铁打向果岭中央');self.send('按这个打')
  c=self.state()['journey']['last_consultation'];self.assertEqual(c['player_intent'],'稳一点');self.assertEqual(c['decision'],'7铁打向果岭中央')
  self.assertFalse(any(k.startswith('shots.') for k in self.state()['facts']))
 def test_failed_consent_not_silently_assumed(self):
  for t in ['可以记住','阿明','码']:self.send(t)
  self.send('我不知道你什么意思');self.assertEqual(view(self.state())['stage'],'proactive')
 def test_gps_does_not_stack_question_during_strategy(self):
  from datetime import datetime,timezone
  self.onboarding();self.begin();self.send('这杆怎么打');base=1793923200
  for dt,lon in [(0,121.003),(4,121.0033),(8,121.0036),(16,121.0036),(24,121.0036)]:
   self.n+=1
   r=self.e.command('j',str(self.n),'journey_event',dict(protocol_version=5,type='gps',event_id='g'+str(self.n),observed_at=datetime.fromtimestamp(base+dt,timezone.utc).isoformat(),data={'latitude':31,'longitude':lon,'accuracy_m':2}),now=base+dt)
  self.assertEqual(self.state()['facts']['context.active_hole']['value'],2)
  self.assertEqual(r['text'],'');self.assertFalse(any(q['status']=='pending' for q in self.state()['questions'].values()))
  self.assertEqual(self.state()['journey']['consultation']['phase'],'intent')
if __name__=='__main__':unittest.main()
