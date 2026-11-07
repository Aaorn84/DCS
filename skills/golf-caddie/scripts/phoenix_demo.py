"""Source-coordinate demo only: explicit independent-ring closure, no survey validation."""
import json,math,copy
from pathlib import Path
from functools import lru_cache
from shot_evidence import haversine
ID='dongguan-phoenix-ab-blue-demo'
NAME='东莞凤凰山（A+B蓝台演示）'
@lru_cache(maxsize=1)
def _asset():
 paths=[Path(__file__).parent/'assets/phoenix-demo.json',Path(__file__).parents[1]/'assets/courses/phoenix-demo.json']
 for p in paths:
  if p.is_file():return json.loads(p.read_text())
 raise ValueError('Phoenix demo asset missing')
def course():return copy.deepcopy(_asset())
def preview(number,snapshot=None):
 data=snapshot or _asset()
 h=next(h for h in data['holes'] if h['number']==number)
 return {'name':NAME,'hole':number,'source_name':h['source_name'],'par':h['par'],'published_yardage':h['published_yardage'],'positions':h['simulation_positions'],'paths':h['display_paths'],'source_sha256':data['source_sha256'],'bounds':h['bbox']}

def generate(normalized,route):
 """Derive demo geometry from real vertices. Source paths stay unchanged in display_paths."""
 from lie_position import polygon_contains
 confirmation=normalized.get('coordinate_confirmation',{})
 if normalized.get('source',{}).get('public_id')!='B87QFJP7' or confirmation.get('crs')!='WGS84' or confirmation.get('source_sha256')!=normalized['source']['sha256']:raise ValueError('confirmed Phoenix WGS84 source required')
 rows=route.get('holes',[])
 if len(rows)!=18 or any(h.get('round_hole_number')!=i+1 or h.get('course_id')!=(30914 if i<9 else 30915) or h.get('tee_id')!=(650688 if i<9 else 650692) for i,h in enumerate(rows)):raise ValueError('explicit A+B blue 18-hole route required')
 source=normalized['source']['sha256'];out={'course_id':ID,'map_version':'phoenix-demo-'+source[:12],'crs':'WGS84','synthetic':False,'reference_simulation':True,'production_spatial_use_allowed':False,'source_sha256':source,'geometry_assumptions':'Each source path closed as independent outer ring for simulation only; no inferred inner rings or OB.','holes':[]}
 def box(points,pad=0):return [min(p['longitude'] for p in points)-pad,min(p['latitude'] for p in points)-pad,max(p['longitude'] for p in points)+pad,max(p['latitude'] for p in points)+pad]
 for row in route['holes']:
  hid=row['hole_id'];n=row['round_hole_number'];src=next(h for h in normalized['holes'] if h['hole_id']==hid);refs=src['reference_coordinates'];tee=refs['teeGPSCoordinate'];green=refs['greenGPSCoordinate'];cos=math.cos(math.radians(tee['latitude']))
  def xy(p):return ((p['longitude']-tee['longitude'])*111000*cos,(p['latitude']-tee['latitude'])*111000)
  gx,gy=xy(green);dist=math.hypot(gx,gy);fx,fy=gx/dist,gy/dist;rx,ry=fy,-fx
  def project(p):
   x,y=xy(p);return x*rx+y*ry,x*fx+y*fy
  def unproject(x,y):return {'latitude':tee['latitude']+(x*ry+y*fy)/111000,'longitude':tee['longitude']+(x*rx+y*fx)/(111000*cos)}
  records=[g for g in normalized['geometry_records'] if g['hole_id']==hid]
  paths=[{'kind':g['source_type'],'id':str(hid)+':'+g['source_type']+':'+str(i),'source_path':g['source_path']+'/source_paths/'+str(i),'points':p} for g in records for i,p in enumerate(g['source_paths']) if len(p)>=3]
  boundaries=[p for p in paths if p['kind']=='HoleBoundry'];rings=[]
  for p in boundaries:
   ring=[[v['longitude'],v['latitude']] for v in p['points']]
   if ring[-1]!=ring[0]:ring.append(ring[0])
   rings.append(ring)
  def in_boundary(point):return any(polygon_contains([ring],dict(point,accuracy_m=2)) for ring in rings)
  surfaces=[]
  for p in paths:
   surface={'FairwayTrace':'fairway','BunkerTrace':'bunker','GreenTrace':'green','TeeboxTrace':'tee'}.get(p['kind'])
   if not surface:continue
   ring=[[v['longitude'],v['latitude']] for v in p['points']]
   if ring[-1]!=ring[0]:ring.append(ring[0])
   surfaces.append({'id':p['id'],'surface':surface,'verified':True,'verification_scope':'source_derived_simulation_only','source':source+':'+p['source_path'],'geometry':{'type':'Polygon','coordinates':[ring]}})
  fairways=[p for p in paths if p['kind']=='FairwayTrace'];obstacles=[p for p in paths if p['kind'] in ('BunkerTrace','WaterTrace')]
  def cross_intervals(station):
   intervals=[]
   for p in fairways:
    ring=[project(v) for v in p['points']];ring=ring+[ring[0]];hits=[]
    for (x,y),(u,v) in zip(ring,ring[1:]):
     if (y<=station<v) or (v<=station<y):hits.append(x+(u-x)*(station-y)/(v-y))
    hits.sort();intervals.extend((hits[i],hits[i+1]) for i in range(0,len(hits)-1,2))
   # Union overlapping independent paths to avoid double-counting width.
   merged=[]
   for lo,hi in sorted(intervals):
    if merged and lo<=merged[-1][1]:merged[-1]=(merged[-1][0],max(hi,merged[-1][1]))
    else:merged.append((lo,hi))
   return merged
  zones=[];midpoints=[]
  for start in range(40,331,5):
   station=(start+2.5)*.9144
   if station>dist-15:continue
   segments=cross_intervals(station)
   if not segments:continue
   lo,hi=min(segments,key=lambda t:0 if t[0]<=0<=t[1] else min(abs(t[0]),abs(t[1])))
   mid=(lo+hi)/2;target=unproject(mid,station)
   if not in_boundary(target):continue
   hazards=[]
   for p in obstacles:
    values=[project(v) for v in p['points']];min_y=min(v[1] for v in values);max_y=max(v[1] for v in values);min_x=min(v[0] for v in values);max_x=max(v[0] for v in values)
    lateral=max(0,lo-max_x,min_x-hi)
    if min_y<=station+15 and max_y>=station-15 and lateral<=35:
     side='right' if (min_x+max_x)/2>mid else 'left';far=max(p['points'],key=lambda v:haversine(tee,v))
     hazards.append({'id':p['id'],'side':side,'kind':'bunker' if p['kind']=='BunkerTrace' else 'water','label':'沙坑' if p['kind']=='BunkerTrace' else '水体','far_edge':dict(far,verified=True,verification_scope='source_vertex_simulation_only',source=source+':'+p['source_path']),'edge_method':'radial_farthest_source_vertex_from_reference_tee'})
   zones.append({'id':'station-'+str(start),'start_yards':start,'end_yards':start+4.999,'width_yards':round((hi-lo)/.9144,1),'preferred_side':'center','hazards':hazards,'target_reference':target,'width_method':'5yd_station_bin_midpoint_cross_section_independent_closed_source_paths','simulation_only':True})
   midpoints.append(target)
  approach=refs['approachGPSCoordinate']
  # Use source approach if it is on the simulated fairway; otherwise derive a visible fairway sample.
  fair_surfaces=[z for z in surfaces if z['surface']=='fairway']
  onfair=any(polygon_contains(z['geometry']['coordinates'],dict(approach,accuracy_m=2)) for z in fair_surfaces)
  if not in_boundary(approach) or not onfair:
   if midpoints:approach=min(midpoints,key=lambda v:haversine(v,refs['approachGPSCoordinate']))
  boundary_points=[v for p in boundaries for v in p['points']]+[tee,green,approach]
  def vicinity(p,meters):return [p['longitude']-meters/(111000*cos),p['latitude']-meters/111000,p['longitude']+meters/(111000*cos),p['latitude']+meters/111000]
  objects=[{'id':'green-'+str(hid),'kind':'green_center',**green,'reference_only':True,'source':source+':'+src['source_path']+'/reference_coordinates/greenGPSCoordinate'}]
  for p in obstacles:
   points=p['points'];center={'latitude':sum(v['latitude'] for v in points)/len(points),'longitude':sum(v['longitude'] for v in points)/len(points)}
   objects.append({'id':p['id'],'kind':'hazard_reference',**center,'source':source+':'+p['source_path']})
  out['holes'].append({'number':n,'source_hole_id':hid,'source_name':src['name'],'par':row['par'],'published_yardage':row['published_yardage'],'tee_id':row['tee_id'],'bbox':box(boundary_points,.00003),'tee_bbox':vicinity(tee,10),'green_bbox':vicinity(green,8),'simulation_boundary_rings':rings,'objects':objects,'surface_zones':surfaces,'tee_strategy':{'verified':True,'verification_scope':'source_derived_simulation_only','source':source,'landing_zones':zones},'display_paths':paths,'simulation_positions':{name:dict(p,accuracy_m=2,simulation_hole=n) for name,p in [('tee',tee),('fairway',approach),('green',green)]}})
 return out
if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser();parser.add_argument('normalized');parser.add_argument('route');parser.add_argument('output');a=parser.parse_args();result=generate(json.loads(Path(a.normalized).read_text()),json.loads(Path(a.route).read_text()));Path(a.output).parent.mkdir(parents=True,exist_ok=True);Path(a.output).write_text(json.dumps(result,ensure_ascii=False,separators=(',',':'))+'\n');print('Generated',len(result['holes']),'holes;',sum(len(h['tee_strategy']['landing_zones']) for h in result['holes']),'source-derived demo zones')
