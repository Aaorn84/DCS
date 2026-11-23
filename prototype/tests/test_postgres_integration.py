"""Real PostgreSQL contract tests. CI provisions a disposable service/database."""
from testing.database import TestDatabase
import os,unittest,uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from services.api.server import Store,Engine,Problem
from round_state import Conflict,canonical
from shared_core import CORE_VERSION
from offline_sync import prepare,synchronize,row,setup,AGGREGATE

class PostgresIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.database=TestDatabase();self.url=self.database.url;self.store=Store(self.url)
  self.alice=self.store.auth({'email':uuid.uuid4().hex+'@example.test','password':'test-password-123'},True)
  self.bob=self.store.auth({'email':uuid.uuid4().hex+'@example.test','password':'test-password-123'},True)
  self.owner=self.alice['user']['id']
 def tearDown(self):self.database.cleanup()
 def op(self,**kw):return dict(operationId='op',kind='club',id='driver',baseVersion=0,data={'name':'一号木','distance':240,'distanceType':'carry'},**kw)
 def ready(self):
  e=Engine(self.url,self.owner);setup(e);e.create(AGGREGATE);s=e.state(AGGREGATE)
  from phoenix_demo import course
  s['journey']={'stage':'ready','round':{'id':uuid.uuid4().hex,'course':'dongguan-phoenix-ab-blue-demo','tee':'蓝Tee','start_hole':1,'finished':False},'profile':{},'quiet':False,'memory_allowed':False,'number':1,'history':[]}
  s['facts']['context.course_snapshot']={'value':'map','valid':True};s['evidence']['map']={'data':course()}
  e.db.execute('UPDATE rounds SET state=%s WHERE owner=%s AND id=%s',(canonical(s),self.owner,AGGREGATE));return e
 def test_parallel_record_retry_is_single_commit_and_owner_scoped(self):
  with ThreadPoolExecutor(max_workers=4) as threads:results=list(threads.map(lambda _:self.store.apply(self.owner,self.op()),range(8)))
  self.assertTrue(all(x==results[0] for x in results));self.assertEqual(1,len(self.store.snapshot(self.owner)));self.assertEqual([],self.store.snapshot(self.bob['user']['id']))
  self.assertEqual(1,self.store.apply(self.bob['user']['id'],self.op())['version'])
 def test_parallel_offline_retry_commits_one_cursor_and_one_event(self):
  e=self.ready()
  try:p=prepare(e,{'device_id':'postgres-device','expected_version':0,'local_engine_version':1,'core_version':CORE_VERSION})
  finally:e.close()
  at=datetime.now(timezone.utc).isoformat();command=dict(v=1,semantics=2,id='start',at=at,expected_revision=0,command='start',data={})
  body=dict(p['offline'],device_id='postgres-device',events=[dict(seq=1,event=dict(type='local_round_command',event_id='start',observed_at=at,data=command))])
  def send(_):
   engine=Engine(self.url,self.owner)
   try:return synchronize(engine,body)
   except Conflict:return 'conflict'  # a simultaneous stale read is safe to retry
   finally:engine.close()
  with ThreadPoolExecutor(max_workers=4) as threads:answers=list(threads.map(send,range(8)))
  self.assertTrue(any(x!='conflict' for x in answers));self.assertNotEqual('conflict',send(0))
  e=Engine(self.url,self.owner)
  try:
   self.assertEqual(1,row(e)['cursor']);self.assertEqual(1,e.state(AGGREGATE)['version'])
   self.assertEqual(1,e.db.execute('SELECT count(*) FROM commands WHERE owner=%s',(self.owner,)).fetchone()[0])
   other=Engine(self.url,self.bob['user']['id']);other.create(AGGREGATE)
   try:
    with self.assertRaises(Conflict):synchronize(other,body)
   finally:other.close()
  finally:e.close()
 def test_cross_connection_locks_do_not_block_other_accounts(self):
  a=Engine(self.url,self.owner);b=Engine(self.url,self.bob['user']['id'])
  try:
   a.db.begin();b.db.begin()
   b.db.execute('ROLLBACK');a.db.execute('ROLLBACK')
  finally:a.close();b.close()
 def test_wsgi_onboarding_and_local_strategy_use_the_postgres_projection(self):
  import io,json
  from wsgi import Application
  from phoenix_demo import preview
  app=Application(self.url);token=self.alice['token'];sequence=0
  def request(path,body):
   raw=json.dumps(body).encode();status=[]
   env={'PATH_INFO':path,'REQUEST_METHOD':'POST','REMOTE_ADDR':'127.0.0.1','CONTENT_LENGTH':str(len(raw)),'HTTP_AUTHORIZATION':'Bearer '+token,'wsgi.input':io.BytesIO(raw)}
   reply=json.loads(b''.join(app(env,lambda s,h:status.append(s))))
   self.assertTrue(status[0].startswith('200'),reply);return reply
  def event(kind,**data):
   nonlocal sequence
   sequence+=1
   return request('/journey',dict(action='core_event',operation_id='pg'+str(sequence),event=dict(type=kind,event_id='pg'+str(sequence),observed_at=datetime.now(timezone.utc).isoformat(),**data)))
  for word in ('可以记住','球友','好','好','260','160','偏右','跳过','东莞凤凰山（A+B蓝台演示）','蓝台','1'):event('message',text=word)
  event('message',text='开始球局');event('gps',data=dict(preview(1)['positions']['tee'],simulation_source='map_click',simulation_position_action='move'))
  answer=event('message',text='这杆怎么打');self.assertTrue(answer['result']['shared_core']);self.assertIn('一号木',answer['result']['text'])
 def test_runtime_role_requires_no_schema_privileges(self):
  import psycopg
  from psycopg import sql
  from urllib.parse import urlsplit,urlunsplit
  from database import close_pools
  # Provision all tables with the test schema owner, then use a distinct DML-only login.
  e=self.ready();e.close();role='runtime_'+uuid.uuid4().hex;password=uuid.uuid4().hex
  parts=urlsplit(self.url);address=parts.netloc.rsplit('@',1)[-1]
  url=urlunsplit((parts.scheme,role+':'+password+'@'+address,parts.path,parts.query,parts.fragment))
  with psycopg.connect(self.url,autocommit=True) as admin:
   admin.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
   try:
    admin.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(self.database.schema),sql.Identifier(role)))
    admin.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA {} TO {}').format(sql.Identifier(self.database.schema),sql.Identifier(role)))
    store=Store(url);account=store.auth({'email':uuid.uuid4().hex+'@example.test','password':'test-password-123'},True)
    engine=Engine(url,account['user']['id']);engine.create(AGGREGATE)
    try:
     setup(engine)
     answer=engine.command(AGGREGATE,'runtime','application_event',dict(type='resume',event_id='runtime',observed_at=datetime.now(timezone.utc).isoformat()),expected_version=0)
     self.assertEqual(1,answer['version'])
    finally:engine.close()
   finally:
    close_pools()
    admin.execute(sql.SQL('REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA {} FROM {}').format(sql.Identifier(self.database.schema),sql.Identifier(role)))
    admin.execute(sql.SQL('REVOKE USAGE ON SCHEMA {} FROM {}').format(sql.Identifier(self.database.schema),sql.Identifier(role)))
    admin.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
 def test_file_database_configuration_is_rejected_without_creating_a_file(self):
  import tempfile
  from pathlib import Path
  from database import connect
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'database-file'
   with self.assertRaisesRegex(ValueError,'PostgreSQL'):connect(str(path))
   with self.assertRaisesRegex(ValueError,'PostgreSQL'):Store(str(path))
   self.assertFalse(path.exists())
 def test_schema_is_provisioned_explicitly_and_runtime_never_creates_missing_tables(self):
  import psycopg
  from psycopg import sql
  from database import connect,ensure_schema,close_pools
  close_pools(self.url)
  with psycopg.connect(self.url,autocommit=True) as admin:admin.execute('DROP TABLE operations')
  db=connect(self.url)
  try:
   with self.assertRaises(psycopg.errors.UndefinedTable):ensure_schema(db)
  finally:db.close()
  with psycopg.connect(self.url,autocommit=True) as admin:self.assertIsNone(admin.execute("SELECT to_regclass('operations')").fetchone()[0])
