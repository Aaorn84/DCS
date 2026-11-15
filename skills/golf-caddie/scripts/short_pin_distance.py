"""Approximate pin distance using the observed pin sector and mapped green outline."""
import math,re
from round_state import fact_value,canonical
from dialogue_routing import scope
from lie_position import fresh_position,polygon_contains
from shot_evidence import haversine

def estimate(state,now,*,short_game_only=True, include_aim=False):
 pos=fresh_position(state,now)
 if not pos:return None
 course=state.get('evidence',{}).get(fact_value(state,'context.course_snapshot'),{}).get('data',{})
 hole=next((h for h in course.get('holes',[]) if h['number']==fact_value(state,'context.active_hole')),None)
 if not hole:return None
 greens=[o for o in hole.get('objects',[]) if o['kind']=='green_center']
 if len(greens)!=1:return None
 green=greens[0]
 if short_game_only and haversine(pos['value'],green)/.9144>50:return None
 row=state.get('journey',{}).get('pin_locations',{}).get(canonical(scope(state)),{})
 if row.get('status')!='complete' or row.get('depth') not in ('前','中','后'):return None
 rings=[]
 for z in hole.get('surface_zones',[]):
  if z.get('surface')=='green' and z.get('verified') is True and z.get('source') and z.get('geometry',{}).get('type')=='Polygon':
   candidate=z['geometry']['coordinates']
   if polygon_contains(candidate,{**green,'accuracy_m':0}):rings.append(candidate)
 if not rings and course.get('reference_simulation') is True:
  for path in hole.get('display_paths',[]):
   if path.get('kind')=='GreenTrace':
    candidate=[[[p['longitude'],p['latitude']] for p in path['points']]]
    if candidate[0] and candidate[0][0]!=candidate[0][-1]:candidate[0].append(candidate[0][0])
    if polygon_contains(candidate,{**green,'accuracy_m':0}):rings.append(candidate)
 if len(rings)!=1:return None
 rings=rings[0]
 tee=hole.get('simulation_positions',{}).get('tee') if course.get('reference_simulation') else None
 if not tee:
  box=hole.get('tee_bbox')
  if not box:return None
  tee={'longitude':(box[0]+box[2])/2,'latitude':(box[1]+box[3])/2}
 cos=math.cos(math.radians(green['latitude']))
 dx=(green['longitude']-tee['longitude'])*111000*cos;dy=(green['latitude']-tee['latitude'])*111000;norm=math.hypot(dx,dy)
 if norm<5:return None
 fx,fy=dx/norm,dy/norm
 def project(p):
  x=(p[0]-green['longitude'])*111000*cos;y=(p[1]-green['latitude'])*111000
  return x*fy-y*fx,x*fx+y*fy
 pts=[project(p) for p in rings[0]];xmin=min(x for x,y in pts);xmax=max(x for x,y in pts);ymin=min(y for x,y in pts);ymax=max(y for x,y in pts)
 if xmax-xmin<1 or ymax-ymin<1:return None
 def point(x,y):return {'longitude':green['longitude']+(x*fy+y*fx)/(111000*cos),'latitude':green['latitude']+(-x*fx+y*fy)/111000,'accuracy_m':0}
 depth={'前':0,'中':1,'后':2}[row['depth']];side={'左':0,'中':1,'右':2}.get(row.get('side'))
 lo=ymin+(ymax-ymin)*depth/3;hi=ymin+(ymax-ymin)*(depth+1)/3
 left=xmin if side is None else xmin+(xmax-xmin)*side/3;right=xmax if side is None else xmin+(xmax-xmin)*(side+1)/3
 distances=[]; aim=None; aim_error=float("inf")
 for i in range(21):
  for k in range(21):
   p=point(left+(right-left)*i/20,lo+(hi-lo)*k/20)
   if polygon_contains(rings,p):
    distances.append(haversine(pos['value'],p))
    if include_aim:
     error=(i-10)**2+(k-10)**2
     if error<aim_error:aim,aim_error=p,error
 if not distances:return None
 pad=pos['value']['accuracy_m']+math.hypot((right-left)/20,(hi-lo)/20)
 return {'min_m':max(0,min(distances)-pad),'max_m':max(distances)+pad,'depth':row['depth'],'side':row.get('side'),'method':'green_polygon_pin_thirds_range','source':'user_observed_pin_sector','not_for_learning':True,**({'aim':aim} if include_aim else {})}

def pin_distance_request(text):
 clean=re.sub(r'[\s，,。！!？?]','',text)
 return bool(re.fullmatch(r'(?:如果)?(?:按|到|距)?(?:旗位|旗杆)(?:(?:的|大概|大约|约)|距离|有)*是?(?:多少(?:码|米)?|多远|几码|几米)(?:呢|啊)?',clean))

def pin_distance_wording(result,unit):
 divisor=1 if unit=='米' else .9144
 pin=result['depth']+'旗'+('偏'+result['side'] if result['side'] in ('左','右') else '')
 midpoint=round((result['min_m']+result['max_m'])/2/divisor/5)*5
 return f'按{pin}和果岭轮廓估算，到旗位约{midpoint:g}{unit}'

def present_short_pin(state,text,now):
 pattern=r'到果岭(?:参考点|中心)(?:直线)?约[0-9.]+(码|米)'
 match=re.search(pattern,text)
 if not match:return text,None
 result=estimate(state,now)
 if not result:return text,None
 wording=pin_distance_wording(result,match[1])
 text=text[:match.start()]+wording+text[match.end():]
 text=text.replace('，不是旗杆距离','，这是旗位区域估算').replace('旗位只有方位信息，距离仍按果岭参考点。','这是旗位区域估算，非精确旗杆距离。')
 return text,result
