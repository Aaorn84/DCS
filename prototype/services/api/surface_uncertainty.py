"""Read-only uncertainty disk containment for stored landing reports."""
import math
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
