"""End-to-end ball-identity and relief regression cases through journey events."""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_journey_recovery as support
from ball_rules import current, penalties
from journey import view
from round_state import fact_value
from phoenix_demo import preview


class BallRulesTests(unittest.TestCase):
    protocol_version=107
    setUp=support.JourneyRecoveryTests.setUp
    tearDown=support.JourneyRecoveryTests.tearDown
    send=support.JourneyRecoveryTests.send
    onboard=support.JourneyRecoveryTests.onboard

    def start(self):
        self.onboard()
        for word in ('3','轻松打球','开始球局'):
            self.send(word)
        self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))

    def point(self,lat=22.70130,lon=114.15062):
        return self.send(type='gps',data=dict(latitude=lat,longitude=lon,accuracy_m=2,
                                             simulation_hole=3,simulation_source='map_click'))

    def flow(self):
        return current(self.e.state('j'))

    def check_replay(self):
        self.assertEqual(self.e.state('j'),self.e.replay('j'))

    def test_separate_clubs_and_provisional_followups(self):
        self.start()
        self.send('好像OB了')
        self.send('暂定球已打，用3号木')
        self.point()
        self.send('暂定球又打了一杆')
        self.send('暂定球换了4号铁')
        self.point(22.702,114.1498)
        self.send('确认出界')
        self.point(22.702,114.1498)
        rows=view(self.e.state('j'))['round_records']['clubs']
        self.assertEqual([1,3,4],[row['stroke_number'] for row in rows])
        self.assertEqual(['3号木','4号铁'],[row['club'] for row in rows[1:]])
        self.assertEqual(1,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_second_provisional(self):
        self.start()
        self.send('可能出界')
        self.send('暂定球已打，用3号木')
        self.point()
        self.send('暂定球也出界了')
        self.send('第二颗暂定球已打，用4号铁')
        self.point(22.7014,114.15055)
        self.send('确认出界')
        self.point(22.7014,114.15055)
        rows=view(self.e.state('j'))['round_records']['clubs']
        self.assertEqual([1,3,5],[row['stroke_number'] for row in rows])
        self.assertEqual(2,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_original_found_discards_provisional(self):
        self.start()
        self.send('可能出界')
        self.send('暂定球已打，用3号木')
        self.point()
        self.assertIn('作废',self.send('没出界，在长草里')['text'])
        rows=view(self.e.state('j'))['round_records']['clubs']
        self.assertEqual(1,len(rows))
        self.assertEqual(0,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_search_deadline_and_identification(self):
        self.start()
        self.send('没找到')
        self.send('开始找球')
        self.send('暂定球已打')
        self.clock+=timedelta(seconds=181)
        self.assertIn('使用中球',self.send('找到原球')['text'])
        self.check_replay()

    def test_found_before_deadline_has_identification_time(self):
        self.start()
        self.send('没找到')
        self.send('开始找球')
        self.send('找到一个球，不确定是不是我的')
        self.clock+=timedelta(seconds=181)
        self.assertIn('继续打原球',self.send('确认是我的球')['text'])
        self.assertEqual(0,penalties(self.e.state('j'),3))

    def test_nearer_hole_and_late_found(self):
        self.start()
        self.send('可能出界')
        self.send('暂定球已打')
        self.point()
        self.send('暂定球已经从原球预计位置更靠洞处击球')
        self.assertIn('失去使用中球',self.send('找到原球')['text'])
        self.check_replay()

    def test_water_red_lateral_drop_twice_then_place(self):
        self.start()
        self.send('确认下水')
        self.send('红桩')
        self.send('侧向两杆范围抛球')
        self.send('已确认最后越界点')
        self.assertIn('再正确抛一次',self.send('抛球停在救济区外')['text'])
        self.assertIn('第二次抛球首次触地点',self.send('第二次也滚出去了')['text'])
        self.send('已在第二次落地点放置')
        self.assertEqual(1,penalties(self.e.state('j'),3))
        self.assertIn('当前位置',self.send('就在这里完成救济')['text'])
        self.assertIsNone(self.flow()['pending'])
        self.check_replay()

    def test_water_yellow_and_same_position(self):
        self.start()
        self.send('确认下水')
        self.send('黄桩')
        self.assertIn('需要确认红桩',self.send('侧向两杆范围抛球')['text'])
        self.send('向后延线抛球')
        self.send('已确认最后越界点')
        self.send('已在合法位置抛球')
        self.send('球停在救济区内')
        self.assertIn('当前位置',self.send('就在这里完成救济')['text'])
        self.assertIsNone(self.flow()['pending'])
        self.check_replay()

    def test_play_water_ball_as_it_lies(self):
        self.start()
        self.send('确认下水')
        self.assertIn('未增加',self.send('原球可以打')['text'])
        self.assertEqual(0,penalties(self.e.state('j'),3))
        self.assertNotIn('请更新',self.send('这杆怎么打')['text'])
        self.check_replay()

    def test_uncertain_water_needs_certainty(self):
        self.start()
        self.send('没找到，但是朝水飞去了')
        self.send('只可能进罚杆区')
        self.assertIn('通常不打暂定球',self.send('可以打暂定球吗')['text'])
        self.assertIn('罚杆区',self.send('三分钟没找到')['text'])
        self.send('也可能在长草里')
        self.assertIn('一杆加距离',self.send('三分钟没找到')['text'])

    def test_local_rule_scope_and_dropping_zone(self):
        self.start()
        self.send('确认下水')
        self.assertIn('尚未确认',self.send('已按当地规则E-5抛球')['text'])
        self.send('本洞采用指定抛球区')
        self.send('红桩')
        self.assertIn('已选择',self.send('使用指定抛球区')['text'])
        self.send('就在这里完成救济')
        self.assertEqual(1,penalties(self.e.state('j'),3))
        self.send(type='simulation_hole',hole=4)
        from ball_rules import rules_for
        self.assertFalse(rules_for(self.e.state('j')).get('dropping_zone'))

    def test_e5_and_b3(self):
        self.start()
        self.send('确认出界')
        self.send('本洞采用E-5')
        self.assertIn('两杆罚杆',self.send('已按当地规则E-5抛球')['text'])
        self.send('就在这里完成救济')
        self.assertEqual(2,penalties(self.e.state('j'),3))
        self.send(type='simulation_hole',hole=3)
        self.send('本洞采用B-3')
        self.send('可能下水')
        self.send('只可能进罚杆区')
        self.send('暂定球已打，用3号木')
        self.point()
        self.assertIn('继续罚杆区暂定球',self.send('找到原球在罚杆区')['text'])
        self.send('继续罚杆区暂定球')
        self.point()
        self.assertEqual(1,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_consecutive_incidents_and_correction(self):
        self.start()
        self.send('确认出界')
        self.send('已回原位')
        self.point(22.6994,114.1508)
        self.point()
        self.send('确认下水')
        self.send('红桩')
        self.send('原球可以打')
        self.assertEqual(1,penalties(self.e.state('j'),3))
        self.send('这杆又下水了')
        self.send('黄桩')
        self.send('回上一杆位置')
        self.send('已回原位')
        self.point(22.70135,114.15060)
        self.assertEqual(2,penalties(self.e.state('j'),3))
        self.assertIn('撤销',self.send('撤销上次罚杆')['text'])
        self.assertEqual(1,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_mistake_and_boundary(self):
        self.start()
        self.assertIn('整体',self.send('球好像压线了')['text'])
        self.send('确认出界')
        self.send('已回原位')
        self.point(22.6994,114.1508)
        self.assertIn('更正为红桩',self.send('实际是红桩区')['text'])
        self.assertEqual(0,penalties(self.e.state('j'),3))
        self.assertIn('恢复',self.send('刚才看错了，原球在界内')['text'])
        self.assertEqual(0,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_idempotent_event(self):
        self.start()
        self.send('确认出界')
        self.send('确认出界')
        self.assertEqual(1,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_full_par_five_ob_provisional_and_score(self):
        self.start()
        for word in ('这杆怎么打','3号木240码','没有','没有','没有','4号铁190码'):
            self.send(word)
        self.send(type='gps',data=dict(preview(3)['positions']['tee'],simulation_source='map_click'))
        self.send('1号木')
        self.send('应该是OB了')
        self.send('暂定球已打')
        self.assertIn('暂定球实际用',self.send('3号木')['text'])
        self.point()
        self.send('确认出界')
        self.point()
        self.send('这杆怎么打')
        self.send('左前')
        self.send('5号铁')
        self.send(type='gps',data=dict(preview(3)['positions']['green'],simulation_source='map_click'))
        self.send(type='simulation_hole',hole=4)
        self.send('第3洞6杆')
        self.send('两推')
        draft=self.e.state('j')['session']['draft']
        self.assertEqual((6,2,1),(draft['total'],draft['putts'],draft['penalties']))
        rows=[r for r in view(self.e.state('j'))['round_records']['clubs'] if r['hole']==3]
        self.assertEqual([1,3,4,5,6],[r['stroke_number'] for r in rows])
        self.assertEqual(['一号木','3号木','5号铁','推杆','推杆'],[r['club'] for r in rows])
        self.assertTrue(self.send('确认')['saved'])
        self.check_replay()

    def test_late_original_without_provisional_needs_replay(self):
        self.start()
        self.send('没找到')
        self.send('开始找球')
        self.clock+=timedelta(seconds=181)
        self.assertIn('一杆加距离',self.send('找到原球')['text'])
        self.assertEqual(1,penalties(self.e.state('j'),3))

    def test_b3_found_outside_discards_all_provisionals(self):
        self.start()
        self.send('本洞采用B-3')
        self.send('可能下水')
        self.send('只可能进罚杆区')
        self.send('暂定球已打')
        self.point()
        self.assertIn('作废',self.send('球在界内长草里')['text'])
        self.assertEqual(0,penalties(self.e.state('j'),3))
        self.assertEqual(1,len(view(self.e.state('j'))['round_records']['clubs']))

    def test_b3_certain_water_promotes(self):
        self.start()
        self.send('本洞采用B-3')
        self.send('可能下水')
        self.send('只可能进罚杆区')
        self.send('暂定球已打')
        self.point()
        self.assertIn('成为使用中球',self.send('确认下水')['text'])
        self.point()
        self.assertEqual(1,penalties(self.e.state('j'),3))

    def test_provisional_water_after_original_ob(self):
        self.start()
        self.send('可能OB')
        self.send('暂定球已打，用3号木')
        self.point()
        self.send('暂定球下水了')
        self.send('确认出界')
        self.assertIn('现场是红桩',self.point()['text'])
        self.send('黄桩')
        self.send('回上一杆位置')
        self.send('已回原位')
        self.point(22.70135,114.15060)
        self.assertEqual(2,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_e5_for_lost_provisional_and_duplicate(self):
        self.start()
        self.send('本洞采用E-5')
        self.send('可能OB')
        self.send('暂定球已打')
        self.point()
        self.send('暂定球也出界了')
        self.send('确认出界')
        self.point()
        self.assertIn('另加两杆',self.send('暂定球按E-5抛球')['text'])
        self.assertEqual(3,penalties(self.e.state('j'),3))
        self.point(22.7014,114.15060)
        self.send(type='simulation_hole',hole=3)
        self.send('确认出界')
        self.send('已按当地规则E-5抛球')
        self.send('已按当地规则E-5抛球')
        self.assertEqual(2,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_correction_invalidates_committed_score(self):
        self.start()
        self.send('确认出界')
        self.send('已回原位')
        self.point()
        self.send('第3洞6杆，2推，1罚杆')
        self.assertTrue(self.send('确认')['saved'])
        self.assertIn('重新确认',self.send('撤销上次罚杆')['text'])
        state=self.e.state('j')
        self.assertIsNone(fact_value(state,'holes.3.total'))
        self.assertEqual('penalties',state['session']['draft']['awaiting'])
        self.send('没有罚杆')
        self.assertEqual(0,self.e.state('j')['session']['draft']['penalties'])
        self.check_replay()

    def test_pre107_pending_provisional_migrates(self):
        self.protocol_version=106
        self.start()
        self.send('可能出界')
        self.send('暂定球已打')
        self.protocol_version=107
        self.assertIn('成为使用中球',self.send('确认出界')['text'])
        self.point()
        self.assertEqual([1,3],[r['stroke_number'] for r in view(self.e.state('j'))['round_records']['clubs']])
        self.check_replay()

    def test_refresh_does_not_complete_relief_but_explicit_near_position_does(self):
        self.start()
        self.send('确认出界')
        self.send('已回原位')
        data=dict(preview(3)['positions']['tee'],simulation_source='map_click',simulation_refresh=True)
        self.send(type='gps',data=data)
        self.assertIsNotNone(self.flow()['pending'])
        data.pop('simulation_refresh')
        result=self.send(type='gps',data=data)
        self.assertIn('移动未计作击球',result['text'])
        self.assertIsNone(self.flow()['pending'])
        self.assertEqual(1,len(view(self.e.state('j'))['round_records']['clubs']))
        self.check_replay()

    def test_wrong_drop_and_correction_before_play(self):
        self.start()
        self.send('确认下水')
        self.send('红桩')
        self.send('侧向两杆范围抛球')
        self.send('已确认最后越界点')
        self.assertIn('不计入两次正确抛球',self.send('抛球方式不对')['text'])
        self.assertIn('先纠正',self.send('击球前发现抛错位置')['text'])
        self.send('已在合法位置抛球')
        self.send('球停在救济区内')
        self.point()
        self.assertEqual(1,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_undeclared_provisional_and_original_found(self):
        self.start()
        self.send('好像OB了')
        self.assertIn('原球退出',self.send('没声明暂定球就打了')['text'])
        self.assertIn('失去使用中球',self.send('找到原球')['text'])
        self.point()
        self.assertEqual(1,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_provisional_request_and_invalid_provisional_already_played(self):
        self.start()
        self.assertIn('原球的去向',self.send('能不能先打暂定球')['text'])
        self.send('可能下水')
        self.send('只可能进罚杆区')
        self.assertIn('通常不打',self.send('先打一个暂定球可以吗')['text'])
        self.assertIn('一杆加距离成为使用中球',self.send('暂定球已打')['text'])
        self.assertEqual(1,penalties(self.e.state('j'),3))
        self.assertIn('原球已退出',self.send('确认下水')['text'])
        self.check_replay()

    def test_play_from_penalty_area_then_ob_extra_option(self):
        self.start()
        self.send('确认下水')
        self.send('原球可以打')
        self.point()
        self.send('这杆又出界了')
        self.assertIn('合计两杆罚杆',self.send('改按罚杆区向后延线')['text'])
        self.send('已确认最后越界点')
        self.send('就在这里完成救济')
        self.assertEqual(2,penalties(self.e.state('j'),3))
        self.check_replay()

    def test_score_total_conflict_can_be_corrected(self):
        self.start()
        self.send('确认出界')
        self.send('已回原位')
        self.point()
        self.point(22.702,114.1498)
        reply=self.send('第3洞3杆，2推，1罚杆')
        self.assertIn('至少',reply['text'])
        self.assertEqual('total',self.e.state('j')['session']['draft']['awaiting'])
        self.send('5')
        self.assertEqual('confirm',self.e.state('j')['session']['draft']['awaiting'])
        self.assertTrue(self.send('确认')['saved'])
        self.check_replay()

    def test_correct_map_landing_and_actual_club_preserves_one_stroke(self):
        self.start()
        self.point()
        self.send('上一杆实际用了3号木')
        before=view(self.e.state('j'))['round_records']['clubs']
        self.assertEqual('3号木',before[0]['club'])
        data=dict(latitude=22.7014,longitude=114.15060,accuracy_m=2,
                  simulation_hole=3,simulation_source='map_click',simulation_position_action='correct')
        self.send(type='gps',data=data)
        after=view(self.e.state('j'))['round_records']['clubs']
        self.assertEqual(1,len(after))
        self.assertEqual('3号木',after[0]['club'])
        self.assertNotEqual(before[0]['total_horizontal_m'],after[0]['total_horizontal_m'])
        self.check_replay()
