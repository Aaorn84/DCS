"""Read-only bunker distances from fresh position, with explicit ambiguity."""
import re,math
from round_state import fact_value

def handle(state,text,now):
 clean=re.sub(r'[\s，,。！？?!]','',text)
 if not re.fullmatch(r'.{0,12}沙坑(?:有)?(?:多远|多少(?:码|米)?|距离多少(?:码|米)?)(?:呢|啊|吗)?',clean):return None
 from lie_position import fresh_position
 pos=fresh_position(state,now)
 if not pos:return '请先更新当前球位，我再核对到沙坑的距离。'
 p=pos['value'];eid=fact_value(state,'context.course_snapshot');course=state.get('evidence',{}).get(eid,{}).get('data',{})
 hole=next((h for h in course.get('holes',[]) if h['number']==fact_value(state,'context.active_hole')),None)
 if not hole:return '当前球洞还没有可核对的沙坑地图。'
 from tee_geometry import mapped_polygons
 rings=mapped_polygons(hole,course.get('reference_simulation') is True)['bunker'];rows=[]
 for name,polygon in rings.items():
  points=[((x-p['longitude'])*111195*math.cos(math.radians(p['latitude'])),(y-p['latitude'])*111195) for x,y in polygon[0]]
  near=float('inf')
  for (x,y),(u,v) in zip(points,points[1:]):
   dx,dy=u-x,v-y;t=max(0,min(1,-(x*dx+y*dy)/(dx*dx+dy*dy))) if dx*dx+dy*dy else 0
   near=min(near,math.hypot(x+t*dx,y+t*dy))
  far=max(math.hypot(x,y) for x,y in points);rows.append((near,far))
 if not rows:return '当前地图没有可核对的沙坑边界，请现场确认。'
 rows.sort();unit=state.get('journey',{}).get('profile',{}).get('units',{}).get('value','码');div=1 if unit=='米' else .9144
 # Do not silently choose one of several bunkers based only on proximity.
 j=state.get('journey',{});c=j.get('consultation') or {}
 options=([c['suggestion']] if c.get('suggestion') else (c.get('last_offer') or {}).get('options',[]))
 refs={m.group(1) for o in options for m in [re.search(r'约(\d+)(?:码|米)的沙坑',o.get('target',''))] if m}
 if len(refs)==1:
  distance=float(next(iter(refs)))*div
  matches=[r for r in rows if r[0]-10<=distance<=r[1]+10]
  if len(matches)==1:rows=matches
 selected=rows if len(rows)<=3 else rows[:3]
 lines=[f'{"沙坑" if len(rows)==1 else "按距离从近到远，第"+str(i+1)+"处沙坑"}近沿约{round(a/div)}{unit}，远沿约{round(b/div)}{unit}。' for i,(a,b) in enumerate(selected)]
 return ('地图上有多处沙坑，先列最近的'+str(len(selected))+'处；请确认你问的是哪一处。' if len(rows)>1 else '')+''.join(lines)+'这是当前球位到沙坑边界的直线距离，不代表沿瞄准线必须飞越的距离。'
