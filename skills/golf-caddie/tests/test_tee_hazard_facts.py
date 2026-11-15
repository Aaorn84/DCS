import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_tee_options as base
from tee_hazard_facts import route_facts
from speech_presentation import spoken_text
class TeeHazardFactsTests(unittest.TestCase):
 setUp=base.TeeOptionsTests.setUp
 tearDown=base.TeeOptionsTests.tearDown
 begin=base.TeeOptionsTests.begin
 send=base.TeeOptionsTests.send
 def test_real_course_directions_and_read_only(self):
  self.begin();s=self.e.state('j');before=copy.deepcopy(s);routes=s['journey']['tee_route_options']['routes'];facts=route_facts(s,routes,self.clock.timestamp())
  self.assertEqual(s,before)
  self.assertEqual(set(facts),{'conservative','aggressive'})
  for f in facts.values():
   self.assertGreater(f['width_yards'],0)
   self.assertIsNotNone(f['bunker'])
   self.assertGreater(f['bunker']['far_m'],f['bunker']['near_m'])
  out=self.send('怎么打');text=spoken_text(out['text'],route_details=facts)
  self.assertIn('到前沿',text);self.assertIn('到后沿',text);self.assertEqual(text.count('？'),1)
 def test_no_contours_does_not_invent_distances(self):
  self.begin();s=self.e.state('j');routes=s['journey']['tee_route_options']['routes']
  for e in s['evidence'].values():
   for h in e.get('data',{}).get('holes',[]):h['surface_zones']=[];h['display_paths']=[]
  facts=route_facts(s,routes,self.clock.timestamp())
  self.assertTrue(all(v['bunker'] is None for v in facts.values()))
 def test_stale_fix_does_not_reuse_geometry(self):
  self.begin();s=self.e.state('j');self.assertEqual(route_facts(s,s['journey']['tee_route_options']['routes'],self.clock.timestamp()+120),{})

 def test_water_uses_its_own_contour_and_preserves_state(self):
  self.begin();s=self.e.state('j');routes=s['journey']['tee_route_options']['routes']
  for e in s['evidence'].values():
   for h in e.get('data',{}).get('holes',[]):
    for z in h.get('surface_zones',[]):
     if z.get('surface')=='bunker':z['surface']='water'
    for path in h.get('display_paths',[]):
     if path.get('kind')=='BunkerTrace':path['kind']='WaterTrace'
    for z in h.get('tee_strategy',{}).get('landing_zones',[]):
     for hazard in z.get('hazards',[]):
      if hazard['kind']=='bunker':hazard['kind']='water';hazard['label']='水障碍'
  before=copy.deepcopy(s);facts=route_facts(s,routes,self.clock.timestamp());self.assertEqual(s,before)
  for fact in facts.values():
   self.assertIsNone(fact['bunker']);self.assertIsNotNone(fact['water']);self.assertEqual(fact['water']['kind'],'water');self.assertGreater(fact['water']['far_m'],fact['water']['near_m'])
  value='保守：长铁杆约190码，瞄落区中间，预计下一杆约185码；落区约27码宽。\n进取：一号木约260码，瞄落区中间，预计下一杆约115码；右侧水障碍。\n预计距离以实际落点为准。今天想走哪条？'
  result=spoken_text(value,route_details=facts);self.assertIn('水域方向',result);self.assertIn('到后沿',result);self.assertNotIn('沙坑方向',result)
 def test_missing_water_contour_does_not_use_bunker(self):
  self.begin();s=self.e.state('j');routes=s['journey']['tee_route_options']['routes']
  for e in s['evidence'].values():
   for h in e.get('data',{}).get('holes',[]):
    h['surface_zones']=[z for z in h.get('surface_zones',[]) if z.get('surface')!='water'];h['display_paths']=[z for z in h.get('display_paths',[]) if z.get('kind')!='WaterTrace']
  facts=route_facts(s,routes,self.clock.timestamp());self.assertTrue(all(v['water'] is None for v in facts.values()));self.assertTrue(any(v['bunker'] for v in facts.values()))

 def test_same_fairway_bunker_not_far_green_bunker(self):
  self.begin();out=self.send('怎么打');s=self.e.state('j');facts=route_facts(s,out['tee_routes'],self.clock.timestamp())
  c=facts['conservative']['bunker'];a=facts['aggressive']['bunker']
  self.assertEqual(c['id'],a['id']);self.assertTrue(c['beyond_carry']);self.assertFalse(a['beyond_carry']);self.assertLess(a['far_m']/.9144,300)
  text=spoken_text(out['text'],route_details=facts);conservative=text.split('\n')[0]
  self.assertIn('到前沿',conservative);self.assertNotIn('飞越远沿',conservative);self.assertNotIn('还要留余量',conservative)
 def test_unmatched_bound_identity_cannot_fall_back_to_other_bunker(self):
  self.begin();s=self.e.state('j');routes=s['journey']['tee_route_options']['routes']
  for e in s['evidence'].values():
   for h in e.get('data',{}).get('holes',[]):
    for z in h.get('tee_strategy',{}).get('landing_zones',[]):
     for hazard in z.get('hazards',[]):
      if hazard['kind']=='bunker':hazard['id']='missing-known-bunker'
  facts=route_facts(s,routes,self.clock.timestamp());self.assertIsNone(facts['aggressive']['bunker'])

 def test_carry_window_includes_edges_and_spanning_obstacles(self):
  from tee_hazard_facts import within_carry_window
  def h(near,far):return {'near_m':near*.9144,'far_m':far*.9144}
  for interval in [(150,160),(240,250),(100,300),(200,210)]:self.assertTrue(within_carry_window(h(*interval),200))
  for interval in [(100,149.9),(250.1,300)]:self.assertFalse(within_carry_window(h(*interval),200))
 def test_outside_window_omits_stale_risk_copy(self):
  value='保守：长铁杆约190码，瞄落区中间，预计下一杆约185码；落区约27码宽。\n进取：一号木约260码，瞄落区中间，预计下一杆约115码；右侧沙坑，要留意偏向障碍的失误。\n预计距离以实际落点为准。今天想走哪条？'
  facts={'aggressive':{'width_yards':42,'outside_window':['bunker'],'bunker':None,'water':None}}
  result=spoken_text(value,route_details=facts);self.assertNotIn('沙坑',result);self.assertNotIn('近远沿',result);self.assertIn('42码',result)

 def test_carry_crossing_and_near_edge_warnings(self):
  value='保守：长铁杆约190码，瞄落区中间，预计下一杆约185码；落区约27码宽。\n进取：一号木约260码，瞄落区中间，预计下一杆约115码；右侧沙坑。\n预计距离以实际落点为准。今天想走哪条？'
  for label in ('bunker','water'):
   def render(carry):
    facts={'aggressive':{'width_yards':42,label:{'side':'右侧','near_m':225*.9144,'far_m':255*.9144,'carry_yards':carry}}}
    return spoken_text(value,route_details=facts).split('\n')[1]
   for carry in (220,240,255):
    text=render(carry);self.assertIn('到前沿',text);self.assertNotIn('到后沿',text);self.assertIn('另一条方案',text)
   self.assertIn('球滚动后有进入',render(220));self.assertIn('会落在'+('沙坑' if label=='bunker' else '水域')+'范围内',render(240))
   text=render(260);self.assertIn('到后沿',text);self.assertIn('余量偏小',text);self.assertIn('避开',text)
   self.assertNotIn('余量偏小',render(280))
