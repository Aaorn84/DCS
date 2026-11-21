"""Cross-path regression cases for the seven protocol-110 audit findings."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_relief_confirmation as support
from ball_rules import current,penalties
from journey import view


class StrokeConsistencyTests(unittest.TestCase):
    protocol_version=111
    setUp=support.ReliefConfirmationTests.setUp
    tearDown=support.ReliefConfirmationTests.tearDown
    send=support.ReliefConfirmationTests.send
    onboard=support.ReliefConfirmationTests.onboard
    start=support.ReliefConfirmationTests.start
    point=support.ReliefConfirmationTests.point
    select_and_sound=support.ReliefConfirmationTests.select_and_sound
    water_drop=support.ReliefConfirmationTests.water_drop

    def check(self):
        self.assertEqual(self.e.state('j'),self.e.replay('j'))

    def test_ordinary_voice_landing_commits_once_then_map_fills_distance(self):
        self.start()
        self.select_and_sound()
        self.send('球道中间')
        before=view(self.e.state('j'))['round_records']['clubs']
        self.assertEqual(1,len(before))
        self.assertEqual('7号铁',before[0]['club'])
        self.assertIsNone(before[0]['total_horizontal_m'])
        with patch('ball_rules.map_landing',return_value=None):
            self.point()
        after=view(self.e.state('j'))['round_records']['clubs']
        self.assertEqual(1,len(after))
        self.assertIsNotNone(after[0]['total_horizontal_m'])
        self.check()

    def test_later_non_audio_shot_gets_its_own_incident(self):
        self.start()
        with patch('ball_rules.map_landing',return_value=None):
            self.select_and_sound()
            self.point()
            self.send('球道中间')
            self.point(22.70145,114.15055)
        flow=current(self.e.state('j'))
        latest=[item for item in flow['sequence'] if item['kind']=='stroke'][-1]['id']
        self.send('下水了')
        self.assertEqual(latest,current(self.e.state('j'))['incidents'][-1]['shot_id'])
        self.assertEqual(2,len(view(self.e.state('j'))['round_records']['clubs']))
        self.check()

    def test_score_cannot_override_recorded_penalty_silently(self):
        self.start()
        self.send('确认出界');self.send('已回原位');self.send('确认在当前位置')
        reply=self.send('第4洞6杆，2推，0罚杆')
        self.assertIn('逐杆记录有1罚杆',reply['text'])
        self.assertEqual('penalties',self.e.state('j')['session']['draft']['awaiting'])
        self.assertFalse(self.send('确认').get('saved'))
        self.send('撤销上次罚杆')
        self.send('0罚杆')
        self.assertEqual(0,self.e.state('j')['session']['draft']['penalties'])
        self.assertTrue(self.send('确认')['saved'])
        self.check()

    def test_reclassifying_ob_to_water_removes_the_old_penalty(self):
        self.start()
        self.send('确认出界')
        self.send('确认下水')
        self.send('原球可以打')
        self.assertEqual(0,penalties(self.e.state('j'),4))
        self.check()

    def test_dropped_replacement_cannot_be_abandoned_for_original(self):
        self.start()
        self.water_drop()
        flow=current(self.e.state('j'))
        self.assertNotEqual('original',flow['active_ball'])
        self.assertTrue(flow['incidents'][-1]['relief_applied'])
        self.assertIn('替代球已成为使用中球',self.send('原球可以打')['text'])
        self.assertEqual(1,penalties(self.e.state('j'),4))
        self.send('确认在当前位置')
        self.check()

    def test_unresolved_water_blocks_score_and_can_resume(self):
        self.start()
        self.send('确认下水')
        reply=self.send('第4洞4杆，2推，0罚杆')
        self.assertIn('未完成',reply['text'])
        self.assertEqual('incident',self.e.state('j')['session']['draft']['awaiting'])
        self.assertFalse(self.send('确认').get('saved'))
        self.send('原球可以打')
        self.send('继续记分')
        self.assertEqual('confirm',self.e.state('j')['session']['draft']['awaiting'])
        self.assertTrue(self.send('确认')['saved'])
        self.check()

    def test_legacy_incidents_remain_separate_when_last_is_undone(self):
        self.protocol_version=106
        self.start()
        self.send('确认出界');self.send('已回原位');self.point()
        self.point(22.70145,114.15055)
        self.send('确认下水');self.send('已在合法位置抛球');self.point(22.7016,114.15045)
        self.protocol_version=111
        self.send('我在')
        self.assertEqual(2,len(current(self.e.state('j'))['incidents']))
        self.assertEqual(2,penalties(self.e.state('j'),4))
        self.send('撤销上次罚杆')
        self.assertEqual(1,penalties(self.e.state('j'),4))
        self.check()

    def test_audio_landing_accepts_seen_prefix_and_green(self):
        self.start();self.select_and_sound()
        reply=self.send('看到了，果岭上')['text']
        self.assertIn('球在果岭上',reply)
        state=self.e.state('j')
        self.assertEqual('果岭',state['journey']['reported_landing']['lie'])
        self.assertEqual('idle',state['journey']['shot_audio']['phase'])
        self.assertFalse(state['journey']['shot_audio']['enabled'])
        self.assertEqual(1,len(view(state)['round_records']['clubs']))
        self.check()

    def test_unrecognized_landing_answer_can_be_rephrased(self):
        self.start();self.select_and_sound()
        self.send('我想一下')
        self.assertEqual('asked',self.e.state('j')['journey']['shot_audio']['phase'])
        self.assertIn('球在果岭上',self.send('果岭上')['text'])
        self.assertEqual(1,len(view(self.e.state('j'))['round_records']['clubs']))
        self.check()

    def test_two_audio_sessions_without_second_club_still_save_two_strokes(self):
        self.start();self.select_and_sound()
        self.send('沙坑')
        self.point()
        state=self.e.state('j')
        report=state['journey']['reported_landing']
        self.assertIsNotNone(report['position'])
        from approach_dialogue import prepare
        c={}
        prepare(state,c,self.clock.timestamp())
        self.assertEqual('沙坑',c['lie_report'])
        old_arm=state['journey']['shot_audio']['arm_id']
        self.send('开启击球声音识别')
        self.assertNotEqual(old_arm,self.e.state('j')['journey']['shot_audio']['arm_id'])
        self.send('音频检测到疑似击球')
        self.send('击球声音等待结束');self.send('击球声音等待结束')
        self.send('果岭上')
        state=self.e.state('j');rows=view(state)['round_records']['clubs']
        self.assertEqual(2,len(rows))
        self.assertEqual('7号铁',rows[0]['club'])
        self.assertIsNone(rows[1]['club'])
        self.assertIsNone(rows[1]['total_horizontal_m'])
        self.assertEqual('果岭',state['journey']['reported_landing']['lie'])
        self.check()
