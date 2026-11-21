import sys,unittest,random
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import tee_geometry as geometry
from lie_position import polygon_contains as original
from phoenix_demo import course
class PlanningGeometryCacheTests(unittest.TestCase):
 def test_exact_samples_match_full_uncertainty_algorithm(self):
  h=course()['holes'][17];polys=geometry.mapped_polygons(h,True);rng=random.Random(18)
  for collection in polys.values():
   for rings in collection.values():
    xs=[p[0] for p in rings[0]];ys=[p[1] for p in rings[0]]
    for _ in range(30):
     p=dict(longitude=rng.uniform(min(xs)-.0001,max(xs)+.0001),latitude=rng.uniform(min(ys)-.0001,max(ys)+.0001),accuracy_m=0)
     self.assertEqual(geometry.polygon_contains(rings,p),original(rings,p))
 def test_cache_reuses_validation_but_expires_between_plans(self):
  h={'display_paths':[]};calls=[]
  @geometry.planning_geometry_cache
  def plan():
   geometry.mapped_polygons(h,True);geometry.mapped_polygons(h,True)
  with patch('tee_geometry._mapped_polygons',side_effect=lambda *args:calls.append(1) or {}):
   plan();self.assertEqual(len(calls),1)
   plan();self.assertEqual(len(calls),2)
 def test_nonzero_uncertainty_keeps_original_disk_check(self):
  rings=[[[0,0],[1,0],[1,1],[0,1],[0,0]]]
  p=dict(latitude=.5,longitude=.000001,accuracy_m=2)
  self.assertEqual(geometry.polygon_contains(rings,p),original(rings,p))
 def test_tee_candidates_match_original_geometry(self):
  h=course()['holes'][17];snapshot=course()
  state={'evidence':{'map':{'data':snapshot}}}
  analysis=dict(course_evidence='map',hole=18)
  clubs=[('driver',dict(label='一号木',carry_yards=260)),('three_wood',dict(label='3号木',carry_yards=240))]
  origin=h['simulation_positions']['tee']
  fast=geometry.tee_targets(state,analysis,clubs,origin=origin,allow_crossing=True)
  with patch('tee_geometry.polygon_contains',side_effect=original):
   baseline=geometry.tee_targets(state,analysis,clubs,origin=origin,allow_crossing=True)
  self.assertEqual(fast,baseline)
 def test_exception_does_not_leave_cache_for_next_request(self):
  @geometry.planning_geometry_cache
  def fail():raise ValueError('stop')
  with self.assertRaises(ValueError):fail()
  self.assertIsNone(geometry._geometry_cache.get())
 def test_identical_targets_reused_only_inside_plan_with_copy_isolation(self):
  from unittest.mock import patch
  snapshot=course();s={'evidence':{'map':{'data':snapshot}}};a={'course_evidence':'map','hole':18};clubs=[('driver',dict(label='一号木',carry_yards=260))];origin=snapshot['holes'][17]['simulation_positions']['tee']
  @geometry.planning_geometry_cache
  def plan():
   first=geometry.tee_targets(s,a,clubs,origin=origin);first[0]['club']='mutated'
   second=geometry.tee_targets(s,a,clubs,origin=origin);self.assertNotEqual('mutated',second[0]['club'])
   geometry.tee_targets(s,a,clubs,origin=dict(origin,accuracy_m=origin['accuracy_m']+1))
  with patch('tee_geometry._tee_targets',side_effect=lambda *args,**kwargs:[{'club':'一号木','aim_point':{'latitude':1}}]) as compute:
   plan();self.assertEqual(2,compute.call_count)
   plan();self.assertEqual(4,compute.call_count)
