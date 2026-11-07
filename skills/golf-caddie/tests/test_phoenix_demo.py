import sys,unittest,copy,json
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from phoenix_demo import course,preview,generate,ID,NAME
from round_state import Engine
from round_session import course_schema,gps_matches
from tee_strategy import analyze
class PhoenixMapTests(unittest.TestCase):
 def test_source_points_all_holes_and_identity(self):
  c=course();course_schema(c);self.assertEqual(len(c['holes']),18);self.assertEqual(sum(h['par'] for h in c['holes']),72);self.assertEqual(sum(h['published_yardage'] for h in c['holes']),6388)
  self.assertFalse(c['production_spatial_use_allowed'])
  for h in c['holes']:
   for name,p in h['simulation_positions'].items():self.assertEqual(gps_matches(c,p),[h['number']],(h['number'],name))
  self.assertEqual(c['holes'][0]['source_hole_id'],475519);self.assertEqual(c['holes'][16]['source_hole_id'],475531)
 def test_widths_derived_not_old_synthetic_values(self):
  h=course()['holes'][0];z=next(z for z in h['tee_strategy']['landing_zones'] if z['start_yards']==220);self.assertEqual(z['width_yards'],44.3);self.assertTrue(any(x['kind']=='bunker' for x in z['hazards']));self.assertTrue(z['simulation_only']);self.assertEqual(h['display_paths'][0]['points'][0]['latitude'],22.700623448744366)
 def test_generated_asset_reproduces_source(self):
  root=Path(__file__).resolve().parents[3]/'球场数据接入样本/东莞凤凰山/data'
  normalized=json.loads((root/'course.normalized.json').read_text());route=json.loads((root/'route-ab-blue.example.json').read_text())
  self.assertEqual(generate(normalized,route),course())
  normalized['coordinate_confirmation']['crs']='unknown'
  with self.assertRaises(ValueError):generate(normalized,route)
 def test_full_phoenix_flow_snapshot_replay(self):
  e=Engine(':memory:','phoenix');e.create('j');clock=1794000000;n=0
  def send(text='',kind='message',data=None,dt=0):
   nonlocal n,clock
   n+=1;clock+=dt;p=dict(protocol_version=18,type=kind,event_id='e'+str(n),observed_at=datetime.fromtimestamp(clock,timezone.utc).isoformat())
   if kind=='message':p['text']=text
   else:p['data']=data
   return e.command('j',str(n),'journey_event',p,now=clock)
  for t in ['先打球',NAME,'蓝台','1','轻松打球','状态不错','开始球局']:send(t)
  p=preview(1)['positions'];send(kind='gps',data=p['tee']);r=send('到发球台了');self.assertIn('第1洞',r['text']);self.assertEqual(send('怎么打')['text'],'一号木平常的Carry大概多少码？')
  send('220');self.assertEqual(e.state('j')['journey']['round']['course'],ID)
  send(kind='gps',data=p['fairway'],dt=20);r=send('距离果岭还有多少');self.assertIn('distance',r);self.assertLess(r['distance']['meters'],200)
  # Replaying the saved command must not depend on the asset's future contents.
  import phoenix_demo
  original=phoenix_demo._asset
  phoenix_demo._asset=lambda:(_ for _ in ()).throw(AssertionError('replay read mutable asset'))
  try:self.assertEqual(e.state('j'),e.replay('j'))
  finally:phoenix_demo._asset=original;e.close()
