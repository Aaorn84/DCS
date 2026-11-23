from testing.database import TestDatabase
import io,json,os,tempfile,threading,time,unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from services.api.server import Engine,Store
from database import CapacityError
from shared_core import RuntimePool
from traffic import Limits,RateLimited
from wsgi import Application

class ScaleFoundationTests(unittest.TestCase):
 def test_pool_has_parallel_capacity_and_rejects_excess_waiters(self):
  pool=RuntimePool(size=2,waiters=0);entered=threading.Barrier(3);release=threading.Event()
  def work():entered.wait(timeout=2);release.wait(timeout=2);return 'ok'
  for worker in pool.workers:worker.work=work
  try:
   with ThreadPoolExecutor(max_workers=2) as threads:
    tasks=[threads.submit(pool.run,'work') for _ in range(2)];entered.wait(timeout=2)
    with self.assertRaises(CapacityError):pool.run('work')
    release.set();self.assertEqual(['ok','ok'],[t.result() for t in tasks])
  finally:release.set();pool.close()
 def test_wait_timeout_does_not_leak_pool_slots(self):
  pool=RuntimePool(size=1,waiters=1,wait_seconds=.02);pool.busy.add(0)
  with self.assertRaises(CapacityError):pool.run('call','capabilities')
  self.assertEqual(0,pool.waiting);pool.busy.clear()
  self.assertTrue(pool.run('call','capabilities'));self.assertEqual(set(),pool.busy);pool.close()
 def test_local_limits_are_bounded_expire_and_separate_accounts(self):
  now=[0];limits=Limits(slots=2,clock=lambda:now[0]);limits.check('account','a',1)
  with self.assertRaises(RateLimited):limits.check('account','a',1)
  limits.check('account','b',1)
  with self.assertRaises(CapacityError):limits.check('account','c',1)
  now[0]=61;limits.check('account','c',1);self.assertLessEqual(len(limits.entries),2)
 def test_wsgi_admission_production_guards_and_bounded_metrics(self):
  with TestDatabase() as database:
   with self.assertRaisesRegex(ValueError,'PostgreSQL'):Application('/not-a-postgres-url',production=True)
   with self.assertRaisesRegex(ValueError,'Redis'):Application('postgresql://unused',production=True)
   app=Application(database.url,concurrency=1)
   def request(path='/health',method='GET',body=b'',auth=None):
    status=[];headers=[];env={'PATH_INFO':path,'REQUEST_METHOD':method,'REMOTE_ADDR':'127.0.0.1','CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body)}
    if auth:env['HTTP_AUTHORIZATION']=auth
    result=b''.join(app(env,lambda s,h:(status.append(s),headers.extend(h))))
    return int(status[0].split()[0]),json.loads(result) if result else {},dict(headers)
   self.assertEqual(200,request()[0]);app.admission.acquire()
   try:self.assertEqual(200,request()[0]);self.assertEqual(503,request('/records')[0])
   finally:app.admission.release()
   self.assertEqual(413,request('/auth/login','POST',b'x'*65537)[0])
   self.assertEqual(401,request('/records')[0]);self.assertEqual(401,request('/metrics')[0])
   with patch.dict(os.environ,{'CADDIE_METRICS_TOKEN':'test-secret'}):
    status,data,_=request('/metrics',auth='Bearer test-secret');self.assertEqual(200,status);self.assertIn('/records:503',data['requests'])
   for n in range(5):request('/random'+str(n))
   self.assertTrue(all('random' not in key for key in app.counts))
 def test_auth_rate_limit_precedes_password_work(self):
  with TestDatabase() as database,patch.dict(os.environ,{'CADDIE_AUTH_PER_MINUTE':'1'}):
   app=Application(database.url)
   def request():
    statuses=[];env={'PATH_INFO':'/auth/login','REQUEST_METHOD':'POST','REMOTE_ADDR':'127.0.0.1','CONTENT_LENGTH':'2','wsgi.input':io.BytesIO(b'{}')}
    app(env,lambda s,h:statuses.append(s));return statuses[0]
   self.assertTrue(request().startswith('400'));self.assertTrue(request().startswith('429'))
 def test_computation_does_not_hold_a_write_lock_and_conflicting_commit_is_rejected(self):
  with TestDatabase() as database:
   db=database.url;Store(db);engine=Engine(db,'a');engine.create('r');entered=threading.Event();release=threading.Event()
   # Engine connections must stay on their own thread.
   def reducer(state,*args):
    entered.set();release.wait(timeout=3);state['version']=1;return {'ok':True}
   def slow():
    local=Engine(db,'a')
    try:
     with patch('round_state.reduce',side_effect=reducer):return local.command('r','one','application_event',{},expected_version=0)
    finally:local.close()
   try:
    with ThreadPoolExecutor(max_workers=1) as threads:
     future=threads.submit(slow);self.assertTrue(entered.wait(timeout=2))
     other=Engine(db,'b');other.create('r');other.close()
     # Commit a newer state while the first request is computing.
     engine.db.begin();engine.db.execute('UPDATE rounds SET state=%s WHERE owner=%s AND id=%s',('{"version":1,"facts":{},"evidence":{}}','a','r'));engine.db.execute('COMMIT')
     release.set()
     from round_state import Conflict
     with self.assertRaises(Conflict):future.result()
     self.assertEqual(0,engine.db.execute('SELECT count(*) FROM commands').fetchone()[0])
   finally:release.set();engine.close()
 def test_redis_limits_are_shared_between_instances(self):
  url=os.environ.get('CADDIE_TEST_REDIS_URL')
  if not url:self.skipTest('disposable Redis URL not configured')
  import uuid
  first=Limits(url);second=Limits(url);identity=uuid.uuid4().hex
  first.check('test',identity,1)
  with self.assertRaises(RateLimited):second.check('test',identity,1)
 def test_liveness_bypasses_redis_database_and_admission_but_readiness_checks_dependencies(self):
  with TestDatabase() as database:
   app=Application(database.url,concurrency=1)
   def request(path):
    statuses=[];body=b''.join(app({'PATH_INFO':path,'REQUEST_METHOD':'GET','REMOTE_ADDR':'127.0.0.1','wsgi.input':io.BytesIO()},lambda s,h:statuses.append(s)))
    return int(statuses[0].split()[0]),json.loads(body)
   with patch.object(app.limits,'check',side_effect=CapacityError('Redis unavailable')) as limit,patch.object(app.store,'connect',side_effect=CapacityError('DB unavailable')) as db:
    app.admission.acquire()
    try:self.assertEqual((200,True),(request('/health')[0],request('/health')[1]['ok']))
    finally:app.admission.release()
    self.assertEqual(503,request('/ready')[0]);limit.assert_not_called();db.assert_called_once()
   fake=type('Redis',(),{'ping':lambda self:(_ for _ in ()).throw(ConnectionError('Redis unavailable'))})()
   app.limits.redis=fake
   with patch.object(app.limits,'check',side_effect=AssertionError('business limit called')):
    self.assertEqual(200,request('/health')[0]);self.assertEqual(503,request('/ready')[0])
 def test_retry_after_committed_response_failure_does_not_commit_a_second_event(self):
  from datetime import datetime,timezone
  import round_view
  with TestDatabase() as database:
   app=Application(database.url)
   account=app.store.auth({'email':'receipt@example.test','password':'test-password-123'},True)
   body=json.dumps({'action':'core_event','operation_id':'original-operation','expected_version':0,'event':{'type':'resume','event_id':'original-event','observed_at':datetime.now(timezone.utc).isoformat()}}).encode()
   original=round_view.view;calls=[0]
   def response_fails_once(state):
    rendered=original(state);calls[0]+=1
    if calls[0]==1:raise RuntimeError('simulated response rendering failure after commit')
    return rendered
   def request():
    status=[];reply=b''.join(app({'PATH_INFO':'/journey','REQUEST_METHOD':'POST','REMOTE_ADDR':'127.0.0.1','HTTP_AUTHORIZATION':'Bearer '+account['token'],'CONTENT_LENGTH':str(len(body)),'wsgi.input':io.BytesIO(body)},lambda s,h:status.append(s)))
    return int(status[0].split()[0]),json.loads(reply)
   with patch.object(round_view,'view',side_effect=response_fails_once):
    self.assertEqual(500,request()[0]);self.assertEqual(200,request()[0])
   engine=Engine(database.url,account['user']['id'])
   try:
    self.assertEqual(1,engine.state('companion-journey')['version'])
    self.assertEqual(1,engine.db.execute('SELECT count(*) FROM commands WHERE owner=%s',(account['user']['id'],)).fetchone()[0])
   finally:engine.close()
