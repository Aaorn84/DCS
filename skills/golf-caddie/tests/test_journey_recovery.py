import sys,tempfile,unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from phoenix_demo import preview
from journey import view

class JourneyRecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.db=self.tmp.name+'/round.sqlite'
  self.e=Engine(self.db,'recovery');self.e.create('j')
  self.clock=datetime(2026,11,11,tzinfo=timezone.utc);self.n=0
 def tearDown(self):
  self.e.close();self.tmp.cleanup()
 protocol_version=51
 def send(self,text=None,**fields):
  self.n+=1;self.clock+=timedelta(seconds=8)
  if text is not None:fields.update(type='message',text=text)
  p=dict(protocol_version=self.protocol_version,event_id='r'+str(self.n),observed_at=self.clock.isoformat(),**fields)
  return self.e.command('j',str(self.n),'journey_event',p,now=self.clock.timestamp())
 def gps(self,kind):
  return self.send(type='gps',data=dict(preview(1)['positions'][kind],simulation_source='map_click'))
 def onboard(self):
  for t in ('可以记住','球友','好','好','260','160','偏右','东莞凤凰山（A+B蓝台演示）','蓝台'):self.send(t)
 def at_fairway(self):
  self.onboard()
  for t in ('1','轻松打球','开始球局'):self.send(t)
  self.gps('tee');self.gps('fairway')
  self.assertIn('刚才那杆用的什么杆',self.send('还有多少')['text'])
 def test_simulated_return_restarts_pair_and_keeps_confirmed_record(self):
  self.at_fairway();self.send('1号木');self.send('上一杆打了多少');self.send('是的')
  before=self.e.state('j')['journey']['confirmed_shot_distances']
  self.send(type='simulation_hole',hole=2);self.send('5');self.send('2');self.send('确认')
  self.send(type='simulation_hole',hole=1)
  self.assertNotIn('刚才那杆用的',self.send('还有多少')['text'])
  self.assertNotIn('只打了一杆',self.send('上一杆打了多少')['text'])
  self.gps('fairway')
  self.assertIn('刚才那杆用的',self.send('还有多少')['text'])
  s=self.e.state('j')
  self.assertEqual(s['journey']['confirmed_shot_distances'],before)
  self.assertEqual(view(s)['score_summary']['confirmed_subtotal'],5)
  self.assertEqual(s,self.e.replay('j'))
 def test_colloquial_previous_distance_interrupts_club_question(self):
  from decision_queries import previous_distance
  self.at_fairway()
  for text in ('刚刚打了多少','刚刚开了多远？','上一个打了多少？'):
   self.assertIn('中间只打了一杆',self.send(text)['text'])
   self.assertFalse(self.e.state('j')['journey'].get('confirmed_shot_distances'))
  self.assertIn('包含滚动',self.send('是的')['text'])
  row=self.e.state('j')['journey']['confirmed_shot_distances'][-1]
  self.assertFalse(row['carry'])
  self.assertIsNone(row['club'])
  for text in ('还有多少','刚刚打了五杆','刚刚用了什么杆','下一杆打多少'):
   self.assertFalse(previous_distance(text),text)

 def test_login_and_explicit_resume_keep_valid_question(self):
  self.at_fairway();self.e.close();self.e=Engine(self.db,'recovery')
  for event in (dict(type='resume'),dict(type='message',text='继续刚才的问题')):
   self.assertEqual(self.send(**event)['text'],'刚才那杆用的什么杆？')
  self.assertIn('1号木',self.send('1号木')['text'])
  self.assertNotIn('pending_previous_club',self.e.state('j')['journey'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_resumed_score_prompt_needs_only_one_confirmation(self):
  self.at_fairway()
  self.send(type='simulation_hole',hole=2)
  self.send('五');self.send('两推')
  self.assertIn('确认记录吗',self.send('继续刚才的问题')['text'])
  self.assertEqual(view(self.e.state('j'))['score_summary']['confirmed_holes'],0)
  self.assertTrue(self.send('确认记录')['saved'])
  self.assertEqual(view(self.e.state('j'))['score_summary']['confirmed_subtotal'],5)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_expired_position_does_not_resume(self):
  self.at_fairway();self.clock+=timedelta(seconds=90)
  self.assertNotIn('刚才那杆用的',self.send(type='resume')['text'])
  self.assertNotIn('pending_previous_club',self.e.state('j')['journey'])
 def test_new_position_closes_old_question(self):
  self.at_fairway();self.gps('green')
  self.assertNotIn('pending_previous_club',self.e.state('j')['journey'])
  self.assertNotIn('刚才那杆用的',self.send('继续刚才的问题')['text'])
 def test_preconfirmed_tee_opening_is_ready_for_distance(self):
  self.onboard()
  for _ in range(4):self.gps('tee')
  self.assertEqual(view(self.e.state('j'))['stage'],'goal')
  self.send('轻松打球');out=self.send('开始球局')
  self.assertIn('定位已确认',out['text']);self.assertNotIn('尚未提交',out['text'])
  self.assertIn('果岭',self.send('还有多少')['text'])
 def test_opening_without_fix_still_prompts_for_location(self):
  self.onboard();self.send('1');self.send('轻松打球')
  self.assertIn('尚未提交',self.send('开始球局')['text'])


class ScoreConfirmationAfterBriefTests(unittest.TestCase):
 protocol_version=69
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 gps=JourneyRecoveryTests.gps
 onboard=JourneyRecoveryTests.onboard
 at_fairway=JourneyRecoveryTests.at_fairway

 def test_one_confirmation_after_tee_brief_request(self):
  self.at_fairway()
  self.send(type='simulation_hole',hole=2)
  self.assertIn('确认记录吗',self.send('5杆，2推')['text'])
  self.assertNotIn('果岭参考点',self.send('到发球台了')['text'])
  self.assertTrue(self.send('确认')['saved'])
  self.assertEqual(view(self.e.state('j'))['score_summary']['confirmed_subtotal'],5)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class ScoreAfterGreenTests(ScoreConfirmationAfterBriefTests):
 protocol_version=72

 def test_previous_green_allows_unknown_putts(self):
  self.at_fairway()
  self.gps('green')
  self.send(type='simulation_hole',hole=2)
  out=self.send('3杆')
  self.assertIn('确认记录吗',out['text'])
  self.assertTrue(self.send('确认')['saved'])
  from round_state import fact_value
  state=self.e.state('j')
  self.assertEqual(fact_value(state,'holes.1.total'),3)
  self.assertIsNone(fact_value(state,'holes.1.putts'))
  self.assertEqual(state,self.e.replay('j'))


class TerseDistanceTests(unittest.TestCase):
 protocol_version=73
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 gps=JourneyRecoveryTests.gps
 onboard=JourneyRecoveryTests.onboard
 at_fairway=JourneyRecoveryTests.at_fairway

 def test_past_tense_queries_previous_shot(self):
  self.at_fairway()
  self.assertIn('中间只打了一杆',self.send('打了多少')['text'])
  self.assertIn('包含滚动',self.send('是的')['text'])
  self.assertIn('上一杆水平总距离',self.send('打了多少？')['text'])
  self.assertIn('果岭',self.send('打多少')['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class InferredPuttsTests(unittest.TestCase):
 protocol_version=74
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 gps=JourneyRecoveryTests.gps
 onboard=JourneyRecoveryTests.onboard

 def test_confirmed_tee_to_green_proposes_two_putts(self):
  self.onboard()
  for text in ('1','轻松打球','开始球局'):self.send(text)
  self.gps('tee');self.gps('green')
  self.assertIn('只打了一杆',self.send('打了多少')['text'])
  self.send('是的')
  self.send(type='simulation_hole',hole=2)
  self.assertIn('推算2推',self.send('3杆')['text'])
  self.assertTrue(self.send('确认')['saved'])
  from round_state import fact_value
  self.assertEqual(fact_value(self.e.state('j'),'holes.1.putts'),2)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class ConciseScoreConfirmationTests(ScoreConfirmationAfterBriefTests):
 protocol_version=76

 def test_confirmation_omits_unreported_penalties(self):
  self.at_fairway()
  self.send(type='simulation_hole',hole=2)
  self.assertEqual(self.send('5杆，2推')['text'],'第1洞5杆，2推。确认记录吗？')
  self.assertTrue(self.send('确认')['saved'])
  from round_state import fact_value
  self.assertIsNone(fact_value(self.e.state('j'),'holes.1.penalties'))


class CompactScoreTests(ScoreConfirmationAfterBriefTests):
 protocol_version=78

 def test_total_and_putts_without_punctuation(self):
  self.at_fairway()
  self.send(type='simulation_hole',hole=2)
  self.assertEqual(self.send('5杆2推')['text'],'第1洞5杆，2推。确认记录吗？')
  self.assertTrue(self.send('确认')['saved'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class MultiStrokePuttsTests(InferredPuttsTests):
 protocol_version=79

 def test_three_confirmed_strokes_propose_two_putts(self):
  from phoenix_demo import preview
  self.onboard()
  for text in ('1','轻松打球','开始球局'):self.send(text)
  self.gps('tee');self.gps('fairway')
  self.assertIn('只打了一杆',self.send('打了多少')['text']);self.send('是的')
  points=preview(1)['positions'];a,b=points['fairway'],points['green']
  mid=dict(a,latitude=(a['latitude']+b['latitude'])/2,longitude=(a['longitude']+b['longitude'])/2,simulation_source='map_click')
  self.send(type='gps',data=mid)
  self.assertIn('只打了一杆',self.send('打了多少')['text']);self.send('是的')
  self.gps('green')
  self.assertIn('只打了一杆',self.send('打了多少')['text']);self.send('是的')
  self.send(type='simulation_hole',hole=2)
  self.assertIn('按3杆上果岭推算2推',self.send('5杆')['text'])
  self.assertTrue(self.send('确认')['saved'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class DefaultPenaltyTests(ScoreConfirmationAfterBriefTests):
 protocol_version=80

 def test_unreported_penalties_saved_as_zero(self):
  self.at_fairway()
  self.send(type='simulation_hole',hole=2)
  self.assertEqual(self.send('6杆2推')['text'],'第1洞6杆，2推。确认记录吗？')
  self.assertTrue(self.send('确认')['saved'])
  from round_state import fact_value
  self.assertEqual(fact_value(self.e.state('j'),'holes.1.penalties'),0)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class SimulatedLandingPuttsTests(InferredPuttsTests):
 protocol_version=82

 def test_unconfirmed_simulated_landings_reconcile_at_score(self):
  self.onboard()
  for text in ('1','轻松打球','开始球局'):self.send(text)
  self.gps('tee');self.gps('fairway')
  self.assertIn('只打了一杆',self.send('打了多少')['text']);self.send('是的')
  points=preview(1)['positions'];a,b=points['fairway'],points['green']
  mid=dict(a,latitude=(a['latitude']+b['latitude'])/2,longitude=(a['longitude']+b['longitude'])/2,simulation_source='map_click')
  self.send(type='gps',data=mid)
  self.gps('green')
  self.send(type='simulation_hole',hole=2)
  self.assertIn('按3杆上果岭推算2推',self.send('5杆')['text'])
  self.assertTrue(self.send('确认')['saved'])
  rows=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual([r['stroke_number'] for r in rows if r.get('inferred_from_score')],[2,3])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class AuditFixTests(InferredPuttsTests):
 protocol_version=87

 def test_correction_replaces_location_and_retry_survives_protocol_change(self):
  self.onboard()
  for message in ('1','轻松打球','开始球局'):self.send(message)
  self.gps('tee');self.gps('fairway')
  point=dict(preview(1)['positions']['fairway'],simulation_source='map_click',
             simulation_position_action='correct')
  point['latitude']+=.0001
  self.send(type='gps',data=point)
  rows=self.e.state('j')['journey']['shot_location_candidates']
  self.assertEqual(len(rows),2)
  self.assertEqual(rows[-1]['point']['latitude'],point['latitude'])
  event=dict(protocol_version=87,event_id='retry-v87',type='message',text='谢谢',
             observed_at=self.clock.isoformat())
  first=self.e.command('j','stable-retry','journey_event',event,now=self.clock.timestamp())
  self.assertEqual(first,self.e.command('j','stable-retry','journey_event',
                                       dict(event,protocol_version=88),server_protocol=True))
  from round_state import Conflict
  with self.assertRaises(Conflict):
   self.e.command('j','stable-retry','journey_event',dict(event,protocol_version=88,text='安静'),
                  server_protocol=True)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_score_edit_preserves_reported_penalty(self):
  self.onboard()
  for message in ('1','轻松打球','开始球局','5杆2推1罚','确认','6杆2推','确认'):self.send(message)
  from round_state import fact_value
  self.assertEqual(fact_value(self.e.state('j'),'holes.1.penalties'),1)


class LandingCorrectionTests(InferredPuttsTests):
 protocol_version=88

 def test_reject_empty_correction_then_offer_reconfirmation(self):
  from round_state import fact_value
  self.onboard()
  for message in ('1','轻松打球','开始球局'):self.send(message)
  self.gps('tee')
  old=fact_value(self.e.state('j'),'context.device_position')
  point=dict(preview(1)['positions']['fairway'],simulation_source='map_click',simulation_position_action='correct')
  self.assertEqual(self.send(type='gps',data=point)['reason'],'no_correctable_landing')
  self.assertEqual(fact_value(self.e.state('j'),'context.device_position'),old)
  self.gps('fairway');self.send('打了多少');self.send('是的')
  point['latitude']+=.0001
  out=self.send(type='gps',data=point)
  self.assertIn('落点已更正',out['text'])
  self.assertIn('只打了一杆',out['text'])
  self.assertIn('水平总距离',self.send('是的')['text'])
  rows=self.e.state('j')['journey']['confirmed_shot_distances']
  self.assertEqual([row['valid'] for row in rows],[False,True])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))
