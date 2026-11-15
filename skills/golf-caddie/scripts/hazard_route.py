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


def landing_line(state, now, target=None, *, corridor=False, include_ob=False, stop_at_target=False):
 """Intersect green and mapped hazards along one explicit aiming ray."""
 pos=fresh_position(state,now)
 eid=fact_value(state,'context.course_snapshot')
 evidence=state.get('evidence',{}).get(eid,{})
 if not pos or not evidence.get('active') or evidence.get('phase')!='final':return None
 course=evidence['data']
 hole=next((h for h in course.get('holes',[]) if h['number']==fact_value(state,'context.active_hole')),None)
 if not hole:return None
 centers=[v for v in hole.get('objects',[]) if v['kind']=='green_center']
 if len(centers)!=1:return None
 target=target or centers[0]
 start=pos['value']
 scale=111000*math.cos(math.radians(start['latitude']))
 def xy(lon,lat):
  return (lon-start['longitude'])*scale,(lat-start['latitude'])*111000
 dx,dy=xy(target['longitude'],target['latitude'])
 length=math.hypot(dx,dy)
 if length<5:return None
 fx,fy=dx/length,dy/length
 polygons={kind:[] for kind in ('green','bunker','water')}
 if include_ob:polygons['ob']=[]
 for zone in hole.get('surface_zones',[]):
  shape=zone.get('geometry',{})
  if zone.get('surface') in polygons and zone.get('verified') is True and zone.get('source') and shape.get('type')=='Polygon':
   polygons[zone['surface']].append(shape['coordinates'])
 if course.get('reference_simulation') is True:
  kinds={'GreenTrace':'green','BunkerTrace':'bunker','WaterTrace':'water'}
  for path in hole.get('display_paths',[]):
   kind=kinds.get(path['kind'])
   if not kind or len(path['points'])<3:continue
   ring=[[point['longitude'],point['latitude']] for point in path['points']]
   polygons[kind].append([ring if ring[0]==ring[-1] else ring+[ring[0]]])
 def intervals(rings):
  crossings={0.0}
  for ring in rings:
   pts=[xy(*v) for v in ring]
   projected=[(x*fy-y*fx,x*fx+y*fy) for x,y in pts]
   for (x,a),(u,b) in zip(projected,projected[1:]):
    if abs(u-x)<1e-8:continue
    fraction=-x/(u-x)
    distance=a+fraction*(b-a)
    if 0<=fraction<=1 and distance>0:crossings.add(distance)
  cuts=sorted(crossings)
  for a,b in zip(cuts,cuts[1:]):
   mid=(a+b)/2
   point={'longitude':start['longitude']+fx*mid/scale,
          'latitude':start['latitude']+fy*mid/111000,'accuracy_m':0}
   if polygon_contains(rings,point):yield a,b
 green=next(((a,b) for rings in polygons['green'] for a,b in intervals(rings) if a<=length<=b),None)
 if not green:return None
 limit=length if stop_at_target else green[1]
 hazards={kind:max((b for rings in polygons[kind] for a,b in intervals(rings)
                    if a<limit),default=None) for kind in polygons if kind!='green'}
 if corridor:
  miss=state.get('journey',{}).get('profile',{}).get('usual_miss',{}).get('value')
  accuracy=start['accuracy_m']
  left=accuracy+(3 if miss=='偏左' else 0)
  right=accuracy+(3 if miss=='偏右' else 0)
  for kind in hazards:
   for rings in polygons[kind]:
    for ring in rings:
     pts=[xy(*point) for point in ring]
     projected=[(x*fy-y*fx,x*fx+y*fy) for x,y in pts]
     for (x,a),(u,b) in zip(projected,projected[1:]):
      if max(x,u)<-left or min(x,u)>right or max(a,b)<=0 or min(a,b)>=limit:continue
      if abs(u-x)>1e-8:
       limits=sorted(((-left-x)/(u-x),(right-x)/(u-x)))
       far=max(a+max(0,limits[0])*(b-a),a+min(1,limits[1])*(b-a))
      else:
       far=max(a,b)
      hazards[kind]=max(hazards[kind] or 0,far)
 return {'front_m':green[0],'back_m':green[1],'target_m':length,'hazards':hazards,
         'accuracy_m':start['accuracy_m'],
         'hazard_coverage_complete':hole.get('hazard_coverage_complete') is True}


def green_crossing_advice(state, now, *, target=None, short_game=False, lie=None):
 """Keep an airborne option when a mapped hazard leaves a usable carry window."""
 line=landing_line(state,now,target,corridor=True,include_ob=True,stop_at_target=True)
 if not line or not any(v is not None for v in line['hazards'].values()):
  return None
 far,kind=max((value,kind) for kind,value in line['hazards'].items() if value is not None)
 profile=state.get('journey',{}).get('profile',{})
 unit=profile.get('units',{}).get('value','码')
 scale=1 if unit=='米' else .9144
 margin=max(line['accuracy_m'], (2 if short_game else 3)*.9144)
 low=math.ceil((max(far,line['front_m'])+margin)/scale)
 # Reserve enough depth beyond the landing point for roll and range error.
 high=math.floor((line['back_m']-2*margin)/scale)
 before_target=math.floor((line['target_m']-margin)/scale)
 if low<=before_target:
  high=min(high,before_target)
 elif low<=high:
  deeper=landing_line(state,now,target,corridor=True,include_ob=True)
  far,kind=max((value,kind) for kind,value in deeper['hazards'].items() if value is not None)
  low=math.ceil((max(far,line['front_m'])+margin)/scale)
 label={'bunker':'沙坑','water':'水障碍','ob':'界外区域'}[kind]
 text=f'沿这条线，{label}远沿约{math.ceil(far/scale)}{unit}。'
 if low>high:
  return {'text':text+'按远沿和可用落点算，这条线的飞越与停球空间不足。可以改瞄果岭较宽处，再核对另一条线的Carry。'}
 distance=f'{low}–{high}{unit}' if low<high else f'{low}{unit}'
 text+=f'落点放在障碍后，目标Carry约{distance}。'
 if short_game or lie in ('长草','沙坑'):
  return {'text':text+'如果这个球位能打出你熟悉的抛切高度和Carry，可以走这条线。现场核对触球、障碍边缘和滚动空间后再打。'}
 from iron_estimates import iron_table,pitching_wedge
 table=iron_table(profile)
 clubs=[(f'{n}号铁',v['carry_yards']) for n,v in table.items()]
 wedge=pitching_wedge(profile,table)
 if wedge:
  clubs.append(('P杆',wedge['carry_yards']))
 for key,label in (('driver','一号木'),('three_wood','3号木'),('hybrid','铁木杆'),('long_iron','长铁杆')):
  club=profile.get(key,{}).get('value') or {}
  if isinstance(club,dict) and club.get('distance_type')=='carry' and club.get('units') in ('米','码'):
   distance=club.get('distance')
   if type(distance) in (int,float) and 0<distance<=400:
    clubs.append((club.get('club_name') or label,distance/(.9144 if club['units']=='米' else 1)))
 fits=[(abs(carry*.9144/scale-(low+high)/2),club) for club,carry in clubs
       if low<=carry*.9144/scale<=high]
 option=None
 if fits:
  _,club=min(fits)
  text+='按现有杆距，可考虑'+club+'。'
  option={'club':club,'status':'candidate','source':'mapped_crossing_window','not_for_learning':True}
 else:
  text+='按你能稳定打出的Carry选杆。'
 return {'text':text+'现场再核对球位、风和落地后的滚动空间。','option':option}
