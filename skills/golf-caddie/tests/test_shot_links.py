import unittest,sys,copy
from pathlib import Path
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from phoenix_demo import preview
from shot_links import pair,handle
class ShotLinkTests(unittest.TestCase):
 def setUp(self):self.e=Engine(':memory:','a');self.e.create('j');self.n=0;self.clock=datetime.now().astimezone()-timedelta(seconds=30);self.protocol=28
 def tearDown(self):self.e.close()
 def send(self,text='',gps=None):
  self.n+=1;p=dict(protocol_version=self.protocol,type='gps' if gps else 'message',event_id='p'+str(self.n),observed_at=self.clock.isoformat())
  if gps:p['data']=gps
  else:p['text']=text
  return self.e.command('j',str(self.n),'journey_event',p)
 def begin(self):
  for t in ['先打球','东莞凤凰山（A+B蓝台演示）','蓝台','1','轻松打球','开始球局']:self.send(t)
 def point(self,kind):return dict(preview(1)['positions'][kind],simulation_source='map_click')
 def two_points(self):
  self.begin();self.clock+=timedelta(seconds=5);self.send(gps=self.point('fairway'));self.clock+=timedelta(seconds=10);self.send(gps=self.point('green'))
 def test_confirmation_records_total_not_carry_or_club_learning(self):
  self.two_points();r=self.send('上一杆打了多少？');self.assertIn('相距约165码',r['text']);self.assertIn('对吗',r['text']);self.assertNotIn('confirmed_shot_distances',self.e.state('j')['journey'])
  r=self.send('是的');self.assertIn('包含滚动',r['text']);j=self.e.state('j')['journey'];row=j['confirmed_shot_distances'][-1];self.assertFalse(row['carry']);self.assertFalse(row['learning_eligible']);self.assertIsNone(row['club']);self.assertEqual(len(j['confirmed_shot_distances']),1)
  self.assertNotIn('对吗',self.send('上一杆多远')['text']);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_duplicate_stationary_refresh_does_not_add_endpoint(self):
  self.two_points();before=pair(self.e.state('j'));self.clock+=timedelta(seconds=1);self.send(gps=self.point('green'));self.assertEqual(before,pair(self.e.state('j')))
 def test_two_strokes_or_relief_never_records_single_stroke(self):
  self.two_points();self.send('上一杆打了多少');r=self.send('不是，中间打了两杆');self.assertIn('不记成单杆',r['text']);self.assertNotIn('confirmed_shot_distances',self.e.state('j')['journey']);self.assertNotIn('对吗',self.send('上一杆距离多少')['text'])
 def test_bootstrap_pre_upgrade_accepted_points(self):
  self.protocol=27;self.two_points();self.assertNotIn('shot_location_candidates',self.e.state('j')['journey']);self.protocol=28;r=self.send('上一杆打了多少');self.assertIn('相距约165码',r['text']);self.send('对');self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_rejected_gps_cannot_be_recovered_as_endpoint(self):
  self.protocol=27;self.begin();self.clock+=timedelta(seconds=5);self.send(gps=self.point('fairway'));self.clock+=timedelta(seconds=.1);r=self.send(gps=self.point('green'));self.assertTrue(r['ignored']);self.protocol=28;r=self.send('上一杆打了多少');self.assertNotIn('对吗',r['text']);self.assertLess(len(pair(self.e.state('j'))),2)
 def test_other_topic_defers_question_and_yes_cannot_confirm_it(self):
  self.two_points();self.send('上一杆打了多少');self.send('果岭周边什么情况');self.assertNotIn('pending_shot_link',self.e.state('j')['journey']);self.send('是的');self.assertNotIn('confirmed_shot_distances',self.e.state('j')['journey'])
 def test_revoke_keeps_positions_and_history(self):
  self.two_points();self.send('上一杆打了多少');self.send('好');r=self.send('撤销上一杆距离');self.assertIn('已撤销',r['text']);self.assertFalse(self.e.state('j')['journey']['confirmed_shot_distances'][-1]['valid']);self.assertEqual(len(pair(self.e.state('j'))),2)
 def test_hole_and_position_change_invalidate_confirmation(self):
  self.two_points();self.send('上一杆打了多少');s=self.e.state('j');s['facts']['context.active_hole']['value']=2
  r=handle(s,dict(text='是的',event_id='hole'),datetime.now().timestamp());self.assertIn('已变化',r);self.assertNotIn('confirmed_shot_distances',s['journey'])
if __name__=='__main__':unittest.main()
