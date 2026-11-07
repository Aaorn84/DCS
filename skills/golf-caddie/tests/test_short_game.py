import sys,unittest,time,copy
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from short_game import handle,comparison
from round_state import Engine
from phoenix_demo import preview
from shot_evidence import haversine
import test_green_space
class ShortGameTests(unittest.TestCase):
 def scene(self):
  s=test_green_space.GreenSpaceTests().scene();s['facts']['context.device_position']['value']['latitude']=-.00025;s['journey']['round']={'id':'r'};s['journey']['consultation']={'phase':'plan','lie_report':'球道'};return s
 def test_comparison_not_declaration(self):
  for t in ['打高飞还是切滚呢？','打高飞还是切滚呢','切滚好还是高抛好']:self.assertTrue(comparison(t))
  self.assertFalse(comparison('我决定用切滚'))
 def test_one_question_and_clear_route_advice_is_not_player_decision(self):
  s=self.scene();before=copy.deepcopy(s['journey']['consultation']);r=handle(s,dict(text='打高飞还是切滚呢',event_id='q'),time.time());self.assertEqual(r.count('？'),1);self.assertNotIn('你选的是',r);self.assertEqual(before,s['journey']['consultation'])
  r=handle(s,dict(text='可以',event_id='a'),time.time());self.assertIn('更倾向切滚',r);self.assertNotIn('short_game_question',s['journey']);self.assertTrue(s['journey']['last_short_game_advice']['not_player_decision']);self.assertNotIn('decision',s['journey']['consultation'])
 def test_unknown_route_never_becomes_a_decision(self):
  s=self.scene();handle(s,dict(text='打高飞还是切滚呢',event_id='q'),time.time());r=handle(s,dict(text='不清楚',event_id='a'),time.time());self.assertIn('不假定',r);self.assertNotIn('short_game_question',s['journey']);self.assertNotIn('player_plan',s['journey']['consultation'])
 def test_blocked_route_uses_familiar_pitch_not_extreme_flop(self):
  s=self.scene();handle(s,dict(text='打高飞还是切滚呢',event_id='q'),time.time());r=handle(s,dict(text='有沙坑',event_id='a'),time.time());self.assertIn('别走地面',r);self.assertIn('不硬打高难度',r)
 def test_bunker_lie_and_changed_position(self):
  s=self.scene();s['journey']['consultation']['lie_report']='沙坑';self.assertIn('脱困',handle(s,dict(text='打高飞还是切滚呢',event_id='q'),time.time()))
  s=self.scene();handle(s,dict(text='打高飞还是切滚呢',event_id='q'),time.time());s['facts']['context.device_position']['value']['latitude']-=.0002;self.assertIn('已经变化',handle(s,dict(text='可以',event_id='a'),time.time()))
 def test_old_question_plan_is_removed(self):
  s=self.scene();c=s['journey']['consultation'];c.update(phase='commit',player_plan='打高飞还是切滚呢？');handle(s,dict(text='打高飞还是切滚呢',event_id='q'),time.time());self.assertNotIn('player_plan',c);self.assertEqual(c['phase'],'plan')
 def test_whole_journey_replays_without_committing_question(self):
  e=Engine(':memory:','a');e.create('j');n=0
  def send(text=None):
   nonlocal n;n+=1;p=dict(protocol_version=29,type='gps' if text is None else 'message',event_id='p'+str(n),observed_at=datetime.now().astimezone().isoformat())
   if text is None:
    m=preview(1)['positions'];a=m['fairway'];g=m['green'];ratio=27.432/haversine(a,g);p['data']=dict(latitude=g['latitude']+(a['latitude']-g['latitude'])*ratio,longitude=g['longitude']+(a['longitude']-g['longitude'])*ratio,accuracy_m=2,simulation_hole=1,simulation_source='map_click')
   else:p['text']=text
   return e.command('j',str(n),'journey_event',p)
  try:
   for t in ['先打球','东莞凤凰山（A+B蓝台演示）','蓝台','1','轻松打球','开始球局',None,'这杆怎么打','150']:send(t)
   if e.state('j')['journey']['consultation']['phase']=='lie':send('球道')
   r=send('打高飞还是切滚呢？');self.assertNotIn('你选的是',r['text']);self.assertNotIn('player_plan',e.state('j')['journey']['consultation']);send('可以');self.assertEqual(e.state('j'),e.replay('j'))
  finally:e.close()
if __name__=='__main__':unittest.main()
