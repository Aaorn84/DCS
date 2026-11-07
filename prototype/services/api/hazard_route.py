"""Current-position hazard identity and line/polygon far-edge intersections.
Tee-radial vertices are not a valid general crossing distance.
"""
import math
from round_state import fact_value
from lie_position import fresh_position,polygon_contains
from shot_evidence import haversine

def answer(s,request,now):
 label='沙坑' if request['kind']=='bunker' else '水体'
 pos=fresh_position(s,now)
 if not pos:return '请先更新当前位置，我再计算这条线路的过'+('沙' if request['kind']=='bunker' else '水')+'距离。'
 eid=fact_value(s,'context.course_snapshot');e=s.get('evidence',{}).get(eid,{})
 course=e.get('data',{}) if e.get('active') and e.get('phase')=='final' else {}
 hole=next((h for h in course.get('holes',[]) if h['number']==fact_value(s,'context.active_hole')),None)
 if not hole:return '当前球洞地图不完整，暂时无法计算过'+label+'的距离。'
 greens=[v for v in hole.get('objects',[]) if v.get('kind')=='green_center']
 if len(greens)!=1:return '缺少明确目标方向，暂时无法计算当前线路的障碍远沿。'
 p=pos['value'];g=greens[0];cos=math.cos(math.radians(p['latitude']));dx=(g['longitude']-p['longitude'])*111000*cos;dy=(g['latitude']-p['latitude'])*111000;length=math.hypot(dx,dy)
 if length<5:return '当前位置太接近果岭参考点，无法稳定确定过障碍的方向。'
 fx,fy=dx/length,dy/length
 def xy(point):
  x=(point[0]-p['longitude'])*111000*cos;y=(point[1]-p['latitude'])*111000
  return x*fy-y*fx,x*fx+y*fy
 polygons={}
 for z in hole.get('surface_zones',[]):
  geometry=z.get('geometry',{})
  if z.get('surface')==request['kind'] and z.get('verified') is True and z.get('source') and geometry.get('type')=='Polygon':polygons[z['id']]=geometry.get('coordinates',[])
 if course.get('reference_simulation') is True:
  kind='BunkerTrace' if request['kind']=='bunker' else 'WaterTrace'
  for path in hole.get('display_paths',[]):
   if path.get('kind')!=kind or len(path.get('points',[]))<3:continue
   ring=[[v['longitude'],v['latitude']] for v in path['points']]
   if ring[0]!=ring[-1]:ring.append(ring[0])
   polygons[path['id']]=[ring]
 if not polygons:return '缺少'+label+'轮廓，暂时不能按当前线路计算过障碍的距离。'
 candidates=[]
 for identity,rings in polygons.items():
  crossings=[];xs=[]
  if not rings:continue
  for ring in rings:
   points=[xy(v) for v in ring];xs.extend(x for x,y in points)
   for (x,y),(u,v) in zip(points,points[1:]):
    if abs(u-x)<1e-8:continue
    t=-x/(u-x)
    if 0<=t<=1:crossings.append(y+t*(v-y))
  if not xs:continue
  lateral=(min(xs)+max(xs))/2
  if request.get('side')=='right' and lateral<=0:continue
  if request.get('side')=='left' and lateral>=0:continue
  distances=sorted(set(round(v,4) for v in crossings if v>=0))
  # Midpoint inclusion handles multiple lobes and interior holes on this particular ray.
  intervals=[];breaks=[0]+distances
  for a,b in zip(breaks,breaks[1:]):
   if b-a<1e-4:continue
   t=(a+b)/2;point=dict(latitude=p['latitude']+fy*t/111000,longitude=p['longitude']+fx*t/(111000*cos),accuracy_m=0)
   if polygon_contains(rings,point):intervals.append((a,b))
  if not intervals:continue
  near=min(a for a,b in intervals);far=max(b for a,b in intervals)
  if near>length+pos['value']['accuracy_m']:continue
  candidates.append(dict(id=identity,near_m=near,far_m=far))
 if not candidates:
  return '按当前位置朝果岭参考点的直线，没有找到需要飞越的'+label+'轮廓交点；刚才的风险可能来自路线旁的障碍，不能拿其他'+label+'的远沿代替。'
 # Recompute the same corridor used by short-game advice; never reuse a stale tee obstacle.
 from short_game_route import assess
 route=assess(s,now)
 discussed={v['id'] for v in route.get('obstacles',[]) if v['kind']==request['kind']}
 if discussed:
  relevant=[v for v in candidates if v['id'] in discussed]
  if not relevant:return '刚才提示的'+label+'在路线误差带旁，中心线路没有可靠的远沿交点；需要换一个明确飞越方向后再算。'
  candidates=relevant
 candidates.sort(key=lambda v:v['near_m'])
 if len(candidates)>1 and not request.get('rank'):return '这条线路上有多个'+label+'，你问近处还是远处？'
 chosen=candidates[-1] if request.get('rank')=='far' else candidates[0]
 unit=request.get('unit') or s.get('journey',{}).get('profile',{}).get('units',{}).get('value','码');scale=1 if unit=='米' else .9144
 # Use an upper 5-unit band so rounding never understates a crossing requirement.
 distance=math.ceil(chosen['far_m']/scale/5)*5
 s['journey']['last_hazard_route']={'hazard_id':chosen['id'],'kind':request['kind'],'course_evidence':eid,'hole':hole['number'],'position_version':pos['version'],'target':'green_reference','method':'current_position_ray_polygon_exit','near_m':chosen['near_m'],'far_m':chosen['far_m'],'simulation_only':course.get('reference_simulation') is True}
 text=f'沿当前位置到果岭参考点的直线，到这个{label}远沿约{distance:g}{unit}；飞越还要留余量。'
 if chosen['far_m']>length+pos['value']['accuracy_m']:text+='这个障碍沿线延伸到果岭参考点之后，不能把参考点距离当成过障碍距离。'
 return text
