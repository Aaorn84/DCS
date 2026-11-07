"""Map surface classification at confirmed ball-side device position; fail closed at boundaries."""
import math
from datetime import datetime
from round_state import fact_value
from gps_transition import inside
LABELS={'fairway':'球道','rough':'长草','bunker':'沙坑','green':'果岭','tee':'发球台'}
def fresh_position(s,now):
 p=s['facts'].get('context.device_position',{})
 if not p.get('valid'):return None
 v=p['value'];age=now-datetime.fromisoformat(v['observed_at'].replace('Z','+00:00')).timestamp()
 return p if -5<=age<=60 and v['accuracy_m']<=15 else None

def polygon_contains(rings,p):
 # Entire GPS uncertainty disk must be inside exterior, outside holes, away from every edge.
 if not isinstance(rings,list) or not rings:return False
 scale=111000;cos=math.cos(math.radians(p['latitude']));inside_outer=False
 for index,ring in enumerate(rings):
  if not isinstance(ring,list) or len(ring)<4 or ring[0]!=ring[-1]:return False
  points=[]
  for v in ring:
   if not isinstance(v,list) or len(v)!=2 or any(type(x) not in (int,float) or not math.isfinite(x) for x in v):return False
   points.append(((v[0]-p['longitude'])*scale*cos,(v[1]-p['latitude'])*scale))
  hit=False
  for (x,y),(u,v) in zip(points,points[1:]):
   dx=u-x;dy=v-y;length=dx*dx+dy*dy
   t=max(0,min(1,-(x*dx+y*dy)/length)) if length else 0
   if math.hypot(x+t*dx,y+t*dy)<=p['accuracy_m']:return False
   if (y>0)!=(v>0) and 0<x+(u-x)*(-y)/(v-y):hit=not hit
  if index==0:inside_outer=hit
  elif hit:return False
 return inside_outer

def infer(s,now):
 pos=fresh_position(s,now)
 if not pos:return None
 eid=fact_value(s,'context.course_snapshot');e=s['evidence'].get(eid,{})
 if not e.get('active') or e.get('phase')!='final':return None
 hole=next((h for h in e.get('data',{}).get('holes',[]) if h['number']==fact_value(s,'context.active_hole')),None)
 if not hole:return None
 zones=hole.get('surface_zones',[])
 if not isinstance(zones,list):return None
 matches=[]
 for z in zones:
  if not isinstance(z,dict) or z.get('surface') not in LABELS or z.get('verified') is not True or not z.get('source'):continue
  box=z.get('bbox');geo=z.get('geometry',{})
  valid_box=isinstance(box,list) and len(box)==4 and all(type(x) in (int,float) and math.isfinite(x) for x in box) and box[0]<box[2] and box[1]<box[3]
  hit=inside(box,pos['value']) if valid_box else False
  if isinstance(geo,dict) and geo.get('type')=='Polygon':hit=polygon_contains(geo.get('coordinates'),pos['value'])
  if hit:matches.append(z)
 if len(matches)!=1:return None
 z=matches[0]
 return {'label':LABELS[z['surface']],'source':'gps_course_surface','zone_id':z.get('id'),'map_source':z['source'],'course_evidence':eid,'position_version':pos['version'],'ball_side_source':'user_confirmed','status':'inferred'}
