import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_round_flow as base
from phoenix_demo import preview
from journey import view
class PinLocationTests(unittest.TestCase):
 setUp=base.RoundFlowTests.setUp
 tearDown=base.RoundFlowTests.tearDown
 begin=base.RoundFlowTests.begin
 protocol_version=40
 def send(self,text='',gps=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=self.protocol_version,type='gps' if gps else 'message',event_id='p'+str(self.n),observed_at=self.clock.isoformat(),**({'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def approach(self):
  self.begin(False);self.send(gps=dict(preview(1)['positions']['fairway'],simulation_source='map_click'));self.send('怎么打');return self.send('160')
 def test_one_question_each_then_reuse_and_replay(self):
  out=self.approach();self.assertIn('前部',out['text']);self.assertEqual(out['text'].count('？'),1);self.assertIn('前旗',view(self.e.state('j'))['choices'])
  out=self.send('前旗');self.assertIn('偏左',out['text']);self.assertEqual(out['text'].count('？'),1)
  out=self.send('偏右');self.assertIn('前旗偏右',out['text']);self.assertIn('到旗位约',out['text']);self.assertIn('pin_distance_estimate',out);self.assertNotIn('前部',self.send('怎么打')['text']);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_explicit_pin_distance_from_approach_position(self):
  self.approach();self.send('前旗');self.send('偏左')
  for text in ('如果按旗位距离是多少','按旗位的大概距离是多少？','旗杆距离大概多少'):
   out=self.send(text)
   self.assertIn('按前旗偏左和果岭轮廓估算，到旗位约',out['text'])
   self.assertGreater(out['pin_distance_estimate']['min_m'],50)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_distance_and_tee_do_not_prompt(self):
  self.begin();out=self.send('打多少');self.assertNotIn('旗在',out['text']);self.assertFalse(self.e.state('j')['journey'].get('pin_locations'))
 def test_skip_not_repeated(self):
  self.approach();out=self.send('跳过');self.assertNotIn('旗在',out['text']);self.assertNotIn('旗在',self.send('怎么打')['text'])
 def test_fact_interrupt_preserves_pending(self):
  self.approach();out=self.send('还有多少');self.assertIn('果岭',out['text']);self.assertIn('前部',self.send('怎么打')['text'])
 def test_duplicate_does_not_advance(self):
  self.approach();self.send('前旗');p=copy.deepcopy(self.last);out=self.e.command('j','retry','journey_event',p,now=self.clock.timestamp());self.assertTrue(out['duplicate']);rows=list(self.e.state('j')['journey']['pin_locations'].values());self.assertIsNone(rows[0]['side'])


class PinReplyRegressionTests(unittest.TestCase):
 setUp=base.RoundFlowTests.setUp
 tearDown=base.RoundFlowTests.tearDown
 begin=base.RoundFlowTests.begin
 send=PinLocationTests.send
 protocol_version=52

 def ask_pin_after_previous_distance(self):
  self.begin()
  self.send(gps=dict(preview(1)['positions']['fairway'],simulation_source='map_click'))
  self.assertIn('只打了一杆',self.send('上一杆打了多少')['text'])
  self.send('怎么打？')
  self.assertIn('前部',self.send('160')['text'])

 def test_combined_flag_position_continues_strategy(self):
  self.ask_pin_after_previous_distance()
  out=self.send('后部，偏左')
  self.assertIn('后旗偏左',out['text'])
  self.assertIn('pin_distance_estimate',out)
  j=self.e.state('j')['journey']
  self.assertFalse(j.get('confirmed_shot_distances'))
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_short_depth_and_assent_keep_the_correct_question(self):
  self.ask_pin_after_previous_distance()
  self.assertIn('居中',self.send('后')['text'])
  self.assertIn('居中',self.send('后部')['text'])
  self.assertIn('居中',self.send('对的')['text'])
  self.assertIn('后旗偏左',self.send('偏左')['text'])
  self.assertFalse(self.e.state('j')['journey'].get('confirmed_shot_distances'))


class EdgePinPreferenceTests(unittest.TestCase):
 setUp=base.RoundFlowTests.setUp
 tearDown=base.RoundFlowTests.tearDown
 begin=base.RoundFlowTests.begin
 send=PinLocationTests.send
 ask_pin_after_previous_distance=PinReplyRegressionTests.ask_pin_after_previous_distance
 protocol_version=56

 def test_preference_surfaces_only_for_edge_pin_strategy(self):
  self.ask_pin_after_previous_distance()
  self.send("允许跨场记忆")
  self.send("怎么打？")
  self.send('靠边旗我通常攻旗')
  out=self.send('后部，偏左')
  self.assertIn('确认有空间再考虑攻旗',out['text'])
  self.assertIn('别为追旗贴近左侧边缘',out['text'])
  self.assertNotIn('你喜欢攻旗',self.send('旗杆距离大概多少')['text'])
  self.send('忘记靠边旗打法偏好')
  self.assertNotIn('你喜欢攻旗',self.send('怎么打')['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_repeated_choices_at_same_pin_count_once(self):
  self.ask_pin_after_previous_distance()
  self.send("允许跨场记忆")
  self.send("怎么打？")
  self.send('后部，偏左')
  for _ in range(3):
   self.send('靠边旗两种目标都能打，我选打向果岭中央')
  journey=self.e.state('j')['journey']
  self.assertEqual(len(journey['shot_style_evidence']['edge_pin']),1)
  self.assertNotIn('edge_pin',journey['profile'].get('shot_style_preferences',{}))


class SpokenPinLocationTests(unittest.TestCase):
 setUp=base.RoundFlowTests.setUp
 tearDown=base.RoundFlowTests.tearDown
 begin=base.RoundFlowTests.begin
 send=PinLocationTests.send
 ask_pin_after_previous_distance=PinReplyRegressionTests.ask_pin_after_previous_distance
 protocol_version=67

 def test_front_and_near_left_in_one_reply(self):
  self.ask_pin_after_previous_distance()
  out=self.send('前部，靠左')
  self.assertIn('前旗偏左',out['text'])
  self.assertIn('pin_distance_estimate',out)
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_unclear_reply_keeps_question_open(self):
  self.ask_pin_after_previous_distance()
  self.assertIn('前部、中部',self.send('没看准位置')['text'])
  self.assertIn('偏右',self.send('前部')['text'])
  self.assertIn('前旗偏右',self.send('靠右')['text'])


class NaturalApproachReplyTests(SpokenPinLocationTests):
 protocol_version=69

 def test_reversed_pin_and_bare_iron(self):
  self.ask_pin_after_previous_distance()
  self.assertIn('后旗偏右',self.send('右后')['text'])
  self.assertIn('6号铁',self.send('6号铁')['text'])
  decision=self.e.state('j')['journey']['player_decisions'][-1]
  self.assertEqual(decision['target'],'green_center')
  self.assertFalse(decision['execution_confirmed'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

 def test_explicit_middle_target(self):
  self.ask_pin_after_previous_distance()
  self.send('右后')
  self.send('用6号铁打果岭中间')
  self.assertEqual(self.e.state('j')['journey']['player_decisions'][-1]['target'],'green_center')


class PitchingWedgeChoiceTests(SpokenPinLocationTests):
 protocol_version=81

 def test_pitching_wedge_choice_after_pin_reply(self):
  self.ask_pin_after_previous_distance()
  self.send('右后')
  self.assertIn('P杆',self.send('用P杆')['text'])
  decisions=self.e.state('j')['journey']['player_decisions']
  self.assertEqual(decisions[-1]['club'],'P杆')
  self.assertFalse(decisions[-1]['execution_confirmed'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))
