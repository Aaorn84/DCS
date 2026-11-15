"""Read-only tee-route hazard facts for presentation, never shot or learning updates."""
import math,copy
from round_state import fact_value
from tee_strategy import analyze

def within_carry_window(hazard,carry_yards):
 # Compare unrounded extents in yards, inclusive; a long hazard may span the window.
 return hazard['near_m']/.9144<=carry_yards+50+1e-8 and hazard['far_m']/.9144>=carry_yards-50-1e-8

def route_facts(state, routes, now):
 a=analyze(state,now)
 if not a:return {}
 course=state['evidence'][a['course_evidence']]['data']
 hole=next(h for h in course['holes'] if h['number']==a['hole'])
 pos=state['facts']['context.device_position']['value']
 green=next(o for o in hole['objects'] if o['kind']=='green_center')
 cos=math.cos(math.radians(pos['latitude']))
 def xy(lon,lat):return ((lon-pos['longitude'])*111000*cos,(lat-pos['latitude'])*111000)
 gx,gy=xy(green['longitude'],green['latitude']);length=math.hypot(gx,gy)
 if length<5:return {}
 fx,fy=gx/length,gy/length
 polygons={}
 for z in hole.get('surface_zones',[]):
  g=z.get('geometry',{})
  if z.get('surface') in ('bunker','water') and z.get('verified') is True and z.get('source') and g.get('type')=='Polygon':polygons[(z['surface'],z['id'])]=g.get('coordinates',[])
 if course.get('reference_simulation') is True:
  for p in hole.get('display_paths',[]):
   if p.get('kind') in ('BunkerTrace','WaterTrace') and len(p.get('points',[]))>=3:
    ring=[[v['longitude'],v['latitude']] for v in p['points']]
    polygons[('bunker' if p['kind']=='BunkerTrace' else 'water',p['id'])]=[ring]
 candidates=[]
 for (hazard_kind,identity),rings in polygons.items():
  if not rings or len(rings[0])<3:continue
  pts=[xy(*v[:2]) for v in rings[0]]
  if pts[0]==pts[-1]:pts=pts[:-1]
  cx=sum(x for x,y in pts)/len(pts);cy=sum(y for x,y in pts)/len(pts)
  forward=cx*fx+cy*fy;lateral=cx*fy-cy*fx
  # Only obstacles beside or on the forward playing corridor, before the green.
  if not 0<forward<length or abs(lateral)>80:continue
  distance=math.hypot(cx,cy)
  if distance<1:continue
  ux,uy=cx/distance,cy/distance;cross=[]
  for ring in rings:
   points=[xy(*v[:2]) for v in ring]
   if points[0]!=points[-1]:points.append(points[0])
   for (x,y),(xx,yy) in zip(points,points[1:]):
    side=x*uy-y*ux;side2=xx*uy-yy*ux
    if abs(side2-side)<1e-9:continue
    t=-side/(side2-side)
    if 0<=t<=1:
     d=(x+t*(xx-x))*ux+(y+t*(yy-y))*uy
     if d>0:cross.append(d)
  if len(cross)<2:continue
  candidates.append(dict(kind=hazard_kind,id=identity,x=cx,y=cy,forward=forward,side='右侧' if lateral>5 else '左侧' if lateral< -5 else '前方',near_m=min(cross),far_m=max(cross)))
 result={}
 for route in routes:
  zone=next((z for z in a['candidates'] if z['zone_id']==route['zone_id']),None)
  if not zone:continue
  target=zone['zone'].get('target_reference') or green
  tx,ty=xy(target['longitude'],target['latitude']);norm=math.hypot(tx,ty)
  if norm<1:continue
  nearby=[]
  for candidate in candidates:
   b=copy.deepcopy(candidate);lateral=(b['x']*ty-b['y']*tx)/norm
   b['side']='右侧' if lateral>5 else '左侧' if lateral< -5 else '前方'
   nearby.append(b)
  sides={'right':'右侧','left':'左侧','center':'前方'}
  details={'width_yards':zone['zone']['width_yards'],'outside_window':[]}
  for hazard_kind in ('bunker','water'):
   mapped=[h for h in zone['zone']['hazards'] if h['kind']==hazard_kind]
   ids={h['id'] for h in mapped if h.get('id')}
   pool=[b for b in nearby if b['kind']==hazard_kind]
   if ids:
    # Match the actual obstacle attached to this landing zone, never a same-side substitute.
    pool=[b for b in pool if b['id'] in ids]
   else:
    expected={sides[h['side']] for h in mapped if h['side'] in sides}
    pool=[b for b in pool if (not expected or b['side'] in expected)]
   if pool and not any(within_carry_window(b,route['carry_yards']) for b in pool):details['outside_window'].append(hazard_kind)
   pool=[b for b in pool if within_carry_window(b,route['carry_yards'])]
   chosen=min(pool,key=lambda b:abs(b['forward']/.9144-route['carry_yards'])) if pool else None
   if chosen:
    chosen['carry_yards']=route['carry_yards']
    chosen['beyond_carry']=chosen['near_m']/.9144>route['carry_yards']
    chosen['mapped_sides']=[sides[h['side']] for h in mapped if h['side'] in sides]
   details[hazard_kind]=chosen
  result[route['kind']]=details
 return result
