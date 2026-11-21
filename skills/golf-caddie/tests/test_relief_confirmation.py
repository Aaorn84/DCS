"""Current-shot outcome reports and relief confirmations through normal messages."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from ball_rules import current, penalties
from journey import view
from phoenix_demo import preview
import test_journey_recovery as support


class ReliefConfirmationTests(unittest.TestCase):
    protocol_version=110
    setUp=support.JourneyRecoveryTests.setUp
    tearDown=support.JourneyRecoveryTests.tearDown
    send=support.JourneyRecoveryTests.send
    onboard=support.JourneyRecoveryTests.onboard

    def start(self):
        self.onboard()
        for word in ('4','轻松打球','开始球局'):
            self.send(word)
        self.send(type='gps',data=dict(preview(4)['positions']['tee'],simulation_source='map_click'))

    def point(self, lat=22.70130, lon=114.15062):
        return self.send(type='gps',data=dict(latitude=lat,longitude=lon,accuracy_m=2,
                                             simulation_hole=4,simulation_source='map_click'))

    def water_drop(self):
        self.send('确认下水')
        self.send('黄桩')
        self.send('向后延线抛球')
        self.send('已确认最后越界点')
        self.send('已在合法位置抛球')
        return self.send('球停在救济区内')

    def select_and_sound(self):
        self.send(type='gps',data=dict(preview(4)['positions']['tee'],simulation_source='map_click'))
        self.send('这杆怎么打')
        self.send('中旗偏左')
        self.send('7号铁')
        self.send('开启击球声音识别')
        self.send('音频检测到疑似击球')
        self.send('击球声音等待结束')
        reply=self.send('击球声音等待结束')
        self.assertIn('看到球落哪儿',reply['text'])

    def test_new_audio_shot_is_not_old_water_duplicate(self):
        self.start()
        self.water_drop()
        self.send('就在这里完成救济')
        self.select_and_sound()
        reply=self.send('下水了')
        self.assertIn('红桩还是黄桩',reply['text'])
        flow=current(self.e.state('j'))
        self.assertEqual(2,len(flow['incidents']))
        self.assertEqual('water_color',flow['incidents'][-1]['phase'])
        self.assertEqual(self.e.state('j'),self.e.replay('j'))

    def test_confirmation_alias_and_short_confirmation(self):
        self.start()
        self.water_drop()
        self.assertIn('确认在当前位置',view(self.e.state('j'))['choices'])
        self.assertIn('可以再问',self.send('确认在当前位置')['text'])
        self.assertIsNone(current(self.e.state('j'))['pending'])
        self.send('这杆又下水了')
        self.send('黄桩')
        self.send('回上一杆位置')
        self.send('已回原位')
        self.assertIn('可以再问',self.send('确认')['text'])
        self.assertIsNone(current(self.e.state('j'))['pending'])
        self.assertEqual(2,penalties(self.e.state('j'),4))
        self.assertEqual(self.e.state('j'),self.e.replay('j'))

    def test_plot_before_drop_confirmation_becomes_next_origin(self):
        self.start()
        self.send('确认下水')
        self.send('黄桩')
        reply=self.send('向后延线抛球')
        self.assertNotIn('侧向',reply['text'])
        self.send('已确认最后越界点')
        self.point()
        self.send('已在合法位置抛球')
        result=self.send('球停在救济区内')
        self.assertIn('采用刚才提交的球位',result['text'])
        self.assertIsNone(current(self.e.state('j'))['pending'])
        self.assertNotIn('先处理这颗球',self.send('这杆怎么打')['text'])
        self.assertEqual(1,penalties(self.e.state('j'),4))
        self.assertEqual(self.e.state('j'),self.e.replay('j'))

    def test_voice_then_map_keeps_one_shot_and_distance(self):
        self.start()
        self.select_and_sound()
        self.send('下水了')
        result=self.point()
        self.assertIn('沿用已有击球记录',result['text'])
        rows=view(self.e.state('j'))['round_records']['clubs']
        self.assertEqual(1,len(rows))
        self.assertEqual('7号铁',rows[0]['club'])
        self.assertIsNotNone(rows[0]['total_horizontal_m'])
        self.send('确认下水')
        self.assertEqual(1,len(current(self.e.state('j'))['incidents']))
        self.assertEqual(self.e.state('j'),self.e.replay('j'))
