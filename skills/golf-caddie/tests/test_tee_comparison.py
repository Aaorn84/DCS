import sys,unittest
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from tee_comparison import analyze,proposal
class TeeComparisonTests(unittest.TestCase):
 def setUp(self):
  self.e=Engine(':memory:','c');self.e.create('j');self.n=0;self.clock=1794000000
  for text in ['可以记住','球友','可以','不记录击球','240','140','偏右','演示球场（合成）','白台','1','轻松打球','状态不错','开始球局']:self.send(text)
  self.send(kind='gps',data=dict(latitude=31,longitude=120.9992,accuracy_m=2));self.send('到发球台了')
 def tearDown(self):self.e.close()
 def send(self,text='',kind='message',data=None):
  self.n+=1;p=dict(protocol_version=8,type=kind,event_id='e'+str(self.n),observed_at=datetime.fromtimestamp(self.clock,timezone.utc).isoformat())
  if kind=='message':p['text']=text
  else:p['data']=data
  return self.e.command('j',str(self.n),'journey_event',p,now=self.clock)
 def test_unstated_intent_and_single_club_question(self):
  r=self.send('这杆怎么打');c=self.e.state('j')['journey']['consultation'];self.assertNotIn('player_intent',c);self.assertNotIn('结合你想',r['text']);self.assertIn('较进取',r['text']);self.assertIn('3号木',r['text']);self.assertEqual(r['text'].count('？'),1);self.assertEqual(c['phase'],'tee_club')
 def test_shorter_same_risk_not_safe(self):
  self.send('稳一点');r=self.send('210');self.assertIn('长铁',r['text']);r=self.send('4铁180码');c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['suggestion']['club'],'长铁杆');self.assertEqual(c['suggestion']['strategy'],'relative_conservative');self.assertIn('下一杆通常更长',r['text']);self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_safer_three_wood_if_different_zone(self):
  self.send('稳一点');r=self.send('190');self.assertNotIn('长铁杆平常',r['text']);c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['suggestion']['club'],'3号木')
 def test_declined_clubs_no_invention(self):
  self.send('这杆怎么打');self.send('不知道');self.send('没有这支杆');s=self.e.state('j');self.assertNotIn('three_wood',s['journey']['profile']);self.assertNotIn('long_iron',s['journey']['profile']);self.assertEqual(s['journey']['consultation']['suggestion']['club'],'7号铁')
 def test_explicit_attack_driver(self):
  r=self.send('争取进攻');c=self.e.state('j')['journey']['consultation'];self.assertEqual(c['player_intent'],'争取进攻');self.assertEqual(c['suggestion']['strategy'],'aggressive');self.assertEqual(c['suggestion']['club'],'一号木');self.assertIn('较进取',r['text'])
 def test_no_safe_alternative_no_relabel(self):
  a=analyze(self.e.state('j'),self.clock);a['clubs'].update(three_wood={},long_iron={});a['candidates']=[x for x in a['candidates'] if x['club_key']=='driver'];r=proposal(a,'稳一点');self.assertEqual(r['options'],[]);self.assertIn('不把同一条风险路线',r['text'])
 def test_total_club_distance_not_used_as_carry(self):
  self.send('这杆怎么打');r=self.send('总距离210码');self.assertNotIn('three_wood',self.e.state('j')['journey']['profile']);self.assertEqual(self.e.state('j')['journey']['consultation']['phase'],'tee_club')
if __name__=='__main__':unittest.main()
