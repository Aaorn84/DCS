"""User-selected trusted tee club; preference, never a safety guarantee or shot."""
import re
from club_selection import selection

def handle(state,text,event_id):
 j=state['journey'];clean=re.sub(r'[，,。！!\s]','',text)
 clean=clean.replace('保底球杆','保底开球杆')
 if clean in ('保底开球杆设置','设置我的保底开球杆','更换保底开球杆','修改保底开球杆'):
  clean='设置保底开球杆'
 if clean in ('取消保底开球杆','清除保底开球杆'):
  j.setdefault('profile',{}).pop('fairway_finder',None);j['profile'].pop('trusted_tee_club',None);j.pop('finder_pending',None)
  return '已取消保底开球杆设置。'
 pending=j.get('finder_pending');rid=(j.get('round') or {}).get('id')
 if pending and pending.get('round')!=rid:j.pop('finder_pending',None);pending=None
 m=re.fullmatch(r'(?:设置|我的|把)?保底开球杆(?:设为|是|用|选)?(.*)',clean)
 if not m and not pending:return None
 body=m[1] if m else clean
 if not body:
  j['finder_pending']={'round':rid,'phase':'club'}
  return '哪支杆是你最信任的保底开球杆？可以选一号木、球道木、铁木杆或铁杆；随时可以更换或取消。'
 if body in ('跳过','取消','不知道'):
  j.pop('finder_pending',None);return '这次先不设置保底开球杆。'
 unit=j.get('profile',{}).get('units',{}).get('value','码')
 if pending and pending.get('phase')=='carry':
  distance=re.fullmatch(r'(?:Carry|carry)?(\d{2,3})(码|米)?',body)
  if distance and 10<=int(distance[1])<=400:
   key=pending['key'];j.setdefault('profile',{})[key]=dict(value=dict(distance=int(distance[1]),units=distance[2] or unit,distance_type='carry',club_name=pending['label']),source='user_report',event_id=event_id)
   j.pop('finder_pending',None);return '已补充保底开球杆Carry。之后会用它比较保守路线，仍需核对落区和障碍。'
  return '这支保底开球杆的稳定Carry大概多少？不清楚可以跳过。'
 combined=re.fullmatch(r'(.+?)(?:Carry|carry|落地)?(\d{2,3})(码|米)?',body)
 chosen=selection(combined[1],hybrid=True,expanded=True) if combined else selection(body,hybrid=True,expanded=True)
 if combined and chosen:
  distance=int(combined[2])
  if not 10<=distance<=400:return '请确认这支保底开球杆的常态Carry距离。'
  j.setdefault('profile',{})[chosen['key']]=dict(value=dict(distance=distance,units=combined[3] or unit,distance_type='carry',club_name=chosen['label']),source='user_report',event_id=event_id)

 if not chosen and pending and pending.get('optional'):
  j.pop('finder_pending',None);return None
 if not chosen:return '请报保底开球杆的杆名，例如“5号木”或“4号铁”；也可以跳过。'
 j.setdefault('profile',{})['fairway_finder']=dict(value=dict(club_key=chosen['key'],club_name=chosen['label']),source='user_report',event_id=event_id)
 if j['profile'].get(chosen['key'],{}).get('value',{}).get('distance_type')!='carry':
  j['finder_pending']=dict(round=rid,phase='carry',key=chosen['key'],label=chosen['label'])
  return '已将'+chosen['label']+'设为保底开球杆。它稳定Carry大概多少？不清楚可以跳过。'
 j.pop('finder_pending',None)
 return '已将'+chosen['label']+'设为保底开球杆。之后会优先用它比较保守路线，但不会把它当作一定安全，也不记作本杆选杆或击球。'
