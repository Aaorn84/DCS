import sys,unittest
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from journey import view
from phoenix_demo import preview
class GreenDialogueTests(unittest.TestCase):
 def setUp(self):self.e=Engine(':memory:','a');self.e.create('j');self.n=0
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',**kw):
  self.n+=1
  return self.e.command('j',str(self.n),'journey_event',dict(protocol_version=24,type=kind,event_id='p'+str(self.n),observed_at=datetime.now().astimezone().isoformat(),**({'text':text} if kind=='message' else {}),**kw))
 def begin(self,map_click=True):
  for t in ['先打球','东莞凤凰山（A+B蓝台演示）','蓝台','1','轻松打球','开始球局']:self.send(t)
  gps=dict(preview(1)['positions']['fairway'])
  if map_click:gps['simulation_source']='map_click'
  self.send(kind='gps',data=gps)
 def test_missing_carry_asks_only_one_direct_question(self):
  self.begin();r=self.send('你觉得应该用哪只杆？');self.assertEqual(r['text'],'7号铁平常的Carry大概多少码？');self.assertEqual(view(self.e.state('j'))['choices'],['不知道','跳过','自己打'])
 def test_map_selection_is_not_reasked_and_detail_is_not_spoken(self):
  self.begin();self.send('应该用哪支杆');r=self.send('150');self.assertNotIn('就在自己的球旁',r['text']);self.assertNotIn('障碍参考点距设备',r['text']);self.assertNotIn('这些不是障碍',r['text']);self.assertEqual(self.e.state('j')['journey']['consultation']['ball_position_report'],'simulation_selected');self.assertEqual(view(self.e.state('j'))['score_summary']['confirmed_holes'],0);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_plain_device_gps_does_not_confirm_ball(self):
  self.begin(False);self.send('用哪支杆');r=self.send('150');self.assertEqual(r['text'],'你现在就在自己的球旁吗？')
 def test_green_question_preserves_plan(self):
  import copy
  self.begin();self.send('用哪支杆');self.send('160');before=copy.deepcopy(self.e.state('j')['journey']['consultation'])
  for question in ['果岭右前侧有沙坑吗','果岭右前侧有沙坑吗？','果岭周边是什么情况？']:
   reply=self.send(question);self.assertNotIn('球旁',reply['text']);self.assertNotIn('位置已变化',reply['text']);self.assertIn('果岭',reply['text']);self.assertEqual(before,self.e.state('j')['journey']['consultation'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_refresh_does_not_invalidate_plan(self):
  self.begin();self.send('用哪支杆');self.send('160')
  gps=dict(preview(1)['positions']['fairway'],simulation_source='map_click');self.send(kind='gps',data=gps)
  r=self.send('7铁打向果岭中央');self.assertNotIn('位置已变化',r['text']);self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'commit')
 def test_actual_movement_and_stale_position_still_invalidate(self):
  import copy,time
  from green_requests import position_changed
  self.begin();self.send('用哪支杆');self.send('160');state=self.e.state('j');c=state['journey']['consultation'];pos=state['facts']['context.device_position'];pos['version']+=1;pos['value']['latitude']+=.0003
  self.assertTrue(position_changed(state,c,time.time()))
  pos['value']['latitude']-=.0003;self.assertFalse(position_changed(state,c,time.time()))
  self.assertTrue(position_changed(state,c,time.time()+90))
if __name__=='__main__':unittest.main()
