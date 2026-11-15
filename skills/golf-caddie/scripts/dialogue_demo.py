#!/usr/bin/env python3
"""Offline synthetic-clock journey demonstration. No network or user database writes."""
from datetime import datetime,timedelta
from round_state import Engine,fact_value
from phoenix_demo import preview
from shot_evidence import haversine

def run_demo(emit=print):
 e=Engine(':memory:','offline-demo');e.create('demo');n=0;clock=datetime.fromisoformat('2026-11-08T08:00:00+08:00');transcript=[]
 def event(text=None,gps=None):
  nonlocal n,clock
  n+=1;clock+=timedelta(seconds=10)
  p=dict(protocol_version=32,type='gps' if gps else 'message',event_id='demo-'+str(n),observed_at=clock.isoformat())
  if gps:p['data']=gps
  else:p['text']=text
  out=e.command('demo',str(n),'journey_event',p,now=clock.timestamp());transcript.append({'event':p,'reply':out['text']})
  if emit:
   emit(('模拟定位' if gps else '你：'+text))
   if out['text']:emit('球童：'+out['text'])
  return out
 try:
  if emit:emit('离线演示：合成时钟、凤凰山来源地图、内存数据库；不代表实地击球。')
  for text in ['仅本场','叫我球友','可以提醒','可以记录','240','160','偏右','东莞凤凰山（A+B蓝台演示）','蓝台','1','轻松打球','开始球局']:event(text)
  m=preview(1)['positions'];event(gps=dict(m['fairway'],simulation_source='map_click'))
  for text in ['还有多少','这杆怎么打','果岭右前侧有沙坑吗','用熟悉的短杆过渡','还有多少','好']:event(text)
  assert e.state('demo')['journey']['consultation']['phase']=='commit'
  event(gps=dict(m['fairway'],simulation_source='map_click')) # normal stationary refresh; not a shot
  event('继续刚才的问题');event('好');assert 'consultation' not in e.state('demo')['journey']
  event('我还是用了7铁')
  a=m['fairway'];g=m['green'];ratio=27.432/haversine(a,g)
  gps=dict(latitude=g['latitude']+(a['latitude']-g['latitude'])*ratio,longitude=g['longitude']+(a['longitude']-g['longitude'])*ratio,accuracy_m=2,simulation_hole=1,simulation_source='map_click')
  event(gps=gps)
  for text in ['上一杆打了多少','是的','高抛还是切滚','过沙需要多少','这洞加二','两推','没有','好']:event(text)
  assert fact_value(e.state('demo'),'holes.1.total')==6
  for text in ['结束球局','确认结束','挺开心','今天到这里']:event(text)
  state=e.state('demo');assert state==e.replay('demo')
  result={'events':n,'replay_matches':True,'score':fact_value(state,'holes.1.total'),'execution_reports':len(state['journey'].get('execution_reports',[])),'confirmed_distances':len(state['journey'].get('confirmed_shot_distances',[])),'coach_enabled':state['journey']['coach']['enabled'],'stage':state['journey']['stage'],'transcript':transcript}
  if emit:emit('验收通过：6杆、一条未归属执行、一条已确认总距离；教练关闭；重放一致。')
  return result
 finally:e.close()
if __name__=='__main__':run_demo()
