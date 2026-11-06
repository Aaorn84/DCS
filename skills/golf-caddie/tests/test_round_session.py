import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from round_state import Engine, StateError, valid_ref

COURSE = dict(course_id='synthetic', map_version='1', crs='WGS84', synthetic=True,
 holes=[dict(number=1, par=4, bbox=[120.999,30.999,121.004,31.002], objects=[dict(id='g1', kind='green_center',latitude=31.001,longitude=121.003)]),
        dict(number=2, par=4, bbox=[121.009,30.999,121.014,31.002], objects=[dict(id='g2',kind='green_center',latitude=31.001,longitude=121.013)])])
STAMP='2026-11-06T00:00:00Z'
NOW=1793923200


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.e=Engine(':memory:', 'a');self.e.create('r');self.n=0
    def tearDown(self):self.e.close()
    def event(self, type, **kwargs):
        self.n+=1
        return self.e.command('r', str(self.n), 'session_event', dict(type=type,event_id='e'+str(self.n),observed_at=STAMP,**kwargs),now=NOW)
    def course(self):return self.event('course', data=COURSE)
    def gps(self, longitude=121.001, **kw):
        return self.event('gps', data=dict(latitude=31, longitude=longitude, accuracy_m=2), **kw)
    def voice(self,text,**kw):return self.event('voice',text=text,**kw)
    def score(self):
        self.course();self.gps();self.voice('这洞六杆');self.voice('两推');return self.voice('没有罚杆')
    def test_three_inputs_atomic_score_confirmation(self):
        self.score()
        self.assertNotIn('holes.1.total',self.e.state('r')['facts'])
        self.assertTrue(self.voice('确认')['saved'])
        s=self.e.state('r');self.assertEqual(s['facts']['holes.1.total']['value'],6)
        self.assertEqual(s['facts']['holes.1.putts']['value'],2)
        self.assertEqual(s['facts']['holes.1.penalties']['value'],0)
        self.assertEqual(s,self.e.replay('r'))
    def test_questions_sequential(self):
        self.course();self.gps()
        self.assertEqual(self.voice('六杆')['text'],'这一洞几推？')
        self.assertIn('罚杆',self.voice('两推')['text'])
        self.assertIn('确认',self.voice('不清楚')['text'])
        self.voice('确认')
        self.assertIsNone(self.e.state('r')['facts']['holes.1.penalties']['value'])
    def test_bogey_does_not_force_penalty(self):
        self.course();self.gps();self.voice('五杆')
        self.assertIn('确认',self.voice('两推')['text'])
    def test_cross_hole_score_is_not_current_hole(self):
        self.course();self.gps(121.011)
        self.voice('一号洞五杆');self.voice('两推');self.voice('确认')
        s=self.e.state('r');self.assertEqual(s['facts']['context.active_hole']['value'],2)
        self.assertEqual(s['facts']['holes.1.total']['value'],5)
    def test_distance_has_origin_and_cannot_be_carry(self):
        self.course();self.gps()
        d=self.voice('还有多少码')
        self.assertEqual(d['distance']['origin'],'device_gps')
        self.assertFalse(d['distance']['carry'])
        self.assertIn('果岭中心',d['text']);self.assertGreater(d['distance']['meters'],100)
        self.assertFalse(any(k.startswith('shots.') for k in self.e.state('r')['facts']))
    def test_course_change_invalidates_distance(self):
        self.course();self.gps();self.voice('还有多少')
        ids=list(self.e.state('r')['derived']);self.course()
        self.assertFalse(self.e.state('r')['derived'][ids[0]]['valid'])
    def test_gps_move_invalidates_distance(self):
        self.course();self.gps();self.voice('还有多少');ids=list(self.e.state('r')['derived'])
        self.gps(121.002)
        self.assertFalse(self.e.state('r')['derived'][ids[0]]['valid'])
    def test_ambiguous_course_match_refuses_distance(self):
        c=copy.deepcopy(COURSE);c['holes'][1]['bbox']=c['holes'][0]['bbox']
        self.event('course',data=c);self.assertEqual(self.gps()['candidate_holes'],[1,2])
        with self.assertRaises(StateError):self.voice('还有多少')
    def test_stale_gps_refuses_distance(self):
        self.course()
        self.n+=1
        self.e.command('r',str(self.n),'session_event',dict(type='gps',event_id='stale',observed_at='2026-11-05T00:00:00Z',data=dict(latitude=31,longitude=121.001,accuracy_m=2)),now=NOW)
        with self.assertRaises(StateError):self.voice('还有多少')
    def test_unknown_hole_does_not_save(self):
        with self.assertRaises(StateError):self.voice('五杆')
        self.assertFalse(self.e.state('r')['facts'])
    def test_out_of_order_gps_is_ignored(self):
        self.course();self.gps();before=self.e.state('r')['session']['gps_evidence']
        self.n+=1
        r=self.e.command('r',str(self.n),'session_event',dict(type='gps',event_id='old',observed_at='2026-11-05T00:00:00Z',data=dict(latitude=31,longitude=121.011,accuracy_m=2)),now=NOW)
        self.assertTrue(r['ignored']);self.assertEqual(self.e.state('r')['session']['gps_evidence'],before)
    def test_quiet_not_reopened_by_gps(self):
        self.course();self.gps();self.assertTrue(self.voice('安静')['pause'])
        self.gps(121.011)
        self.assertTrue(self.e.state('r')['facts']['context.quiet']['value'])
        self.assertEqual(self.voice('六杆')['text'],'')
        self.voice('继续');self.assertFalse(self.e.state('r')['facts']['context.quiet']['value'])
    def test_retract_preserves_hole_and_course(self):
        self.score();self.voice('确认');self.gps(121.011)
        self.voice('撤销上一条记分')
        s=self.e.state('r');self.assertIsNone(s['facts']['holes.1.total']['value'])
        self.assertEqual(s['facts']['context.active_hole']['value'],2)
        self.assertEqual(s,self.e.replay('r'))
    def test_intervening_gps_requires_new_confirmation(self):
        self.score();self.gps()
        self.assertFalse(self.voice('确认')['saved'])
        self.assertTrue(self.voice('确认')['saved'])
    def test_partial_does_not_create_draft(self):
        r=self.voice('一号洞六杆',phase='partial')
        self.assertTrue(r['partial']);self.assertIsNone(self.e.state('r')['session']['draft'])
    def test_wrong_count_suffix_cannot_answer_putts(self):
        self.course();self.gps();self.voice('六杆');self.voice('两罚')
        self.assertNotIn('putts',self.e.state('r')['session']['draft'])
    def test_inconsistent_score_cannot_commit(self):
        self.course();self.gps();self.voice('三杆，两推，两罚')
        self.assertFalse(self.e.state('r')['facts'].get('holes.1.total'))
    def test_skipping_keeps_unknown_and_no_score(self):
        self.course();self.gps();self.voice('六杆');self.voice('先不记')
        self.assertNotIn('holes.1.total',self.e.state('r')['facts'])
        self.assertIsNone(self.e.state('r')['session']['draft'])
    def test_course_validation_is_atomic(self):
        bad=copy.deepcopy(COURSE);bad['holes'][1]['number']=1
        with self.assertRaises(StateError):self.event('course',data=bad)
        self.assertEqual(self.e.state('r')['version'],0)
    def test_unsupported_long_sentence_not_saved(self):
        self.course();self.gps();r=self.voice('我还是用了7铁，有点短，右边')
        self.assertTrue(r['unsupported']);self.assertFalse(any(k.startswith('shots.') for k in self.e.state('r')['facts']))

    def test_proactive_previous_score_binds_to_previous_hole(self):
        self.course();self.gps();self.voice('换洞时提醒记分')
        self.assertIn('上一洞',self.gps(121.011)['text'])
        self.assertEqual(self.gps(121.011)['text'],'')
        self.voice('五杆');self.voice('两推');self.voice('确认')
        self.assertEqual(self.e.state('r')['facts']['holes.1.total']['value'],5)
        self.assertNotIn('holes.2.total',self.e.state('r')['facts'])
    def test_no_proactive_without_agreement(self):
        self.course();self.gps()
        self.assertEqual(self.gps(121.011)['text'],'')
    def test_quiet_suppresses_agreed_proactive_prompt(self):
        self.course();self.gps();self.voice('换洞时提醒记分');self.voice('安静')
        self.assertEqual(self.gps(121.011)['text'],'')
        self.assertFalse(any(q['status']=='pending' for q in self.e.state('r')['questions'].values()))
