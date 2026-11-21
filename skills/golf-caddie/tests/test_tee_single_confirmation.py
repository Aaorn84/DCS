import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_journey_recovery as support
from phoenix_demo import preview
from journey import view

class SingleConfirmationTests(unittest.TestCase):
 protocol_version=111
 setUp=support.JourneyRecoveryTests.setUp
 tearDown=support.JourneyRecoveryTests.tearDown
 send=support.JourneyRecoveryTests.send
 onboard=support.JourneyRecoveryTests.onboard
 def test_agree_with_driver_keeps_mapped_target_and_commits_once(self):
  self.onboard()
  for text in ('1','轻松打球','开始球局'):self.send(text)
  self.send(type='gps',data=dict(preview(1)['positions']['tee'],simulation_source='map_click'))
  self.send('这杆怎么打')
  state=self.e.state('j');old=state['journey']['consultation']['suggestion']
  self.assertIn('沙坑',old['target'])
  reply=self.send('好，1号木')['text']
  self.assertIn('好，开球用一号木',reply)
  state=self.e.state('j')
  self.assertNotIn('consultation',state['journey'])
  self.assertEqual(old['target'],state['journey']['last_consultation']['decision']['target'])
  self.assertEqual([],view(state)['round_records']['clubs'])
  self.assertEqual(state,self.e.replay('j'))

 def test_middle_sector_does_not_require_a_second_side_question(self):
  self.onboard()
  for text in ('4','轻松打球','开始球局'):self.send(text)
  self.send(type='gps',data=dict(preview(4)['positions']['tee'],simulation_source='map_click'))
  self.send('这杆怎么打')
  reply=self.send('中部')['text']
  self.assertNotIn('旗位偏左、居中，还是偏右',reply)
  self.assertIn('左右尚未确认',reply)
  row=next(iter(self.e.state('j')['journey']['pin_locations'].values()))
  self.assertEqual('unknown',row['side'])
  self.assertTrue(row['side_estimated'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_par_three_accepts_agreement_with_numbered_iron(self):
  self.onboard()
  for text in ('2','轻松打球','开始球局'):self.send(text)
  self.send(type='gps',data=dict(preview(2)['positions']['tee'],simulation_source='map_click'))
  self.send('这杆怎么打');self.send('中旗偏右')
  reply=self.send('好，6号铁')['text']
  self.assertIn('好，用6号铁',reply)
  state=self.e.state('j')
  self.assertEqual('6号铁',state['journey']['player_decisions'][-1]['club'])
  self.assertEqual([],view(state)['round_records']['clubs'])
  self.assertEqual(state,self.e.replay('j'))

 def test_driver_audio_and_position_update_keep_one_complete_stroke(self):
  self.onboard()
  for text in ('1','轻松打球','开始球局'):self.send(text)
  self.send(type='gps',data=dict(preview(1)['positions']['tee'],simulation_source='map_click'))
  self.send('这杆怎么打');self.send('好，1号木')
  self.send('开启击球声音识别');self.send('音频检测到疑似击球')
  self.send('击球声音等待结束');self.send('击球声音等待结束')
  self.send('球道中间')
  rows=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual(1,len(rows));self.assertEqual('一号木',rows[0]['club'])
  reply=self.send(type='gps',data=dict(preview(1)['positions']['fairway'],simulation_source='map_click',simulation_position_action='move'))
  self.assertNotIn('simulated_shot_recorded',reply)
  rows=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual(1,len(rows));self.assertEqual('一号木',rows[0]['club'])
  self.assertGreater(rows[0]['total_horizontal_m'],0)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_stroke_distance_rejects_old_landing_as_replay_origin(self):
  self.onboard()
  for text in ('3','轻松打球','开始球局'):self.send(text)
  tee=dict(preview(3)['positions']['tee'],simulation_source='map_click')
  fairway=dict(preview(3)['positions']['fairway'],simulation_source='map_click')
  self.send(type='gps',data=tee)
  # Explicit selection with an approach target is not needed for this GPS chain.
  self.send(type='gps',data=fairway)
  self.send('确认出界');self.send('已回原位')
  bad=self.send(type='gps',data={**fairway,'simulation_position_action':'move'})
  from ball_rules import current
  self.assertIsNotNone(current(self.e.state('j'))['pending'])
  self.assertIn('不符',bad['text'])
  self.send(type='gps',data={**tee,'simulation_position_action':'move'})
  self.assertIsNone(current(self.e.state('j'))['pending'])
  self.send(type='gps',data={**fairway,'simulation_position_action':'shot'})
  rows=view(self.e.state('j'))['round_records']['clubs']
  self.assertEqual([1,3],[r['stroke_number'] for r in rows])
  self.assertAlmostEqual(rows[0]['total_horizontal_m'],rows[1]['total_horizontal_m'],places=5)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_pin_survives_club_choice_and_next_landing(self):
  self.onboard()
  for text in ('2','轻松打球','开始球局'):self.send(text)
  self.send(type='gps',data=dict(preview(2)['positions']['tee'],simulation_source='map_click'))
  self.send('这杆怎么打');self.send('中旗偏右')
  import copy
  pins=copy.deepcopy(self.e.state('j')['journey']['pin_locations'])
  self.send('好，6号铁')
  self.assertEqual(pins,self.e.state('j')['journey']['pin_locations'])
  self.send('开启击球声音识别');self.send('音频检测到疑似击球')
  self.send('击球声音等待结束');self.send('击球声音等待结束');self.send('球道')
  self.send(type='gps',data=dict(preview(2)['positions']['fairway'],simulation_source='map_click',simulation_position_action='shot'))
  self.assertEqual(pins,self.e.state('j')['journey']['pin_locations'])
  reply=self.send('这杆怎么打')['text']
  self.assertNotIn('旗在果岭哪里',reply)
  self.assertEqual(pins,self.e.state('j')['journey']['pin_locations'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_reset_hole_can_prompt_score_again_once(self):
  self.onboard()
  for text in ('4','轻松打球','开始球局'):self.send(text)
  self.send(type='gps',data=dict(preview(4)['positions']['tee'],simulation_source='map_click'))
  self.assertIn('第4洞还没记分',self.send(type='simulation_hole',hole=5)['text'])
  self.send(type='simulation_hole',hole=4,clear_test_records=True)
  self.assertNotIn(4,self.e.state('j')['session']['gps_prompted_holes'])
  self.assertIn('第4洞还没记分',self.send(type='simulation_hole',hole=5)['text'])
  self.assertNotIn('第4洞还没记分',self.send(type='simulation_hole',hole=5)['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_named_aggressive_choice_commits_before_audio_enable(self):
  self.onboard()
  for text in ('1','轻松打球','开始球局'):self.send(text)
  self.send(type='gps',data=dict(preview(1)['positions']['tee'],simulation_source='map_click'))
  self.send('这杆怎么打')
  from unittest.mock import patch
  from journey_tee_options import offer,reduce_journey
  from tee_strategy import analyze
  from journey import _apply_journey
  from shot_audio import arm,handle
  state=self.e.state('j');now=self.clock.timestamp()
  routes=[dict(kind='conservative',club_key='long_iron',club='4号铁',zone_id='short',target='中间',carry_yards=190,remaining_yards=210,risk='落区更宽'),dict(kind='aggressive',club_key='driver',club='一号木',zone_id='driver',target='中间',carry_yards=260,remaining_yards=140,risk='右侧沙坑')]
  event=dict(protocol_version=37,type='message',event_id='named-offer',observed_at=self.clock.isoformat(),_tee_geometry_v94=True,_carry_crossing_v96=True,_stroke_consistency_v111=True)
  offer(state,event,analyze(state,now),routes,now)
  with patch('journey_tee_options.build_routes',return_value=routes):
   selected=reduce_journey(state,dict(event,event_id='named-choice',text='进取方案'),state['version']+1,now)
  self.assertIn('沙坑',selected['text'])
  commit=dict(event,event_id='named-commit',text='按这个打')
  reply=_apply_journey(state,commit,state['version']+1,now)
  self.assertIn('好，开球用一号木',reply['text'])
  self.assertNotIn('consultation',state['journey'])
  arm(state,commit,now)
  handle(state,dict(commit,text='开启击球声音识别',protocol_version=111),now)
  self.assertEqual('armed',state['journey']['shot_audio']['phase'])
  handle(state,dict(commit,text='音频检测到疑似击球',protocol_version=111),now)
  self.assertEqual('waiting',state['journey']['shot_audio']['phase'])

 def test_old_background_landing_cannot_recreate_reset_hole_stroke(self):
  self.onboard()
  for text in ('7','轻松打球','开始球局'):self.send(text)
  tee=dict(preview(7)['positions']['tee'],simulation_source='map_click')
  landing=dict(preview(7)['positions']['fairway'],simulation_source='map_click')
  self.send(type='gps',data=tee);self.send(type='gps',data=landing)
  self.send(type='simulation_hole',hole=7,clear_test_records=True)
  before=self.e.state('j')['facts']['context.device_position']['value']
  rejected=self.send(type='gps',data=dict(landing,simulation_refresh=True))
  self.assertTrue(rejected['ignored']);self.assertEqual('stale_simulation_position',rejected['reason'])
  self.assertEqual(before,self.e.state('j')['facts']['context.device_position']['value'])
  self.send(type='gps',data=dict(tee,simulation_refresh=True))
  self.assertEqual([],view(self.e.state('j'))['round_records']['clubs'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_score_total_infers_one_putt_without_interrupted_score_dialogue(self):
  self.onboard()
  for text in ('7','轻松打球','开始球局'):self.send(text)
  from unittest.mock import patch
  self.send(type='gps',data=dict(preview(7)['positions']['tee'],simulation_source='map_click'))
  with patch('ball_rules.map_landing',return_value=None):
   self.send(type='gps',data=dict(preview(7)['positions']['fairway'],simulation_source='map_click'))
   self.send(type='gps',data=dict(preview(7)['positions']['green'],simulation_source='map_click'))
  self.send(type='simulation_hole',hole=8)
  for _ in range(3):
   reply=self.send(type='gps',data=dict(preview(8)['positions']['tee'],simulation_source='map_click',simulation_refresh=True))
   self.assertNotIn('第8洞',reply['text'])
  reply=self.send('3')['text']
  self.assertNotIn('几推',reply);self.assertIn('1推',reply)
  for _ in range(2):
   reply=self.send(type='gps',data=dict(preview(8)['positions']['tee'],simulation_source='map_click',simulation_refresh=True))
   self.assertNotIn('第8洞',reply['text'])
  self.assertTrue(self.send('确认记录').get('saved'))
  state=self.e.state('j');self.assertEqual(1,state['facts']['holes.7.putts']['value'])
  deferred=[self.send(type='gps',data=dict(preview(8)['positions']['tee'],simulation_source='map_click',simulation_refresh=True))['text'] for _ in range(3)]
  self.assertEqual(1,sum('第8洞' in text for text in deferred))
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_same_hole_navigation_keeps_shots_and_infers_putts(self):
  self.onboard()
  for text in ('8','轻松打球','开始球局'):self.send(text)
  from unittest.mock import patch
  from ball_rules import current
  self.send(type='gps',data=dict(preview(8)['positions']['tee'],simulation_source='map_click'))
  with patch('ball_rules.map_landing',return_value=None):
   self.send(type='gps',data=dict(preview(8)['positions']['fairway'],simulation_source='map_click'))
   self.send(type='gps',data=dict(preview(8)['positions']['green'],simulation_source='map_click'))
  import copy
  before=copy.deepcopy(current(self.e.state('j'))['sequence'])
  self.assertEqual(2,len(before))
  self.send(type='simulation_hole',hole=8)
  self.assertEqual(before,current(self.e.state('j'))['sequence'])
  self.send(type='simulation_hole',hole=9)
  reply=self.send('3')['text']
  self.assertIn('1推',reply);self.assertNotIn('几推',reply)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))
