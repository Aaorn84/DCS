"""Localhost HTTP comparison. No browser rendering, ASR or TTS timings."""
import json,threading,tempfile,time,urllib.request,sys
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/api'))
from server import make_server
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from testing.database import TestDatabase

def measure():
 with TestDatabase() as database:
  server=make_server(database.url,port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base='http://127.0.0.1:'+str(server.server_port);result={}
  try:
   for action in ('core_event',):
    token=None;n=0;known={}
    def request(path,body):
     req=urllib.request.Request(base+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
     with urllib.request.urlopen(req) as response:return json.load(response)
    def event(kind,**data):
     nonlocal n,known
     n+=1;r=request('/journey',dict(action=action,operation_id='bench'+str(n),compact_view=True,known_sections=known,event=dict(type=kind,event_id='bench'+str(n),observed_at=datetime.now(timezone.utc).isoformat(),**data)));known=r.get('journey_revisions',{});return r
    token=request('/auth/register',dict(email=action+'@example.test',password='password-12345'))['token']
    for word in ('可以记住','球友','好','好','260','160','偏右','跳过','东莞凤凰山（A+B蓝台演示）','蓝台','1'):event('message',text=word)
    begin=time.perf_counter();r=event('message',text='开始球局');start_ms=(time.perf_counter()-begin)*1000
    from phoenix_demo import preview
    point=preview(1)['positions']['tee'];event('gps',data=dict(point,simulation_source='map_click',simulation_position_action='move'))
    samples=[]
    for _ in range(30):
     begin=time.perf_counter();r=event('message',text='这杆怎么打');samples.append((time.perf_counter()-begin)*1000)
    ordered=sorted(samples);result[action]=dict(samples=len(samples),round_start_ms=round(start_ms,3),first_plan_ms=round(samples[0],3),p50_ms=round(ordered[len(ordered)//2],3),p95_ms=round(ordered[int(len(ordered)*.95)],3),shared_core=r['result'].get('shared_core',False))
  finally:server.shutdown();server.server_close();thread.join()
 return result
if __name__=='__main__':print(json.dumps(dict(environment='darwin arm64 Python3.12 + Node24, localhost HTTP, isolated PostgreSQL, Phoenix hole1, 30 queries per mode, compact views; excludes browser rendering/ASR/TTS',results=measure()),ensure_ascii=False,indent=2))
