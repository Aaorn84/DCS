import sys,unittest,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hazard_route import answer
import test_green_space
class HazardRouteTests(unittest.TestCase):
 def scene(self):
  s=test_green_space.GreenSpaceTests().scene();s['journey']['round']={'id':'r'};s['facts']['context.device_position']['value']['latitude']=-.0002635
  h=s['evidence']['map']['data']['holes'][0];h['surface_zones']=[];s['evidence']['map']['data']['reference_simulation']=True
  h['display_paths']=[self.box('b','BunkerTrace',-.00005,-.00018,.00005,-.00012)]
  h['tee_strategy']={'verified':True,'source':'tee-only','landing_zones':[{'hazards':[{'id':'wrong','kind':'bunker','side':'right','far_edge':{'latitude':.00052,'longitude':0,'verified':True,'source':'tee-radial'}}]}]}
  return s
 def box(self,id,kind,w,a,e,n):return {'id':id,'kind':kind,'source_path':id,'points':[{'latitude':y,'longitude':x} for x,y in [(w,a),(e,a),(e,n),(w,n),(w,a)]]}
 def query(self,s,**kw):return answer(s,dict(kind='bunker',side=None,unit=None,**kw),time.time())
 def test_32_to_green_cannot_select_unrelated_95_yard_tee_vertex(self):
  s=self.scene();r=self.query(s);self.assertIn('约20码',r);self.assertNotIn('95',r);self.assertEqual(s['journey']['last_hazard_route']['hazard_id'],'b');self.assertEqual(s['journey']['last_hazard_route']['method'],'current_position_ray_polygon_exit')
 def test_obstacle_off_line_is_not_reported_as_crossing(self):
  s=self.scene();s['evidence']['map']['data']['holes'][0]['display_paths']=[self.box('side','BunkerTrace',.00012,-.00018,.0002,-.0001)];r=self.query(s);self.assertIn('没有找到',r);self.assertNotIn('远沿约',r)
 def test_multiple_crossed_bunkers_require_one_identity_question(self):
  s=self.scene();s['evidence']['map']['data']['holes'][0]['display_paths'].append(self.box('near','BunkerTrace',-.00005,-.00025,.00005,-.00022));r=self.query(s);self.assertEqual(r.count('？'),1);self.assertIn('近处还是远处',r);self.assertIn('约10码',self.query(s,rank='near'));self.assertIn('约20码',self.query(s,rank='far'))
 def test_far_edge_beyond_green_is_explained_not_clamped(self):
  s=self.scene();s['evidence']['map']['data']['holes'][0]['display_paths']=[self.box('long','BunkerTrace',-.00005,-.00018,.00005,.0002)];r=self.query(s);self.assertIn('延伸到果岭参考点之后',r);self.assertIn('约60码',r)
 def test_missing_contour_never_uses_old_tee_far_edge(self):
  s=self.scene();s['evidence']['map']['data']['holes'][0]['display_paths']=[];self.assertIn('缺少沙坑轮廓',self.query(s))
 def test_moving_recomputes_distance_and_stale_fix_is_rejected(self):
  s=self.scene();self.assertIn('约20码',self.query(s));s['facts']['context.device_position']['value']['latitude']=-.0002;self.assertIn('约10码',self.query(s));self.assertIn('更新当前位置',answer(s,dict(kind='bunker'),time.time()+90))
if __name__=='__main__':unittest.main()
