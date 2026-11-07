"""Directional mapped extent beyond green edge, never a claim of playable or safe space."""
import re,math
from green_requests import requested as surroundings,answer as surroundings_answer
from round_state import fact_value
from lie_position import fresh_position,polygon_contains

def space_query(text):
 return bool(re.search(r'果岭(?:的)?(?:后|后面|后方|后侧|背后)',text) and re.search(r'空间|余量|多少|多远|几码|几米|多大|多长|能打长',text))
def requested(text):return space_query(text) or surroundings(text)

def answer(s,text,now):
 if not space_query(text):return surroundings_answer(s,text,now)
 eid=fact_value(s,'context.course_snapshot');e=s.get('evidence',{}).get(eid,{})
 h=next((h for h in e.get('data',{}).get('holes',[]) if h['number']==fact_value(s,'context.active_hole')),None) if e.get('active') and e.get('phase')=='final' else None
 if not h:return '当前球洞地图还不完整，暂时无法确认果岭后方空间。'
 greens=[o for o in h.get('objects',[]) if o.get('kind')=='green_center'];pos=fresh_position(s,now)
 if len(greens)!=1:return '地图缺少果岭参考点，暂时无法计算后方空间。'
 if not pos:return '请先更新当前位置，我再按进攻方向查看果岭后方空间。'
 g=greens[0];p=pos['value'];cos=math.cos(math.radians(g['latitude']));dx=(g['longitude']-p['longitude'])*111000*cos;dy=(g['latitude']-p['latitude'])*111000;length=math.hypot(dx,dy)
 if length<10:return '目前太靠近果岭参考点，无法稳定判断进攻方向上的后方空间。'
 fx,fy=dx/length,dy/length
 def coordinates(v):
  x=(v['longitude']-g['longitude'])*111000*cos;y=(v['latitude']-g['latitude'])*111000
  return x*fy-y*fx,x*fx+y*fy
 def hits(path):
  pts=[coordinates(v) for v in path.get('points',[])]
  if len(pts)<3:return []
  out=[]
  for (x,y),(u,v) in zip(pts,pts[1:]+pts[:1]):
   if abs(u-x)<1e-8:continue
   t=-x/(u-x)
   if 0<=t<=1:
    distance=y+t*(v-y)
    if distance>0:out.append(distance)
  return sorted(set(round(v,4) for v in out))
 def contains(path):
  ring=[[v['longitude'],v['latitude']] for v in path.get('points',[])]
  if len(ring)<3:return False
  if ring[-1]!=ring[0]:ring.append(ring[0])
  return polygon_contains([ring],dict(g,accuracy_m=0))
 paths=h.get('display_paths',[])
 green_paths=[v for v in paths if v.get('kind')=='GreenTrace' and contains(v)]
 if len(green_paths)!=1 or not hits(green_paths[0]):return '地图还不能可靠确定果岭后沿，暂时无法报后方余量。'
 edge=hits(green_paths[0])[0];limits=[]
 boundaries=[v for v in paths if v.get('kind')=='HoleBoundry' and contains(v)]
 if len(boundaries)==1:
  exits=hits(boundaries[0])
  if exits and exits[0]>edge:limits.append((exits[0],'球洞图示边界'))
 for path in paths:
  label={'BunkerTrace':'后方沙坑近沿','WaterTrace':'后方水体近沿'}.get(path.get('kind'))
  if not label:continue
  intersections=hits(path)
  # An obstacle overlapping the green rear edge makes this simplified model indeterminate.
  if intersections and intersections[0]<=edge:return '果岭后沿与障碍图层存在重叠，暂时无法可靠计算后方余量。'
  if intersections:limits.append((intersections[0],label))
 if not limits:return '地图缺少后方障碍或边界资料，暂时无法确认有多少可用空间。'
 end,label=min(limits);unit='米' if '米' in text else '码' if '码' in text else s.get('journey',{}).get('profile',{}).get('units',{}).get('value','码')
 distance=(end-edge)/(1 if unit=='米' else .9144)
 return f'沿当前进攻方向，果岭后沿到{label}约{round(distance/5)*5:g}{unit}。这是图示间距，不代表可安全落球的空间。'
