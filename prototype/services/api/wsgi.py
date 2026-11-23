"""Production WSGI entry: shared routes, bounded work, no second domain engine."""
import io,ipaddress,json,os,threading,time,uuid
from collections import Counter
from http import HTTPStatus
from types import SimpleNamespace
from wsgiref.headers import Headers
from server import Handler,Store,Problem,Engine,health_snapshot
from database import CapacityError,integer,require_url
from traffic import Limits,RateLimited

class Application:
 def __init__(self,database,*,production=False,redis_url=None,concurrency=None):
  require_url(database)
  if production and not redis_url:raise ValueError('production requires shared Redis rate limits')
  if production and len(os.environ.get('CADDIE_METRICS_TOKEN',''))<32:raise ValueError('production requires a metrics token of at least 32 characters')
  self.production=production;self.store=Store(database);self.limits=Limits(redis_url)
  self.admission=threading.BoundedSemaphore(concurrency or integer('CADDIE_HTTP_INFLIGHT',16,1,256))
  self.lock=threading.Lock();self.counts=Counter();self.latencies=Counter()
  self.trusted=[ipaddress.ip_network(x.strip()) for x in os.environ.get('CADDIE_TRUSTED_PROXIES','').split(',') if x.strip()]
  engine=Engine(database,'__startup__')
  try:
   from offline_sync import setup
   setup(engine)
  finally:engine.close()
  from shared_core import _pool
  _pool.warm()
 def client(self,environ):
  remote=environ.get('REMOTE_ADDR','unknown')
  try:
   if any(ipaddress.ip_address(remote) in network for network in self.trusted):
    candidate=environ.get('HTTP_X_REAL_IP','')
    if candidate:remote=str(ipaddress.ip_address(candidate))
  except ValueError:pass
  return remote
 def __call__(self,environ,start_response):
  started=time.monotonic();request_id=uuid.uuid4().hex;admitted=False;code=200;extra=[]
  path=environ.get('PATH_INFO','');method=environ.get('REQUEST_METHOD','GET')
  try:
   if path=='/health' and method=='GET':
    data=health_snapshot('production' if self.production else 'test')
   elif path=='/metrics':
    token=os.environ.get('CADDIE_METRICS_TOKEN','')
    import hmac
    if not token or not hmac.compare_digest(environ.get('HTTP_AUTHORIZATION',''),'Bearer '+token):raise Problem(401,'unauthorized')
    with self.lock:data={'requests':dict(self.counts),'latency_buckets_ms':dict(self.latencies)}
   else:
    admitted=self.admission.acquire(blocking=False)
    if not admitted:raise CapacityError('request capacity exceeded')
    peer=self.client(environ)
    if not (path=='/ready' and method=='GET'):
     self.limits.check('ip',peer,integer('CADDIE_IP_PER_MINUTE',300,1,100000))
    if path in ('/auth/register','/auth/login'):
     self.limits.check('auth',peer,integer('CADDIE_AUTH_PER_MINUTE',10,1,1000))
    if method not in ('GET','POST','OPTIONS'):raise Problem(405,'method not allowed')
    headers=Headers([(k[5:].replace('_','-').title(),v) for k,v in environ.items() if k.startswith('HTTP_')])
    headers['Content-Length']=environ.get('CONTENT_LENGTH','0') or '0'
    route=Handler.__new__(Handler);route.command=method;route.path=path;route.headers=headers
    route.rfile=environ.get('wsgi.input',io.BytesIO());route.server=SimpleNamespace(store=self.store,limits=self.limits)
    if path=='/ready' and method=='GET':
     try:
      with self.store.connect() as db:db.execute('SELECT 1')
      from shared_core import call
      call('capabilities')
      if self.limits.redis:self.limits.redis.ping()
     except Exception as exc:raise CapacityError('readiness dependency unavailable') from exc
     data={'ok':True}
    elif method=='OPTIONS':data={};code=204
    else:data=route.route()
  except RateLimited:code=429;data={'error':'请求较频繁，请稍后重试'};extra=[('Retry-After','60')]
  except CapacityError:code=503;data={'error':'服务繁忙，请保留当前操作后重试'};extra=[('Retry-After','1')]
  except Problem as exc:code=exc.status;data={'error':exc.message,**exc.extra}
  except Exception as exc:
   import psycopg
   transient=isinstance(exc,(TimeoutError,psycopg.OperationalError,psycopg.errors.QueryCanceled,psycopg.errors.LockNotAvailable))
   code=503 if transient else 500;data={'error':'服务暂时不可用'}
   if transient:extra=[('Retry-After','1')]
   # Never log request bodies, tokens, DSNs or raw exception messages.
   import logging
   logging.getLogger('caddie').error('request_failed id=%s category=%s',request_id,type(exc).__name__)
  finally:
   if admitted:self.admission.release()
  elapsed=(time.monotonic()-started)*1000
  known=path if path in ('/courses','/offline-rounds','/health','/ready','/journey','/international','/records','/sync','/chat','/auth/login','/auth/register','/auth/logout','/metrics') else 'other'
  bucket=next((str(n) for n in (5,10,25,50,100,250,500,1000,5000) if elapsed<=n),'inf')
  with self.lock:self.counts[known+':'+str(code)]+=1;self.latencies[bucket]+=1
  raw=b'' if code==204 else json.dumps(data,ensure_ascii=False,allow_nan=False).encode()
  response_headers=[('Content-Type','application/json; charset=utf-8'),('Content-Length',str(len(raw))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),('X-Request-ID',request_id),('Server-Timing','app;dur='+str(round(elapsed,3)))]+extra
  origin=environ.get('HTTP_ORIGIN','')
  if origin and origin in os.environ.get('CADDIE_CORS_ORIGINS','').split(','):
   response_headers.extend([('Access-Control-Allow-Origin',origin),('Vary','Origin'),('Access-Control-Allow-Headers','Authorization, Content-Type'),('Access-Control-Allow-Methods','GET, POST, OPTIONS')])
  start_response(str(code)+' '+HTTPStatus(code).phrase,response_headers);return [raw]

def create_app():
 database=os.environ.get('CADDIE_DATABASE_URL')
 if not database:raise ValueError('CADDIE_DATABASE_URL required')
 return Application(database,production=os.environ.get('CADDIE_ENV','production')=='production',redis_url=os.environ.get('CADDIE_REDIS_URL'))
