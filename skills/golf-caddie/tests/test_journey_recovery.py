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
  self.assertEqual(view(self.e.state('j'))['stage'],'ready')
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
  self.assertEqual([r['stroke_number'] for r in rows if r.get('inferred_from_score') and r.get('source')!='score_placeholder'],[2,3])
  self.assertEqual([r['stroke_number'] for r in rows if r.get('source')=='score_placeholder'],[1])
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


class ImmediateLandingDistanceTests(unittest.TestCase):
 protocol_version=91
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 gps=JourneyRecoveryTests.gps
 onboard=JourneyRecoveryTests.onboard

 def test_map_landing_appears_before_score(self):
  self.onboard()
  for text in ('1','轻松打球','开始球局'):self.send(text)
  self.gps('tee');self.gps('fairway')
  state=self.e.state('j')
  row=view(state)['round_records']['clubs'][0]
  self.assertEqual(row['stroke_number'],1)
  self.assertGreater(row['total_horizontal_m'],0)
  self.assertIn('上一杆水平总距离',self.send('打了多少')['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class ScoreWordingTests(ImmediateLandingDistanceTests):
 protocol_version=92

 def test_three_strokes_two_putts_confirmation_text(self):
  self.onboard()
  for text in ('1','轻松打球','开始球局'):self.send(text)
  self.gps('tee');self.gps('fairway')
  points=preview(1)['positions'];a,b=points['fairway'],points['green']
  mid=dict(a,latitude=(a['latitude']+b['latitude'])/2,longitude=(a['longitude']+b['longitude'])/2,simulation_source='map_click')
  self.send(type='gps',data=mid)
  self.gps('green')
  self.send(type='simulation_hole',hole=2)
  self.assertEqual(self.send('5杆')['text'],'第1洞5杆（已含罚杆），3杆上果岭，2推。确认记录吗？')
  self.assertTrue(self.send('确认')['saved'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class SimulatedParThreeShotTests(unittest.TestCase):
 protocol_version=93
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 onboard=JourneyRecoveryTests.onboard

 def test_confirm_club_land_on_green_return_to_tee_and_score(self):
  self.onboard()
  for text in ('2','轻松打球','开始球局'):self.send(text)
  positions=preview(2)['positions']
  def move(kind):
   return self.send(type='gps',data=dict(positions[kind],simulation_source='map_click'))
  move('tee')
  self.send('怎么打')
  advice=self.send('后旗偏右')
  self.assertEqual(advice['estimated_iron_option']['club'],'6号铁')
  self.assertIn('6号铁',self.send('可以')['text'])
  self.assertEqual(view(self.e.state('j'))['round_records']['clubs'],[])
  self.assertTrue(move('green')['simulated_shot_recorded'])
  self.assertFalse(move('tee').get('simulated_shot_recorded'))
  self.assertIn('上一杆水平总距离',self.send('上一杆打了多少')['text'])
  rows=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual([(r['hole'],r['stroke_number'],r['club']) for r in rows],[(2,1,'6号铁')])
  self.send(type='simulation_hole',hole=3)
  self.assertIn('第2洞3杆（已含罚杆），1杆上果岭，2推。确认记录吗？',self.send('3杆')['text'])
  self.assertTrue(self.send('确认')['saved'])
  after=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual([r for r in after if r['club']!='推杆'],rows)
  self.assertEqual([2,3],[r['stroke_number'] for r in after if r['club']=='推杆'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class MappedTeeFallbackTests(unittest.TestCase):
 protocol_version=94
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send

 def test_carry_finds_fairway_beside_right_bunker(self):
  for text in ('可以记住','球友','好','好','200','不知道','偏右',
               '东莞凤凰山（A+B蓝台演示）','蓝台','6','轻松打球','开始球局'):
   self.send(text)
  self.send(type='gps',data=dict(preview(6)['positions']['tee'],simulation_source='map_click'))
  advice=self.send('怎么打')
  self.assertIn('近处右侧约205码的沙坑左边',advice['text'])
  self.assertIn('195–205码',advice['text'])
  self.assertIn('按这个打',advice['choices'])
  self.assertIn('一号木',self.send('按这个打')['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_water_across_aim_line_blocks_mapped_fallback(self):
  from tee_geometry import tee_targets

  def surface(kind, x1, x2, y1, y2):
   ring=[[x/111195,y/111195] for x,y in ((x1,y1),(x2,y1),(x2,y2),(x1,y2),(x1,y1))]
   return dict(id=kind,surface=kind,verified=True,source='test',geometry=dict(type='Polygon',coordinates=[ring]))

  fairway=surface('fairway',-30,30,150,220)
  water=surface('water',-30,30,90,110)
  hole=dict(number=1,objects=[dict(kind='green_center',latitude=.003,longitude=0)],
            surface_zones=[fairway])
  origin=dict(latitude=0,longitude=0,accuracy_m=2)
  state=dict(facts={'context.device_position':dict(valid=True,status='confirmed',value=origin)},
             evidence={'course':dict(data=dict(holes=[hole]))})
  analysis=dict(course_evidence='course',hole=1)
  clubs=[('driver',dict(label='一号木',carry_yards=200))]
  self.assertTrue(tee_targets(state,analysis,clubs))
  hole['surface_zones'].append(water)
  self.assertEqual(tee_targets(state,analysis,clubs),[])
  self.assertTrue(tee_targets(state,analysis,clubs,allow_crossing=True))
  from tee_strategy import suggest
  analysis.update(par=4,clubs=dict(clubs),candidates=[],position_version=1)
  offer=suggest(state,analysis,mapped_fallback=True,carry_crossing=True)
  self.assertTrue(offer['options'])
  self.assertIn('飞越',offer['text'])
  hole['surface_zones'][-1]=surface('water',-45,45,90,230)
  self.assertEqual(tee_targets(state,analysis,clubs,allow_crossing=True),[])


class ParFiveTeePlanTests(unittest.TestCase):
 protocol_version=95
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 onboard=JourneyRecoveryTests.onboard

 def test_hole_three_plans_through_the_third_shot(self):
  self.onboard()
  for text in ('3','轻松打球','开始球局'):self.send(text)
  self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
  advice=self.send('这杆怎么打')['text']
  self.assertIn('一号木瞄右侧约290码的沙坑左边',advice)
  self.assertIn('远沿约185码',advice)
  self.assertIn('目标Carry约145码',advice)
  self.assertIn('第三杆到果岭参考点约90码',advice)
  self.assertIn('一号木',self.send('按这个打')['text'])
  self.assertIn('Carry',self.send('4号铁木杆')['text'])
  alternative=self.send('4号铁木杆190码')['text']
  self.assertIn('4号铁木杆',alternative)
  self.assertIn('第三杆到果岭参考点约115码',alternative)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class ParFiveTwoOnTests(ParFiveTeePlanTests):
 protocol_version=97

 def test_card_length_budget_and_plan_choice(self):
  self.onboard()
  for word in ('3','轻松打球','开始球局'):self.send(word)
  self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
  advice=self.send('这杆怎么打')
  self.assertIn('合计最多420码', advice['text'])
  self.assertIn('公布长度490码', advice['text'])
  self.assertIn('第三杆到果岭参考点约90码', advice['text'])
  self.send('3号木')
  self.send('3号木235码')
  self.send('自己打')
  choices=self.send('这杆怎么打')
  self.assertIn('两上方案',choices['text'])
  self.assertIn('第二杆可考虑3号木',choices['text'])
  self.assertIn('三上方案',choices['text'])
  self.assertEqual(choices['choices'],['两上方案','三上方案','自己打'])
  self.assertIn('你想走两上还是三上',self.send('按这个打')['text'])
  self.assertIn('走两上方案',self.send('两上方案')['text'])
  decision=self.e.state('j')['journey']['last_consultation']['decision']
  self.assertEqual(decision['approach']['club'],'3号木')
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class ParFiveMissingFairwayCarryTests(unittest.TestCase):
 protocol_version=98
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 onboard=JourneyRecoveryTests.onboard

 def start_third(self):
  self.onboard()
  for word in ('3','轻松打球','开始球局'):self.send(word)
  self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
  return self.send('这杆怎么打')

 def test_missing_long_club_asks_and_recomputes_both_routes(self):
  first=self.start_third()
  self.assertIn('一号木和7号铁',first['text'])
  self.assertIn('Carry合计420码',first['text'])
  self.assertIn('球道上能稳定用的最长一支杆',first['text'])
  self.assertIn('第三杆到果岭参考点约90码',first['text'])
  self.assertNotIn('低于球洞公布长度',first['text'])
  self.assertIn('在球道上的Carry',self.send('3号木')['text'])
  choices=self.send('235码')
  self.assertEqual(choices['choices'],['两上方案','三上方案','自己打'])
  self.assertIn('第二杆可考虑3号木',choices['text'])
  self.assertIn('走两上方案',self.send('两上方案')['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_skip_keeps_three_on_available(self):
  self.start_third()
  advice=self.send('跳过')
  self.assertIn('第三杆到果岭参考点约90码',advice['text'])
  self.assertIn('按这个打',advice['choices'])
  self.assertIn('一号木',self.send('按这个打')['text'])


class TeeBriefOrderingTests(ParFiveMissingFairwayCarryTests):
 protocol_version=100

 def test_brief_precedes_strategy_and_does_not_reappear_after_dwell(self):
  self.onboard()
  for word in ('1','轻松打球','开始球局'):self.send(word)
  self.send(type='simulation_hole',hole=3)
  advice=self.send('这杆怎么打')['text']
  self.assertTrue(advice.startswith('第3洞，5杆洞。'))
  self.assertLess(advice.index('直线约'),advice.index('候选落区'))
  self.assertLess(advice.index('候选落区'),advice.index('球道上能稳定用的最长一支杆'))
  gps=dict(preview(3)['positions']['tee'],simulation_source='map_click')
  for _ in range(4):
   followup=self.send(type='gps',data=gps)
   self.assertNotIn('第3洞，5杆洞',followup['text'])
  state=self.e.state('j')
  self.assertGreaterEqual(state['journey']['tee_tracking']['fixes'],3)
  self.assertEqual(state,self.e.replay('j'))


class ParFiveBagQuestionsTests(unittest.TestCase):
 protocol_version=101
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 onboard=JourneyRecoveryTests.onboard

 def test_collects_bag_before_suggesting_a_plan(self):
  self.onboard()
  for word in ('1','轻松打球','开始球局'):self.send(word)
  self.send(type='simulation_hole',hole=3)
  first=self.send('这杆怎么打')['text']
  self.assertIn('3号木在球道上',first)
  self.assertNotIn('候选落区',first)
  self.assertIn('5号木在球道上',self.send('3号木235码')['text'])
  self.assertIn('铁木杆在球道上',self.send('5号木220码')['text'])
  self.assertIn('你有3号铁吗',self.send('4号铁木杆200码')['text'])
  self.assertIn('你有4号铁吗',self.send('没有')['text'])
  self.assertEqual(self.send('4铁190码')['choices'],['两上方案','三上方案','自己打'])
  self.send('自己打')
  self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
  self.assertIn('两上方案',self.send('这杆怎么打')['text'])
  profile=self.e.state('j')['journey']['profile']
  self.assertEqual(profile['five_wood']['value']['distance'],220)
  self.assertEqual(profile['iron4']['value']['distance'],190)
  self.assertIn('iron3',profile['absent_fairway_clubs']['value'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class ParFiveRollInTests(ParFiveBagQuestionsTests):
 protocol_version=102

 def test_ten_yard_card_gap_keeps_mapped_roll_in_option(self):
  self.onboard()
  for word in ('3','轻松打球','开始球局'):self.send(word)
  self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
  for word in ('这杆怎么打','3号木220码','没有','没有','没有'):
   self.send(word)
  advice=self.send('没有')
  self.assertEqual(advice['choices'],['两上方案','三上方案','自己打'])
  self.assertIn('目标Carry约220码',advice['text'])
  self.assertIn('落地后再滚',advice['text'])
  self.assertIn('走两上方案',self.send('两上方案')['text'])
  decision=self.e.state('j')['journey']['last_consultation']['decision']
  self.assertLessEqual(decision['approach']['roll_yards'],10)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_ground_hazard_blocks_roll_in(self):
  from tee_geometry import tee_targets

  def surface(kind,x1,x2,y1,y2):
   ring=[[x/111195,y/111195] for x,y in ((x1,y1),(x2,y1),(x2,y2),(x1,y2),(x1,y1))]
   return dict(id=kind,surface=kind,verified=True,source='test',geometry=dict(type='Polygon',coordinates=[ring]))

  hole=dict(number=1,objects=[dict(kind='green_center',latitude=220/111195,longitude=0)],
            surface_zones=[surface('fairway',-35,35,120,208),surface('green',-35,35,206,244)])
  state=dict(evidence={'course':dict(data=dict(holes=[hole]))})
  analysis=dict(course_evidence='course',hole=1)
  clubs=[('five_wood',dict(label='5号木',carry_yards=220))]
  origin=dict(latitude=0,longitude=0,accuracy_m=2)
  kwargs=dict(origin=origin,allow_crossing=True,surface='green',roll_in=True)
  self.assertTrue(tee_targets(state,analysis,clubs,**kwargs))
  hole['surface_zones'].append(surface('bunker',-35,35,203,205))
  self.assertEqual(tee_targets(state,analysis,clubs,**kwargs),[])


class SharedTeeClubConfirmationTests(unittest.TestCase):
 protocol_version=103
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 onboard=JourneyRecoveryTests.onboard

 def test_confirms_shared_tee_club_without_repeating_or_selecting_route(self):
  self.onboard()
  for word in ('3','轻松打球','开始球局'):self.send(word)
  self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
  for word in ('这杆怎么打','3号木220码','没有','没有','没有','没有'):self.send(word)
  reply=self.send('一号木')
  self.assertIn('好，开球用一号木',reply['text'])
  self.assertIn('等开球落定再决定',reply['text'])
  self.assertNotIn('第二杆可考虑',reply['text'])
  state=self.e.state('j')
  self.assertEqual(state['journey']['player_decisions'][-1]['club'],'一号木')
  self.assertNotIn('decision',state['journey']['consultation'])
  self.assertEqual(view(state)['round_records']['clubs'],[])
  self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
  self.send('一号木')
  self.assertEqual(len(self.e.state('j')['journey']['player_decisions']),1)
  self.assertIn('走两上方案',self.send('两上方案')['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class ParFiveApproachRiskTests(unittest.TestCase):
 protocol_version=104
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 onboard=JourneyRecoveryTests.onboard

 def test_narrow_third_hole_entrance_offers_wider_layup(self):
  from tee_geometry import tee_targets
  from tee_strategy import analyze
  self.onboard()
  for word in ('3','轻松打球','开始球局'):self.send(word)
  self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
  state=self.e.state('j')
  analysis=analyze(state,self.clock.timestamp())
  tee=tee_targets(state,analysis,[('driver',analysis['clubs']['driver'])],allow_crossing=True)[0]
  for word in ('这杆怎么打','3号木220码','没有','没有','没有','没有','一号木'):self.send(word)
  self.send(type='gps',data=dict(tee['aim_point'],accuracy_m=2,simulation_hole=3,simulation_source='map_click'))
  self.assertIn('旗在果岭',self.send('这杆怎么打')['text'])
  advice=self.send('左前')['text']
  for phrase in ('两上候选','三上候选','果岭入口','右侧水障碍','右侧沙坑','球道落区','预计第三杆','优先考虑三上','现场白桩'):
   self.assertIn(phrase,advice)
  for word in ('好两上','好，两上'):
   self.assertIn('采用刚才的两上方案',self.send(word)['text'])
  self.assertIn('52度杆',self.send('52')['text'])
  self.assertEqual('52度杆',self.e.state('j')['journey']['player_decisions'][-1]['club'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class BallOutcomeTests(unittest.TestCase):
 protocol_version=105
 setUp=JourneyRecoveryTests.setUp
 tearDown=JourneyRecoveryTests.tearDown
 send=JourneyRecoveryTests.send
 onboard=JourneyRecoveryTests.onboard

 def start(self):
  self.onboard()
  for word in ('3','轻松打球','开始球局'):self.send(word)
  return self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))

 def point(self, lat, lon):
  return self.send(type='gps',data=dict(latitude=lat,longitude=lon,accuracy_m=2,simulation_hole=3,simulation_source='map_click'))

 def test_white_stakes_interrupt_strategy_and_return_is_not_a_shot(self):
  self.start()
  for word in ('这杆怎么打','3号木220码','没有','没有','没有','没有'):self.send(word)
  confirmation=self.send('1号木')['text']
  self.assertIn('开球用一号木',confirmation)
  for phrase in ('暂定球','出界','遗失','下水'):
   self.assertNotIn(phrase,confirmation)
  landing=self.point(22.70111,114.15085)
  self.assertTrue(landing.get('simulated_shot_recorded'),landing)
  self.assertIn('模拟落点提示可能出界',landing['text'])
  for reply in ('这杆怎么打','长草','左前'):
   self.assertIn('原球确认在界内',self.send(reply)['text'])
  self.assertIn('罚一杆',self.send('确认出界')['text'])
  self.send('已回原位')
  tee=preview(3)['positions']['tee']
  self.assertFalse(self.point(tee['latitude'],tee['longitude']).get('simulated_shot_recorded'))
  self.assertTrue(self.point(22.70111,114.15085).get('simulated_shot_recorded'))
  records=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual([r['stroke_number'] for r in records],[1,3])
  self.assertEqual([r['club'] for r in records],['一号木','一号木'])
  score=self.send('这洞6杆，2推')
  self.assertIn('罚杆1',score['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_provisional_then_found_ob_or_water(self):
  self.start()
  self.assertIn('击球前向同组',self.send('没看到球，可能OB，先打暂定球')['text'])
  self.assertIn('先不计入',self.send('暂定球已打')['text'])
  self.assertIn('暂定球作废',self.send('球在界内')['text'])
  self.assertIn('通常先核实',self.send('好像出界')['text'])
  self.send('暂定球已打')
  self.assertIn('成为使用中球',self.send('三分钟没找到')['text'])
  self.point(22.70111,114.15060)
  self.assertIn('先核实',self.send('没看到，可能下水')['text'])
  self.assertIn('通常不打暂定球',self.send('能不能打暂定球')['text'])
  water=self.send('确认下水')['text']
  for phrase in ('最后越过罚杆区边界','红桩','当地规则指定'):
   self.assertIn(phrase,water)
  self.assertIn('一杆罚杆',self.send('已在合法位置抛球')['text'])
  self.assertFalse(self.point(22.70130,114.15062).get('simulated_shot_recorded'))
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class ShotAudioFlowTests(BallOutcomeTests):
 protocol_version=106

 def test_arm_wait_prompt_and_disable(self):
  self.start()
  self.assertEqual('',self.send('音频检测到疑似击球')['text'])
  for word in ('这杆怎么打','3号木220码','没有','没有','没有','没有'):self.send(word)
  self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
  self.send('1号木')
  self.assertEqual('armed',self.e.state('j')['journey']['shot_audio']['phase'])
  self.send('关闭击球声音识别')
  self.send('开启击球声音识别')
  self.assertEqual('armed',self.e.state('j')['journey']['shot_audio']['phase'])
  self.assertEqual('',self.send('音频检测到疑似击球')['text'])
  self.assertEqual('',self.send('击球声音等待结束')['text'])
  self.assertIn('看到球落哪儿',self.send('击球声音等待结束')['text'])
  self.assertFalse(self.e.state('j')['journey']['shot_audio']['enabled'])
  self.point(22.70130,114.15062)
  self.assertIn('球在球道中间',self.send('球道中间')['text'])
  self.assertEqual('球道',self.e.state('j')['journey']['reported_landing']['lie'])
  self.assertEqual('',self.send('音频检测到疑似击球')['text'])
  self.assertEqual('',self.send('击球声音等待结束')['text'])
  self.send('关闭击球声音识别')
  self.assertFalse(self.e.state('j')['journey']['shot_audio']['enabled'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class SimulationRestartOutcomeTests(BallOutcomeTests):
 def test_restart_same_hole_clears_outcome_and_keeps_archived_ordinals(self):
  self.start()
  self.point(22.70111,114.15085)
  self.send('确认出界')
  self.send(type='simulation_hole',hole=3)
  reply=self.send('这杆怎么打')['text']
  self.assertNotIn('先确认上一杆',reply)
  records=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual([],records)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class ProvisionalRecordingTests(BallOutcomeTests):
 def test_uncertain_ob_and_provisional_strokes(self):
  self.start()
  for word in ('应该是OB了','应该是出界了'):
   self.assertIn('可以在上一杆位置打暂定球',self.send(word)['text'])
  self.send('暂定球已打')
  self.send('确认出界')
  self.point(22.70130,114.15062)
  rows=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual([1,3],[r['stroke_number'] for r in rows])
  self.assertIsNotNone(rows[-1]['total_horizontal_m'])
  self.send('这杆怎么打')
  self.send('左前')
  self.send('48')
  self.point(22.70200,114.1498)
  rows=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual([1,3,4],[r['stroke_number'] for r in rows])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))


class RepeatedAttemptPenaltyTests(BallOutcomeTests):
 def test_only_current_attempt_penalty_contributes(self):
  from ball_outcome import reported_penalties
  self.start()
  for _ in range(7):
   self.send('确认出界')
   self.send(type='simulation_hole',hole=3)
  self.send('确认出界')
  self.assertEqual(1,reported_penalties(self.e.state('j'),3))
  self.send(type='simulation_hole',hole=4)
  self.send('第3洞6杆')
  reply=self.send('两推')
  self.assertNotIn('超过',reply['text'])
  draft=self.e.state('j')['session']['draft']
  self.assertEqual((6,2,1),(draft['total'],draft['putts'],draft['penalties']))
  putts=[r for r in view(self.e.state('j'))['round_records']['clubs'] if r['club']=='推杆']
  self.assertEqual([5,6],[r['stroke_number'] for r in putts])
  self.assertTrue(all(r.get('total_horizontal_m') is None for r in putts))
  self.assertEqual(self.e.state('j'),self.e.replay('j'))
