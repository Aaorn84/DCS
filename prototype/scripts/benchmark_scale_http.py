"""Explicit write workload for an ISOLATED test deployment, never real user data."""
import argparse,json,statistics,time,urllib.request,urllib.error,uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone

def measure(base,users=8,turns=10):
 def request(path,body,token=None):
  req=urllib.request.Request(base.rstrip('/')+path,data=json.dumps(body).encode(),headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+token} if token else {})})
  try:
   with urllib.request.urlopen(req,timeout=40) as response:
    reply=json.load(response);timing=response.headers.get('Server-Timing','')
    if timing.startswith('app;dur='):reply['_benchmark_app_ms']=float(timing.split('=',1)[1])
    return response.status,reply
  except urllib.error.HTTPError as exc:return exc.code,json.load(exc)
 actors=[];prefix=uuid.uuid4().hex
 for user in range(users):
  status,reply=request('/auth/register',{'email':prefix+str(user)+'@load.example.test','password':'isolated-load-password-123'})
  if status!=200:raise RuntimeError('test account setup failed: '+str(status))
  actors.append({'token':reply['token'],'seq':0,'known':{}})
 def event(actor,word):
  actor['seq']+=1;n=str(actor['seq'])
  status,reply=request('/journey',dict(action='core_event',operation_id='load'+n,compact_view=True,known_sections=actor['known'],event=dict(type='message',event_id='load'+n,observed_at=datetime.now(timezone.utc).isoformat(),text=word)),actor['token'])
  if status==200:actor['known']=reply.get('journey_revisions',{})
  return status,reply
 for actor in actors:
  for word in ('可以记住','球友','好','好','260','160','偏右','跳过','东莞凤凰山（A+B蓝台演示）','蓝台','1','开始球局'):
   status,_=event(actor,word)
   if status!=200:raise RuntimeError('onboarding failed: '+str(status))
  from phoenix_demo import preview
  actor['seq']+=1;n=str(actor['seq'])
  status,_=request('/journey',dict(action='core_event',operation_id='load'+n,compact_view=True,event=dict(type='gps',event_id='load'+n,observed_at=datetime.now(timezone.utc).isoformat(),data=dict(preview(1)['positions']['tee'],simulation_source='map_click',simulation_position_action='move'))),actor['token'])
  if status!=200:raise RuntimeError('position failed: '+str(status))
 def play(actor):
  samples=[];codes={};app_samples=[]
  for n in range(turns):
   start=time.perf_counter();status,reply=event(actor,'这杆怎么打' if n%3 else '有没有保守方案');samples.append((time.perf_counter()-start)*1000);codes[str(status)]=codes.get(str(status),0)+1
   if '_benchmark_app_ms' in reply:app_samples.append(reply['_benchmark_app_ms'])
  return samples,codes,app_samples
 started=time.perf_counter()
 with ThreadPoolExecutor(max_workers=users) as executor:results=list(executor.map(play,actors))
 elapsed=time.perf_counter()-started;samples=sorted(x for result,_,_ in results for x in result);codes={}
 for _,counts,_ in results:
  for code,n in counts.items():codes[code]=codes.get(code,0)+n
 def summary(values):
  values=sorted(values);return {'samples':len(values),'p50_ms':round(statistics.median(values),3),'p95_ms':round(values[min(len(values)-1,int(len(values)*.95))],3)}
 cold=[items[0] for items,_,_ in results];warm=[x for items,_,_ in results for x in items[1:]]
 app_samples=[x for _,_,items in results for x in items]
 return {'application_handler':summary(app_samples) if app_samples else None,'cold_first_query':summary(cold),'warm_queries':summary(warm) if warm else None,'scope':'real HTTP, independent accounts and serialized turns per account; excludes ASR/TTS/rendering','users':users,'samples':len(samples),'status_counts':codes,'p50_ms':round(statistics.median(samples),3),'p95_ms':round(samples[min(len(samples)-1,int(len(samples)*.95))],3),'requests_per_second':round(len(samples)/elapsed,2)}
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--base-url',required=True);parser.add_argument('--users',type=int,default=8);parser.add_argument('--turns',type=int,default=10);parser.add_argument('--allow-test-writes',action='store_true');args=parser.parse_args()
 if not args.allow_test_writes:parser.error('requires --allow-test-writes; use only disposable test deployment')
 if not 1<=args.users<=100 or not 1<=args.turns<=1000:parser.error('workload out of range')
 print(json.dumps(measure(args.base_url,args.users,args.turns),indent=2))
