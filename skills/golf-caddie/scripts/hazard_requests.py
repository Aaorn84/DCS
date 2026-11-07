"""Hazard carry questions require a measured far edge, never a reference point or zone start."""
import re,math
from round_state import fact_value
from lie_position import fresh_position
from shot_evidence import haversine

def parse(text):
 clean=re.sub(r'[\s，,。！!？?]','',text)
 if re.search(r'罚|上一杆|上杆|刚才',clean):return None
 if not re.search(r'(?:过|飞过|飞越|越过|跨过|跨越|打过|远沿)',clean) or not re.search(r'(?:多少|多远|几码|几米|距离)',clean):return None
 kind='bunker' if re.search(r'沙坑|沙',clean) else 'water' if re.search(r'水|溪|河',clean) else None
 if not kind:return None
 side='right' if re.search(r'右侧|右边|右面',clean) else 'left' if re.search(r'左侧|左边|左面',clean) else None
 return {'kind':kind,'side':side,'unit':'米' if '米' in clean else '码' if '码' in clean else None}

def answer(s,request,now):
 label='沙坑' if request['kind']=='bunker' else '水障碍'
 eid=fact_value(s,'context.course_snapshot');e=s['evidence'].get(eid,{})
 hole=next((h for h in e.get('data',{}).get('holes',[]) if h['number']==fact_value(s,'context.active_hole')),None) if e.get('active') and e.get('phase')=='final' else None
 if not hole:return '当前还没有这洞的障碍远沿资料，暂时算不了飞越距离。'
 metadata=hole.get('tee_strategy',{});hazards={}
 if isinstance(metadata,dict) and metadata.get('verified') is True and metadata.get('source'):
  zones=metadata.get('landing_zones',[])
  if not isinstance(zones,list):zones=[]
  for zone in zones:
   if not isinstance(zone,dict) or not isinstance(zone.get('hazards',[]),list):continue
   for h in zone.get('hazards',[]):
    if not isinstance(h,dict):continue
    if h.get('kind')==request['kind'] and (not request['side'] or h.get('side')==request['side']):
     key=h.get('id')
     if not key:
      # Identity is unknown: no distance may be reported by conflating same-side hazards.
      return label+'的远沿距离还没有可靠数据，暂时算不了过障碍的码数。'
     if not isinstance(key,str):continue
     if key in hazards and hazards[key]!=h:return label+'远沿记录存在冲突，暂时不能报飞越距离。'
     hazards[key]=h
 if len(hazards)>1:return '你问的是哪个'+label+'？'
 if not hazards:return label+'的远沿距离还没有可靠数据，暂时算不了过障碍的码数。'
 h=next(iter(hazards.values()));edge=h.get('far_edge',{})
 valid=isinstance(edge,dict) and edge.get('verified') is True and bool(edge.get('source')) and all(type(edge.get(k)) in (int,float) and math.isfinite(edge[k]) and lo<=edge[k]<=hi for k,lo,hi in [('latitude',-85,85),('longitude',-180,180)])
 if not valid:return label+'的远沿距离还没有可靠数据，暂时算不了过障碍的码数。'
 pos=fresh_position(s,now)
 if not pos:return '更新当前位置后，我再报到'+label+'远沿的距离。'
 unit=request['unit'] or s.get('journey',{}).get('profile',{}).get('units',{}).get('value','码');d=haversine(pos['value'],edge)/(1 if unit=='米' else .9144)
 return '从当前设备位置到'+label+'远沿约'+str(round(d/5)*5)+unit+'；飞越还要留余量。'
