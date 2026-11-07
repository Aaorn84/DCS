import unittest,sys,copy,time
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from green_space import requested,answer
class GreenSpaceTests(unittest.TestCase):
 def scene(self):
  def box(kind,w,s,e,n):return {'kind':kind,'points':[{'longitude':x,'latitude':y} for x,y in [(w,s),(e,s),(e,n),(w,n)]]}
  h={'number':1,'objects':[dict(kind='green_center',latitude=0,longitude=0)],'display_paths':[box('GreenTrace',-.0001,-.0001,.0001,.0001),box('HoleBoundry',-.0004,-.0004,.0004,.0004),box('BunkerTrace',-.00005,.0003,.00005,.00035)]}
  return {'facts':{'context.active_hole':dict(value=1,valid=True),'context.course_snapshot':dict(value='map',valid=True),'context.device_position':dict(valid=True,version=1,value=dict(latitude=-.001,longitude=0,accuracy_m=2,observed_at=datetime.now(timezone.utc).isoformat()))},'evidence':{'map':dict(active=True,phase='final',data={'holes':[h]})},'journey':{}}
 def test_common_phrases_route_as_map_questions(self):
  for q in ['果岭后有多少空间？','果岭后面还有多少余量','果岭后方多远','果岭的后侧空间多大']:self.assertTrue(requested(q))
 def test_nearest_obstacle_measured_from_rear_edge_not_center(self):
  s=self.scene();before=copy.deepcopy(s);text=answer(s,'果岭后有多少空间？',time.time());self.assertIn('果岭后沿到后方沙坑近沿约25码',text);self.assertIn('不代表可安全落球',text);self.assertEqual(s,before)
 def test_boundary_is_not_ob_or_playable_space(self):
  s=self.scene();s['evidence']['map']['data']['holes'][0]['display_paths'].pop();text=answer(s,'果岭后有多少空间？',time.time());self.assertIn('球洞图示边界约35码',text);self.assertNotIn('OB',text)
 def test_missing_green_edge_never_invents_distance(self):
  s=self.scene();s['evidence']['map']['data']['holes'][0]['display_paths'].pop(0);self.assertIn('无法报',answer(s,'果岭后有多少空间',time.time()))
 def test_explicit_meters_and_stale_position(self):
  s=self.scene();self.assertIn('约20米',answer(s,'果岭后多少米空间',time.time()));self.assertIn('更新当前位置',answer(s,'果岭后有多少空间',time.time()+90))
if __name__=='__main__':unittest.main()
