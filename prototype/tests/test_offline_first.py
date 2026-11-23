"""Advance download and offline-origin rounds: real HTTP/PostgreSQL/shared core."""
import hashlib,json,os,subprocess,threading,unittest,urllib.request,urllib.error
from datetime import datetime,timezone
from pathlib import Path
from testing.database import TestDatabase
from services.api.server import make_server,Engine
from shared_core import call,CORE_VERSION,_node
class OfflineFirstTests(unittest.TestCase):
 def setUp(self):
  self.db=TestDatabase();self.server=make_server(self.db.url,port=0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
  self.a=self.server.store.auth({'email':'a@example.test','password':'test-password-123'},True);self.b=self.server.store.auth({'email':'b@example.test','password':'test-password-123'},True)
 def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.db.cleanup()
 def request(self,path,body=None,token=None):
  req=urllib.request.Request(self.base+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+(token or self.a['token'])})
  try:
   with urllib.request.urlopen(req) as response:return response.status,json.load(response)
  except urllib.error.HTTPError as error:return error.code,json.load(error)
 def seed(self,rid='offline-round-123',token=None):
  status,catalog=self.request('/courses',token=token);self.assertEqual(200,status);course=catalog['courses'][0]
  status,download=self.request('/courses',{'course_id':course['course_id'],'tee':course['tees'][0],'include_personal':True},token);self.assertEqual(200,status,download)
  round=dict(id=rid,course=course['course_id'],tee=course['tees'][0],start_hole=10,started_at=datetime.now(timezone.utc).isoformat())
  setup=dict(memory_allowed=True,patch={'carries':{'一号木':{'low':240,'high':240}},'finder':'5号木'})
  wire=call('offline_package_wire',asset=download['asset']['package'],context=json.loads(download['context']['payload_json']),setup=setup,round=round);pack=wire['package']
  from round_state import canonical
  registration=dict(action='register',round_id=rid,device_id='offline-device-1',core_version=CORE_VERSION,asset_sha256=download['asset']['sha256'],context_sha256=download['context']['sha256'],setup=setup,round=round,package_sha256=hashlib.sha256(wire['payload_json'].encode()).hexdigest())
  return registration,pack
 def test_download_before_questionnaire_then_offline_full_round_and_later_sync(self):
  script=Path(__file__).with_name('fixtures')/'offline_first_flow.mjs'
  result=subprocess.run([_node(),'--experimental-transform-types',str(script)],input=json.dumps(dict(base=self.base,token=self.a['token'])),text=True,capture_output=True,timeout=40,cwd=Path(__file__).resolve().parents[2])
  self.assertEqual(0,result.returncode,result.stderr);data=json.loads(result.stdout);self.assertEqual(0,data['offline_network_requests']);self.assertEqual(72,data['totals']['total']);self.assertEqual(72,data['server_totals']['confirmed_subtotal'])
  e=Engine(self.db.url,self.a['user']['id'])
  try:
   self.assertEqual(data['events']+1,e.db.execute('SELECT count(*) FROM commands WHERE owner=%s',(e.owner,)).fetchone()[0])
   self.assertIsNone(e.db.execute('SELECT state FROM rounds WHERE owner=%s AND id=%s',(e.owner,'companion-journey')).fetchone())
  finally:e.close()
 def test_register_is_idempotent_and_cannot_replace_another_device_or_package(self):
  body,pack=self.seed();status,first=self.request('/offline-rounds',body);self.assertEqual(200,status,first)
  self.assertEqual((200,first),self.request('/offline-rounds',body))
  self.assertEqual(409,self.request('/offline-rounds',dict(body,device_id='other-device'))[0])
  self.assertEqual(400,self.request('/offline-rounds',dict(body,package_sha256='wrong'))[0])
  self.assertEqual(400,self.request('/offline-rounds',body,self.b['token'])[0])
 def test_two_devices_can_create_distinct_rounds_without_overwriting_current_web_round(self):
  engine=Engine(self.db.url,self.a['user']['id']);engine.create('companion-journey');before=engine.state('companion-journey')
  try:
   first,_=self.seed('offline-round-one');second,_=self.seed('offline-round-two');second['device_id']='offline-device-2'
   for body in (first,second):self.assertEqual(200,self.request('/offline-rounds',body)[0])
   self.assertEqual(before,engine.state('companion-journey'))
   self.assertEqual(2,engine.db.execute('SELECT count(*) FROM native_rounds WHERE owner=%s',(engine.owner,)).fetchone()[0])
  finally:engine.close()
 def test_history_comparison_uses_previous_native_round_and_postgame_retry_keeps_original_context(self):
  from unittest.mock import patch
  results=[]
  for _ in range(2):
   script=Path(__file__).with_name('fixtures')/'offline_first_flow.mjs'
   result=subprocess.run([_node(),'--experimental-transform-types',str(script)],input=json.dumps(dict(base=self.base,token=self.a['token'])),text=True,capture_output=True,timeout=40,cwd=Path(__file__).resolve().parents[2])
   self.assertEqual(0,result.returncode,result.stderr);results.append(json.loads(result.stdout))
  self.assertIn('比本球场同Tee历史最好持平',results[1]['report'])
  engine=Engine(self.db.url,self.a['user']['id']);rid=results[1]['round_id']
  try:
   operation,payload,seq=engine.db.execute("SELECT command_id,payload,seq FROM commands WHERE owner=%s AND round_id=%s AND kind='native_postgame_event'",(engine.owner,'native-'+rid)).fetchone()
   lease,device,cursor=engine.db.execute('SELECT lease_id,device_id,cursor FROM offline_leases WHERE owner=%s AND aggregate_id=%s',(engine.owner,'native-'+rid)).fetchone()
   envelope={'action':'event','round_id':rid,'device_id':device,'lease_id':lease,'operation_id':operation,'expected_version':seq-1,'event':json.loads(payload)['event']}
   with patch('native_rounds.history_summary',side_effect=AssertionError('retry must use stored context')):
    status,reply=self.request('/offline-rounds',envelope);self.assertEqual(200,status,reply);self.assertEqual(results[1]['report'],reply['result']['text'])
   status,_=self.request('/offline-rounds',{'action':'release','round_id':rid,'device_id':device,'lease_id':lease,'cursor':cursor});self.assertEqual(200,status)
  finally:engine.close()

 def test_core14_checkpoint_continues_after_upgrade_syncs_and_releases_without_migration(self):
  from round_state import canonical
  import time
  engine=Engine(self.db.url,self.a['user']['id'])
  try:
   from course_downloads import asset
   from phoenix_demo import ID
   for core_version in ('1.4.0','1.5.0','1.6.0'):
    legacy=json.loads(json.dumps(asset(ID)['package']));legacy['core_version']=core_version;raw=canonical(legacy);digest=hashlib.sha256(raw.encode()).hexdigest()
    context={'asset_sha256':digest,'profile':{},'dispersion':{},'history_by_hole':{}};context_raw=canonical(context);context_digest=hashlib.sha256(context_raw.encode()).hexdigest()
    engine.db.execute('INSERT INTO course_packages VALUES(%s,%s,%s,%s,%s)',(digest,ID,core_version,raw,time.time()))
    engine.db.execute('INSERT INTO download_contexts VALUES(%s,%s,%s,%s,%s)',(engine.owner,context_digest,digest,context_raw,time.time()))
    for pre_synced in (False,True):
     script=Path(__file__).with_name('fixtures')/'versioned_resume_flow.mjs'
     data=dict(base=self.base,token=self.a['token'],asset=legacy,context=context,asset_sha256=digest,context_sha256=context_digest,pre_synced=pre_synced,core_version=core_version)
     result=subprocess.run([_node(),'--experimental-transform-types',str(script)],input=json.dumps(data),text=True,capture_output=True,timeout=45,cwd=Path(__file__).resolve().parents[2])
     self.assertEqual(0,result.returncode,result.stderr);reply=json.loads(result.stdout);self.assertEqual(core_version,reply['core_version']);self.assertEqual(73,reply['server_total']);self.assertEqual(1,reply['totals']['penalties'])
     self.assertEqual(reply['events'],engine.db.execute('SELECT count(*) FROM commands WHERE owner=%s AND round_id=%s',(engine.owner,'native-'+reply['round_id'])).fetchone()[0])
  finally:engine.close()
 def finish_registration(self,body,commands=(),at=None):
  at=at or body['round']['started_at'];code,reply=self.request('/offline-rounds',body);self.assertEqual(200,code,reply);lease=reply['offline']
  scope=dict(round_id=body['round_id'],device_id=body['device_id'],lease_id=lease['lease_id']);events=[]
  for seq,(kind,data) in enumerate([('start',{}),*commands,('request_finish',{}),('confirm_finish',{'confirmed':True})],1):
   event_id='cmd-'+str(seq);command=dict(v=1,semantics=2,id=event_id,at=at,expected_revision=seq-1,command=kind,data=data)
   events.append(dict(seq=seq,event=dict(type='local_round_command',event_id=event_id,observed_at=at,data=command)))
  code,reply=self.request('/offline-rounds',dict(scope,action='sync',sha256=lease['sha256'],events=events));self.assertEqual(200,code,reply)
  return scope,len(events)
 def with_round_time(self,body,value):
  body=json.loads(json.dumps(body));body['round']['started_at']=value
  engine=Engine(self.db.url,self.a['user']['id'])
  try:
   raw=engine.db.execute('SELECT payload FROM course_packages WHERE digest=%s',(body['asset_sha256'],)).fetchone()[0];context=engine.db.execute('SELECT payload FROM download_contexts WHERE owner=%s AND digest=%s',(engine.owner,body['context_sha256'])).fetchone()[0]
   wire=call('offline_package_wire',asset=json.loads(raw),context=json.loads(context),setup=body['setup'],round=body['round']);body['package_sha256']=hashlib.sha256(wire['payload_json'].encode()).hexdigest();return body
  finally:engine.close()
 def test_unfinished_native_release_is_rejected_and_old_premature_release_is_recoverable(self):
  body,_=self.seed('release-guard-round');code,reply=self.request('/offline-rounds',body);lease=reply['offline'];scope=dict(round_id=body['round_id'],device_id=body['device_id'],lease_id=lease['lease_id']);at=body['round']['started_at']
  def sync(seq,kind,data={}):
   event_id='guard-'+str(seq);command=dict(v=1,semantics=2,id=event_id,at=at,expected_revision=seq-1,command=kind,data=data)
   return self.request('/offline-rounds',dict(scope,action='sync',sha256=lease['sha256'],events=[dict(seq=seq,event=dict(type='local_round_command',event_id=event_id,observed_at=at,data=command))]))
  self.assertEqual(200,sync(1,'start')[0]);self.assertEqual(400,self.request('/offline-rounds',dict(scope,action='release',cursor=1))[0]);self.assertEqual(200,sync(2,'select_club',{'club':'7号铁'})[0])
  engine=Engine(self.db.url,self.a['user']['id'])
  try:engine.db.execute("UPDATE offline_leases SET status='released' WHERE owner=%s AND aggregate_id=%s",(engine.owner,'native-'+body['round_id']))
  finally:engine.close()
  recovery=dict(scope,action='resume_recording',cursor=2)
  self.assertEqual(409,self.request('/offline-rounds',dict(recovery,device_id='wrong-device'))[0])
  for _ in range(2):
   code,reply=self.request('/offline-rounds',recovery);self.assertEqual(200,code,reply);self.assertEqual('active',reply['offline']['status'])
  self.assertEqual(200,sync(3,'request_finish')[0]);self.assertEqual(200,sync(4,'confirm_finish',{'confirmed':True})[0]);self.assertEqual(200,self.request('/offline-rounds',dict(scope,action='release',cursor=4))[0]);self.assertEqual(400,self.request('/offline-rounds',dict(recovery,cursor=4))[0])
 def test_late_old_round_merges_fields_without_reverting_newer_carry_and_undo_removes_its_contribution(self):
  older,_=self.seed('older-personal-round');newer,_=self.seed('newer-personal-round')
  older=self.with_round_time(older,'2026-11-20T00:00:00Z');newer=self.with_round_time(newer,'2026-11-22T00:00:00Z')
  self.finish_registration(newer,[('set_club_carry',{'club':'7号铁','low':175,'high':175})])
  scope,count=self.finish_registration(older,[('set_club_carry',{'club':'7号铁','low':160,'high':160}),('set_club_purpose',{'club':'58度杆','use':'沙坑'})])
  from course_downloads import private_context,asset
  from phoenix_demo import ID
  engine=Engine(self.db.url,self.a['user']['id'])
  try:
   profile=private_context(engine,ID,'蓝Tee',asset(ID)['package']['course'])['profile'];self.assertEqual(175,profile['bag_overrides']['7号铁']['high']);self.assertEqual(175,profile['seven']['value']['distance']);self.assertEqual('沙坑',profile['lofted_wedge_uses']['value']['58'])
   self.assertGreater(engine.db.execute('SELECT count(*) FROM native_profile_fields WHERE owner=%s',(engine.owner,)).fetchone()[0],0)
   event_id='undo-finish';at=older['round']['started_at'];command=dict(v=1,semantics=2,id=event_id,at=at,expected_revision=count,command='undo',data={})
   code,reply=self.request('/offline-rounds',dict(scope,action='sync',sha256=older['package_sha256'],events=[dict(seq=count+1,event=dict(type='local_round_command',event_id=event_id,observed_at=at,data=command))]));self.assertEqual(200,code,reply)
   self.assertEqual(0,engine.db.execute('SELECT count(*) FROM native_profile_fields WHERE owner=%s AND round_id=%s',(engine.owner,older['round_id'])).fetchone()[0]);self.assertEqual(175,private_context(engine,ID,'蓝Tee',asset(ID)['package']['course'])['profile']['seven']['value']['distance'])
  finally:engine.close()
 def test_score_comparison_ignores_core_version_but_respects_course_tee_length_and_completion(self):
  from native_profile import score_basis
  from native_rounds import history_summary
  from course_downloads import asset
  from phoenix_demo import ID
  engine=Engine(self.db.url,self.a['user']['id'])
  try:
   course=asset(ID)['package']['course'];basis_key=score_basis(course)
   for rid,tee,basis,holes,total in [('prior-core14','蓝Tee',basis_key,18,72),('other-tee','白Tee',basis_key,18,60),('incomplete','蓝Tee',basis_key,17,50),('changed-length','蓝Tee','different',18,55),('current-core16','蓝Tee',basis_key,18,75)]:
    engine.db.execute('INSERT INTO native_rounds(owner,round_id,device_id,asset_digest,package_digest,registration_digest,course_id,tee,memory_allowed,finished,updated_at,total,confirmed_holes,score_basis) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(engine.owner,rid,'device-test',rid,'p','r',ID,tee,True,True,1,total,holes,basis))
   result=history_summary(engine,'current-core16');self.assertEqual(1,result['count']);self.assertEqual(72,result['best']);self.assertEqual(72,result['sum'])
   changed=json.loads(json.dumps(course));changed['holes'][0]['published_yardage']+=1;self.assertNotEqual(basis_key,score_basis(changed))
   same=json.loads(json.dumps(course));same['holes'][0]['published_yardage']=float(same['holes'][0]['published_yardage']);self.assertEqual(basis_key,score_basis(same))
  finally:engine.close()
 def test_schema_upgrade_backfills_score_basis_and_original_profile_clocks_without_changing_records(self):
  from database import bootstrap_schema,close_pools
  import psycopg
  body,_=self.seed('migration-profile-round');body=self.with_round_time(body,'2026-11-20T00:00:00Z');self.finish_registration(body,[('set_club_carry',{'club':'7号铁','low':175,'high':175})])
  engine=Engine(self.db.url,self.a['user']['id'])
  try:
   before=engine.db.execute('SELECT state FROM rounds WHERE owner=%s AND id=%s',(engine.owner,'native-'+body['round_id'])).fetchone()[0];count=engine.db.execute('SELECT count(*) FROM commands WHERE owner=%s',(engine.owner,)).fetchone()[0]
   engine.db.execute('DELETE FROM native_profile_fields WHERE owner=%s',(engine.owner,));engine.db.execute('UPDATE native_rounds SET started_at=0,score_basis=NULL WHERE owner=%s',(engine.owner,))
  finally:engine.close()
  with psycopg.connect(self.db.url,autocommit=True) as db:db.execute('UPDATE schema_meta SET version=2')
  close_pools(self.db.url);bootstrap_schema(self.db.url)
  engine=Engine(self.db.url,self.a['user']['id'])
  try:
   self.assertEqual(before,engine.db.execute('SELECT state FROM rounds WHERE owner=%s AND id=%s',(engine.owner,'native-'+body['round_id'])).fetchone()[0]);self.assertEqual(count,engine.db.execute('SELECT count(*) FROM commands WHERE owner=%s',(engine.owner,)).fetchone()[0])
   row=engine.db.execute("SELECT value,occurred_at FROM native_profile_fields WHERE owner=%s AND field='bag:7号铁'",(engine.owner,)).fetchone();self.assertEqual(175,json.loads(row[0])['high']);self.assertLess(row[1],datetime.now(timezone.utc).timestamp()-86400)
   self.assertIsNotNone(engine.db.execute('SELECT score_basis FROM native_rounds WHERE owner=%s',(engine.owner,)).fetchone()[0])
  finally:engine.close()
 def test_postgame_memory_opt_out_removes_round_from_personal_field_reuse(self):
  body,_=self.seed('memory-opt-out-round');scope,count=self.finish_registration(body,[('set_club_carry',{'club':'7号铁','low':175,'high':175})]);self.assertEqual(200,self.request('/offline-rounds',dict(scope,action='release',cursor=count))[0])
  event=dict(type='message',event_id='disable-memory',observed_at=datetime.now(timezone.utc).isoformat(),text='关闭跨场记忆')
  code,reply=self.request('/offline-rounds',dict(scope,action='event',operation_id='disable-memory',event=event));self.assertEqual(200,code,reply)
  engine=Engine(self.db.url,self.a['user']['id'])
  try:
   self.assertEqual(False,engine.db.execute('SELECT memory_allowed FROM native_rounds WHERE owner=%s AND round_id=%s',(engine.owner,body['round_id'])).fetchone()[0]);self.assertEqual(0,engine.db.execute('SELECT count(*) FROM native_profile_fields WHERE owner=%s AND round_id=%s',(engine.owner,body['round_id'])).fetchone()[0])
  finally:engine.close()
