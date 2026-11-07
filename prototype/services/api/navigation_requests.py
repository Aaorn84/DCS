"""Bounded navigation queries; never treats score or previous-shot requests as target distance."""
import re
from lie_position import fresh_position
from round_state import fact_value

def distance_unit(text,default='码'):
 clean=re.sub(r'[\s，,。！!？?]','',text)
 if re.fullmatch(r'(?:还有多少|还剩多少|多少|多远|距离)(?:码|米)?',clean) or re.fullmatch(r'(?:距离|到)?果岭(?:中心)?(?:还(?:有|剩)?|有|距离)?多少(?:码|米)?',clean):
  return '米' if clean.endswith('米') else '码' if clean.endswith('码') else default
 return None

def outside_tee(s,c,now):
 p=fresh_position(s,now)
 if not p:return False
 eid=fact_value(s,'context.course_snapshot');e=s['evidence'].get(eid,{})
 if not e.get('active') or e.get('phase')!='final':return False
 hole=next((h for h in e.get('data',{}).get('holes',[]) if h['number']==c.get('analysis',{}).get('hole')),None)
 if not hole or not hole.get('tee_bbox'):return False
 import math
 gps=p['value'];dy=gps['accuracy_m']/111000;dx=dy/max(.05,math.cos(math.radians(gps['latitude'])))
 w,south,east,n=hole['tee_bbox']
 return gps['longitude']+dx<w or gps['longitude']-dx>east or gps['latitude']+dy<south or gps['latitude']-dy>n

def selected_iron(text):
 clean=re.sub(r'[\s，,。！!？?]','',text)
 m=re.fullmatch(r'(?:好(?:的)?)?(?:那就|就)?(?:用|选|使用)([2-6])(?:号铁|铁)',clean)
 return int(m[1]) if m else None
