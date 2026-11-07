import sys,unittest
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from journey import view
from phoenix_demo import preview
class ApproachDialogueTests(unittest.TestCase):
 def setUp(self):self.e=Engine(':memory:','a');self.e.create('j');self.n=0
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',**kw):
  self.n+=1
  return self.e.command('j',str(self.n),'journey_event',dict(protocol_version=23,type=kind,event_id='p'+str(self.n),observed_at=datetime.now().astimezone().isoformat(),**({'text':text} if kind=='message' else {}),**kw))
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
if __name__=='__main__':unittest.main()
