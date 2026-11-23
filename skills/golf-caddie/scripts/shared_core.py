"""Thin transport to the SAME TypeScript core bundled by the phone.
Bounded persistent worker pool per API process; no Python fallback.
"""
import atexit,json,os,select,shutil,subprocess,sys,threading,time
from collections import OrderedDict
from pathlib import Path
CORE_VERSION='1.6.0'
CORE_DATASET='shared-core-4'
SUPPORTED_CORES=('1.4.0','1.5.0',CORE_VERSION)

def _root():
 for parent in Path(__file__).resolve().parents:
  candidate=parent/'prototype/shared/core/worker.mjs'
  if candidate.is_file():return candidate
 raise RuntimeError('shared core source is missing')

def _node():
 configured=os.environ.get('CADDIE_NODE_BINARY')
 if configured:return configured
 found=shutil.which('node')
 if found:return found
 candidate=Path(sys.executable).resolve().parents[2]/'node/bin/node'
 if candidate.is_file():return str(candidate)
 raise RuntimeError('Node >=22.13 is required; configure CADDIE_NODE_BINARY')

class Runtime:
 def __init__(self):self.lock=threading.RLock();self.process=None;self.buffer=b'';self.pid=os.getpid();self.registered=OrderedDict()
 def close(self):
  with self.lock:
   if self.process:
    self.process.terminate()
    try:self.process.wait(timeout=2)
    except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
    for stream in (self.process.stdin,self.process.stdout):stream.close()
   self.process=None;self.buffer=b'';self.registered.clear()
 def cached(self,method,scope,package_factory,**fields):
  from round_state import StateError
  with self.lock:
   if self.process is None or self.process.poll() is not None:self.registered.clear()
   version=self.registered.get(scope)
   if version is None:
    package=package_factory();version=package.get('core_version');self.call('register_package',package_key=scope,package=package)
   try:result=self.call(method,_core_version=version,package_key=scope,**fields)
   except StateError as exc:
    if str(exc)!='shared package not cached':raise
    self.call('register_package',package_key=scope,package=package_factory());result=self.call(method,_core_version=version,package_key=scope,**fields)
   self.registered.pop(scope,None);self.registered[scope]=version
   while len(self.registered)>8:self.registered.popitem(last=False)
   return result
 def plan(self,scope,package_factory,state,intent=None):return self.cached('plan_cached',scope,package_factory,state=state,intent=intent or {})
 def call(self,method,**payload):
  from round_state import StateError
  source=payload.get('state') or payload.get('package') or payload.get('asset') or {}
  version=payload.pop('_core_version',source.get('core_version',CORE_VERSION))
  if version not in SUPPORTED_CORES:raise StateError('shared core version mismatch: unsupported pinned core version; preserve round data')
  data=json.dumps(dict(core_version=version,method=method,**payload),ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()+b'\n'
  if len(data)>16*1024*1024:raise StateError('shared core request too large')
  with self.lock:
   if self.pid!=os.getpid():self.process=None;self.buffer=b'';self.pid=os.getpid()
   if self.process is None or self.process.poll() is not None:
    self.close();self.process=subprocess.Popen([_node(),'--experimental-transform-types',str(_root())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,bufsize=0)
    os.set_blocking(self.process.stdin.fileno(),False)
   try:
    # A request is never automatically retried after worker failure.
    # Nothing is committed by this pure worker; the caller's transaction aborts.
    deadline=time.monotonic()+20
    offset=0
    while offset<len(data):
     remaining=deadline-time.monotonic()
     if remaining<=0 or not select.select([],[self.process.stdin],[],remaining)[1]:raise TimeoutError('shared core input timed out')
     try:offset+=os.write(self.process.stdin.fileno(),data[offset:])
     except BlockingIOError:continue
    while b'\n' not in self.buffer:
     remaining=deadline-time.monotonic()
     if remaining<=0 or not select.select([self.process.stdout],[],[],remaining)[0]:raise TimeoutError('shared core timed out')
     block=os.read(self.process.stdout.fileno(),65536)
     if not block:raise RuntimeError('shared core worker stopped')
     self.buffer+=block
     if len(self.buffer)>32*1024*1024:raise RuntimeError('shared core response too large')
    line,self.buffer=self.buffer.split(b'\n',1);reply=json.loads(line)
   except Exception:
    self.close();raise
   if not reply.get('ok'):
    if reply.get('kind')=='rule':raise StateError(reply['error'])
    raise RuntimeError(reply.get('error','shared core failed'))
   return reply['result']
class RuntimePool:
 def __init__(self,size=None,waiters=None,wait_seconds=2):
  from runtime_control import integer
  self.size=size or integer('CADDIE_CORE_WORKERS',2,1,16)
  self.max_waiters=integer('CADDIE_CORE_WAITERS',16,0,256) if waiters is None else waiters
  self.wait_seconds=wait_seconds;self.condition=threading.Condition();self.workers=[Runtime() for _ in range(self.size)];self.busy=set();self.waiting=0
 def index(self,scope):
  import hashlib
  return int.from_bytes(hashlib.sha256(scope.encode()).digest()[:8],'big')%self.size
 def run(self,method,*args,scope=None,**kw):
  from runtime_control import CapacityError
  preferred=self.index(scope) if scope is not None else None
  deadline=time.monotonic()+self.wait_seconds
  with self.condition:
   def available():return next((i for i in range(self.size) if i not in self.busy and (preferred is None or preferred==i)),None)
   idx=available()
   if idx is None:
    if self.waiting>=self.max_waiters:raise CapacityError('core queue full')
    self.waiting+=1
    try:
     while idx is None:
      remaining=deadline-time.monotonic()
      if remaining<=0:raise CapacityError('core queue timed out')
      self.condition.wait(remaining);idx=available()
    finally:self.waiting-=1
   self.busy.add(idx)
  try:return getattr(self.workers[idx],method)(*args,**kw)
  finally:
   with self.condition:self.busy.remove(idx);self.condition.notify_all()
 def warm(self):
  for worker in self.workers:worker.call('capabilities')
 def close(self):
  for worker in self.workers:worker.close()
_pool=RuntimePool()
# No child process is started until first use; WSGI workers must not preload it.
atexit.register(lambda:_pool.close())
def call(method,**payload):return _pool.run('call',method,**payload)
def plan(scope,package_factory,state,intent=None):return _pool.run('plan',scope,package_factory,state,intent,scope=scope)
def web_turn(scope,package_factory,state,event,context):return _pool.run('cached','web_event_cached',scope,package_factory,state=state,event=event,context=context,scope=scope)
def create_local_round(package):return call('create',package=package)
def apply_local_command(state,event):return call('apply',state=state,event=event)
def totals(state):return call('totals',state=state)
