import sys,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from approach_strategy import requested,advise
class ApproachTests(unittest.TestCase):
 def setUp(self):
  self.e=Engine(':memory:','a');self.e.create('j');self.n=0;self.now=1794000000
  for t in ['可以记住','球友','可以','不记录击球','230','140','偏右','演示球场（合成）','白台','1','轻松打球','状态不错','开始球局']:self.send(t)
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',data=None):
  self.n+=1;p=dict(protocol_version=5,type=kind,event_id='e'+str(self.n),observed_at=datetime.fromtimestamp(self.now,timezone.utc).isoformat())
  if kind=='message':p['text']=text
  else:p['data']=data
  return self.e.command('j',str(self.n),'journey_event',p,now=self.now)
 def gps(self,lon=121.00165):return self.send(kind='gps',data=dict(latitude=31,longitude=lon,accuracy_m=2))
 def test_distance_followup_risk(self):
  self.gps();self.send('还有多少码');r=self.send('下一杆有什么风险');self.assertIn('Carry',r['text']);self.assertIn('障碍',r['text']);self.assertEqual(r['text'].count('？'),1);self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'intent')
 def test_candidate_after_ball_confirmation(self):
  self.gps();self.send('这杆怎么打');self.send('想上果岭');r=self.send('就在球旁');self.assertIn('7铁可以作为',r['text']);c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['strategy_assessment']['suggestion']['club'],'7号铁')
 def test_risk_not_a_plan_or_decision(self):
  self.gps();self.send('这杆怎么打');self.send('稳一点');self.send('就在球旁');self.send('怎么避免风险');c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['phase'],'plan');self.assertNotIn('player_plan',c);self.assertNotIn('decision',c);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_point_hazard_not_safe_crossing(self):
  self.gps();s=self.e.state('j');eid=s['facts']['context.course_snapshot']['value'];s['evidence'][eid]['data']['holes'][0]['objects'].append(dict(id='water',kind='hazard_reference',latitude=31,longitude=121.002))
  a=advise(s,dict(ball_position_report='user_confirmed',lie_report='球道'),self.now);self.assertIn('不能据此判断能否跨越',a['text']);self.assertEqual(a['risks'][0]['geometry'],'point_only')
 def test_unknown_and_stale(self):
  a=advise(self.e.state('j'),{},self.now);self.assertIsNone(a['suggestion']);self.gps();a=advise(self.e.state('j'),{},self.now+61);self.assertNotIn('distance_m',a)
 def test_rough_not_use_fairway_carry(self):
  self.gps();a=advise(self.e.state('j'),dict(ball_position_report='user_confirmed',lie_report='长草'),self.now);self.assertIsNone(a['suggestion']);self.assertIn('脱困',a['text'])
 def test_supported_queries(self):
  for t in ['下一杆怎么选杆','这杆风险有哪些','有什么策略','用什么杆','下一杆注意什么']:self.assertTrue(requested(t))
if __name__=='__main__':unittest.main()
