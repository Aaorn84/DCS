"""Conservative map-first corridor check; no terrain, grass-speed or pin inference."""
import math
from round_state import fact_value
from lie_position import fresh_position,polygon_contains
from shot_evidence import haversine

def assess(s,now):
 out={'verdict':'unknown','reason':'missing_geometry','limitations':['terrain_unavailable','grass_condition_unknown','green_speed_unknown','green_reference_not_pin'],'model':'sampled_uncertainty_corridor_v1'}
 pos=fresh_position(s,now);eid=fact_value(s,'context.course_snapshot');e=s.get('evidence',{}).get(eid,{})
 if not pos or not e.get('active') or e.get('phase')!='final':return out
 course=e.get('data',{});h=next((h for h in course.get('holes',[]) if h['number']==fact_value(s,'context.active_hole')),None)
 if not h:return out
 greens=[g for g in h.get('objects',[]) if g.get('kind')=='green_center']
 if len(greens)!=1:return out
 start=pos['value'];end=greens[0];length=haversine(start,end)
 if not 1<length<=80:return dict(out,reason='outside_short_game_range')
 zones=[]
 for z in h.get('surface_zones',[]):
  geo=z.get('geometry',{})
  if z.get('verified') is True and z.get('source') and geo.get('type')=='Polygon' and geo.get('coordinates'):
   zones.append(dict(id=z.get('id'),surface=z.get('surface'),rings=geo['coordinates'],source=z['source']))
 # Display paths have an explicit independent-ring convention only in this source demo.
 if course.get('reference_simulation') is True:
  for path in h.get('display_paths',[]):
   surface={'WaterTrace':'water','BunkerTrace':'bunker','RoughTrace':'rough','FairwayTrace':'fairway','GreenTrace':'green'}.get(path.get('kind'))
   pts=path.get('points',[])
   if not surface or len(pts)<3:continue
   ring=[[v['longitude'],v['latitude']] for v in pts]
   if ring[0]!=ring[-1]:ring.append(ring[0])
   if not any(z['id']==path.get('id') for z in zones):zones.append(dict(id=path.get('id'),surface=surface,rings=[ring],source=path.get('source_path')))
 if not zones:return out
 count=max(2,math.ceil(length)) # <= 1m between samples; uncertainty radius includes half-step.
 samples=[dict(latitude=start['latitude']+(end['latitude']-start['latitude'])*i/count,longitude=start['longitude']+(end['longitude']-start['longitude'])*i/count,accuracy_m=start['accuracy_m']) for i in range(count+1)]
 margin=start['accuracy_m']+length/count/2
 def touching(rings,p):
  if polygon_contains(rings,dict(p,accuracy_m=0)):return True
  cos=math.cos(math.radians(p['latitude']))
  for ring in rings:
   for a,b in zip(ring,ring[1:]):
    x=(a[0]-p['longitude'])*111000*cos;y=(a[1]-p['latitude'])*111000;u=(b[0]-p['longitude'])*111000*cos;v=(b[1]-p['latitude'])*111000
    dx=u-x;dy=v-y;t=max(0,min(1,-(x*dx+y*dy)/(dx*dx+dy*dy))) if dx or dy else 0
    if math.hypot(x+t*dx,y+t*dy)<=margin:return True
  return False
 obstacles=[z for z in zones if z['surface'] in ('bunker','water','rough')]
 crossed=[z for z in obstacles if any(touching(z['rings'],p) for p in samples)]
 out.update(course_evidence=eid,position_version=pos['version'],target='green_reference',distance_m=length,simulation_only=course.get('reference_simulation') is True)
 if crossed:return dict(out,verdict='blocked',reason='mapped_obstacle_in_corridor',obstacles=[{'id':z['id'],'kind':z['surface'],'source':z['source']} for z in crossed])
 allowed=[z for z in zones if z['surface'] in ('fairway','green')]
 def union_covers(p):
  # Check uncertainty around a point against the union, allowing fairway/green hand-off.
  cos=math.cos(math.radians(p['latitude']))
  for angle in [None]+[i*math.pi/4 for i in range(8)]:
   q=dict(p,accuracy_m=0)
   if angle is not None:
    q['latitude']+=margin*math.sin(angle)/111000;q['longitude']+=margin*math.cos(angle)/(111000*cos)
   if not any(polygon_contains(z['rings'],q) for z in allowed):return False
  return True
 covered=[union_covers(p) for p in samples]
 if not all(covered):return dict(out,reason='incomplete_or_ambiguous_surface_coverage',covered_samples=sum(covered),samples=len(samples))
 green_samples=[any(polygon_contains(z['rings'],p) for z in allowed if z['surface']=='green') for p in samples]
 run=0
 for on_green in reversed(green_samples):
  if not on_green:break
  run+=1
 usable_green_m=max(0,(run-1)*length/count)
 if usable_green_m<6:return dict(out,reason='insufficient_mapped_green_run',mapped_green_run_m=usable_green_m)
 return dict(out,verdict='clear',reason='continuously_mapped_fairway_green_corridor',mapped_green_run_m=usable_green_m,not_physical_roll_guarantee=True)
