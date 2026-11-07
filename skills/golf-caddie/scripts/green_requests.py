"""Read-only green surroundings relative to the current approach; no score or plan mutation."""
import re,math
from round_state import fact_value
from lie_position import fresh_position
from shot_evidence import haversine

def requested(text):
 clean=re.sub(r'[\s，,。！!？?]','',text)
 from hazard_requests import parse
 if parse(clean):return False
 return ('果岭' in clean and bool(re.search(r'周边|周围|附近|右前|左前|前侧|后侧|右侧|左侧|右边|左边|前方|后方',clean)) and bool(re.search(r'吗|什么|情况|有没有|是否|哪里|哪些|有沙坑|有水',clean)))

def answer(s,text,now):
 eid=fact_value(s,'context.course_snapshot');e=s.get('evidence',{}).get(eid,{})
 h=next((h for h in e.get('data',{}).get('holes',[]) if h['number']==fact_value(s,'context.active_hole')),None) if e.get('active') and e.get('phase')=='final' else None
 if not h:return '还没有当前球洞的地图，暂时无法确认果岭周边情况。'
 greens=[o for o in h.get('objects',[]) if o.get('kind')=='green_center']
 if len(greens)!=1:return '地图缺少果岭参考点，暂时无法确认周边障碍。'
 g=greens[0];pos=fresh_position(s,now)
 if not pos:return '果岭左右要结合进攻方向判断，请先更新当前位置。'
 p=pos['value'];dx=(g['longitude']-p['longitude'])*math.cos(math.radians(g['latitude']));dy=g['latitude']-p['latitude'];length=math.hypot(dx,dy)
 if length*111000<10:return '当前距离果岭参考点太近，暂时无法稳定区分进攻方向上的左右前后。'
 fx,fy=dx/length,dy/length
 rows=[]
 for path in h.get('display_paths',[]):
  if path.get('kind') not in ('BunkerTrace','WaterTrace'):continue
  points=path.get('points',[])
  if len(points)<3:continue
  if min(haversine(g,v) for v in points)>60:continue
  # Bounding-box center avoids weighting a source path by its vertex density.
  center={'latitude':(min(v['latitude'] for v in points)+max(v['latitude'] for v in points))/2,'longitude':(min(v['longitude'] for v in points)+max(v['longitude'] for v in points))/2}
  x=(center['longitude']-g['longitude'])*111000*math.cos(math.radians(g['latitude']));y=(center['latitude']-g['latitude'])*111000
  lateral=x*fy-y*fx;forward=x*fx+y*fy
  side='右' if lateral>5 else '左' if lateral<-5 else ''
  depth='前' if forward<-5 else '后' if forward>5 else ''
  label=(side+depth+'侧') if side or depth else '附近'
  rows.append({'id':path.get('id'),'side':side,'depth':depth,'label':label,'kind':'沙坑' if path['kind']=='BunkerTrace' else '水体'})
 wanted_side='右' if '右' in text else '左' if '左' in text else None
 wanted_depth='前' if re.search(r'[左右]前|前侧|前方',text) else '后' if re.search(r'[左右]后|后侧|后方',text) else None
 kind='沙坑' if '沙坑' in text else '水体' if re.search(r'水|溪|河',text) else None
 matched=[r for r in rows if (not wanted_side or r['side']==wanted_side) and (not wanted_depth or r['depth']==wanted_depth) and (not kind or r['kind']==kind)]
 if matched:
  descriptions=list(dict.fromkeys(r['label']+'有'+r['kind'] for r in matched))
  return '按当前进攻方向，地图显示果岭'+ '，'.join(descriptions)+'。进攻时避开这些障碍，不追贴边旗位。'
 if rows:
  descriptions=list(dict.fromkeys(r['label']+'有'+r['kind'] for r in rows))
  return '地图暂不能确认你问的这个位置；目前显示果岭'+ '，'.join(descriptions)+'。'
 return '现有地图未能确认果岭周边的沙坑或水体分布，不能据此认定没有障碍。'

def position_changed(s,c,now):
 pos=fresh_position(s,now)
 if not pos:return True
 if pos['version']==c.get('position_version'):return False
 previous=c.get('position_point')
 # Old consultations without a coordinate anchor cannot safely compare movement.
 if not previous:return True
 return haversine(previous,pos['value'])>max(5,min(15,previous.get('accuracy_m',0)+pos['value']['accuracy_m']))
