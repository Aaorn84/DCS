from testing.database import TestDatabase
import tempfile,unittest,time
from datetime import datetime,timezone,timedelta
from services.api.server import Engine
from round_state import canonical,Conflict,StateError
from services.api.offline_sync import prepare as raw_prepare,synchronize,release,online_guard,AGGREGATE,row
def prepare(engine,body):
 from shared_core import CORE_VERSION
 return raw_prepare(engine,dict(body,local_engine_version=1,core_version=CORE_VERSION))
class OfflineSyncTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TestDatabase();self.e=Engine(self.tmp.url,'owner');self.e.create(AGGREGATE)
  s=self.e.state(AGGREGATE);s['journey']={'stage':'ready','round':{'id':'real-round','course':'synthetic-journey','tee':'蓝Tee','finished':False},'profile':{},'quiet':False,'memory_allowed':False,'number':1,'history':[]}
  from phoenix_demo import course
  s['journey']['round'].update(course='dongguan-phoenix-ab-blue-demo',start_hole=1)
  s['facts']['context.course_snapshot']={'value':'map','valid':True};s['evidence']['map']={'data':course()}
  self.e.db.execute('UPDATE rounds SET state=%s WHERE owner=%s AND id=%s',(canonical(s),'owner',AGGREGATE))
  self.p=prepare(self.e,{'device_id':'device-one','expected_version':0});self.body=dict(self.p['offline'],device_id='device-one')
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def entry(self,n,text='稍等',seconds=0):
  at=datetime.now(timezone.utc)+timedelta(seconds=seconds)
  command=dict(v=1,semantics=2,id='e'+str(n),at=at.isoformat(),expected_revision=n-1,command='start' if n==1 else 'select_club',data={} if n==1 else {'club':'7号铁'})
  return dict(seq=n,event=dict(type='local_round_command',event_id=command['id'],observed_at=command['at'],data=command))

 def test_other_device_cannot_take_over_and_prepare_is_idempotent(self):
  self.assertEqual(self.p,prepare(self.e,{'device_id':'device-one','expected_version':0}))
  with self.assertRaises(Conflict):prepare(self.e,{'device_id':'device-two','expected_version':0})
  with self.assertRaises(Conflict):online_guard(self.e,self.e.state(AGGREGATE))
 def test_retry_is_idempotent_and_cursor_atomic_with_event(self):
  entry=self.entry(1);body=dict(self.body,events=[entry])
  first=synchronize(self.e,body);second=synchronize(self.e,body)
  self.assertEqual(first,second);self.assertEqual(1,self.e.state(AGGREGATE)['version']);self.assertEqual(1,row(self.e)['cursor'])
  release(self.e,dict(self.body,cursor=1));online_guard(self.e,self.e.state(AGGREGATE))
 def test_gap_and_changed_payload_cannot_mutate_state(self):
  with self.assertRaises(Conflict):synchronize(self.e,dict(self.body,events=[self.entry(2)]))
  first=self.entry(1);synchronize(self.e,dict(self.body,events=[first]))
  first['event']['data']['data']={'changed':True}
  with self.assertRaises(Conflict):synchronize(self.e,dict(self.body,events=[first]))
  self.assertEqual(1,row(self.e)['cursor'])
 def test_control_injection_and_wrong_package_rejected(self):
  item=self.entry(1);item['event']['_stroke_consistency_v111']=True
  with self.assertRaises(StateError):synchronize(self.e,dict(self.body,events=[item]))
  with self.assertRaises(StateError):synchronize(self.e,dict(self.body,sha256='wrong',events=[]))
 def test_recorded_time_used_and_replay_matches(self):
  item=self.entry(1,seconds=-30);synchronize(self.e,dict(self.body,events=[item]))
  at=self.e.db.execute('SELECT at FROM commands WHERE owner=%s',('owner',)).fetchone()[0]
  self.assertAlmostEqual(datetime.fromisoformat(item['event']['observed_at']).timestamp(),at)
  self.assertEqual(1,row(self.e)['cursor'])
 def test_owner_isolation_and_release_cursor_check(self):
  other=Engine(self.tmp.url,'other');other.create(AGGREGATE)
  try:
   with self.assertRaises(Conflict):synchronize(other,dict(self.body,events=[]))
  finally:other.close()
  with self.assertRaises(Conflict):release(self.e,dict(self.body,cursor=99))
  self.assertEqual('active',row(self.e)['status'])
 def test_partial_batch_failure_exposes_committed_cursor_for_resume(self):
  first=self.entry(1);second=self.entry(2);second['event']['data']['expected_revision']=999
  with self.assertRaises(StateError):synchronize(self.e,dict(self.body,events=[first,second]))
  self.assertEqual(1,row(self.e)['cursor']);self.assertEqual(1,self.e.state(AGGREGATE)['version'])
  # Retrying the exact committed prefix is harmless after the interrupted batch.
  self.assertEqual(1,synchronize(self.e,dict(self.body,events=[first]))['offline']['cursor'])
 def test_failed_cursor_write_rolls_back_event_and_state_together(self):
  from unittest.mock import patch
  original=self.e.command
  def failing(*args,**kwargs):
   callback=kwargs['on_commit']
   def fail(state,result):
    callback(state,result)
    raise StateError('simulated disk failure')
   kwargs['on_commit']=fail
   return original(*args,**kwargs)
  with patch.object(self.e,'command',side_effect=failing):
   with self.assertRaises(StateError):synchronize(self.e,dict(self.body,events=[self.entry(1)]))
  self.assertEqual(0,row(self.e)['cursor']);self.assertEqual(0,self.e.state(AGGREGATE)['version'])
  self.assertEqual(0,self.e.db.execute('SELECT count(*) FROM commands').fetchone()[0])
 def test_two_phase_prepare_does_not_block_online_until_activation(self):
  from offline_sync import activate,cancel_preparation
  release(self.e,dict(self.body,cursor=0))
  reserved=prepare(self.e,dict(device_id='device-one',expected_version=0,two_phase=True))['offline']
  self.assertEqual('preparing',reserved['status']);online_guard(self.e,self.e.state(AGGREGATE))
  activated=activate(self.e,reserved);self.assertEqual('active',activated['offline']['status'])
  with self.assertRaises(Conflict):online_guard(self.e,self.e.state(AGGREGATE))
  cancel_preparation(self.e,reserved);online_guard(self.e,self.e.state(AGGREGATE))
 def test_changed_online_state_cannot_activate_stale_preparation(self):
  from offline_sync import activate,cancel_preparation
  release(self.e,dict(self.body,cursor=0))
  reserved=prepare(self.e,dict(device_id='device-one',expected_version=0,two_phase=True))['offline']
  self.e.command(AGGREGATE,'online-progress','application_event',dict(type='message',event_id='online-progress',observed_at=datetime.now(timezone.utc).isoformat(),text='稍等'),guard=lambda s:online_guard(self.e,s))
  with self.assertRaises(Conflict):activate(self.e,reserved)
  cancel_preparation(self.e,reserved);self.assertEqual(1,self.e.state(AGGREGATE)['version'])

 def test_free_text_transport_mode_is_removed(self):
  with self.assertRaises(StateError):raw_prepare(self.e,dict(device_id='device-one',expected_version=0))
  bad=dict(seq=1,event=dict(type='message',event_id='old',observed_at=datetime.now(timezone.utc).isoformat(),text='开始球局'))
  with self.assertRaises(StateError):synchronize(self.e,dict(self.body,events=[bad]))
  self.assertEqual(0,row(self.e)['cursor'])
 def test_unversioned_commands_cannot_commit_state_or_advance_cursor(self):
  item=self.entry(1);item['event']['data'].pop('semantics')
  with self.assertRaisesRegex(StateError,'unsupported command semantics'):synchronize(self.e,dict(self.body,events=[item]))
  self.assertEqual(0,row(self.e)['cursor']);self.assertEqual(0,self.e.state(AGGREGATE)['version'])
  self.assertEqual(0,self.e.db.execute('SELECT count(*) FROM commands').fetchone()[0])
 def test_native_finish_saves_the_pinned_comparison_basis(self):
  commands=[('start',{}),('draft_score',dict(total=4,putts=2,penalties=0)),('confirm_score',dict(confirmed=True)),('request_finish',{}),('confirm_finish',dict(confirmed=True))]
  entries=[]
  for seq,(name,data) in enumerate(commands,1):
   entry=self.entry(seq);entry['event']['data'].update(command=name,data=data);entries.append(entry)
  reply=synchronize(self.e,dict(self.body,events=entries));self.assertEqual(5,reply['offline']['cursor'])
  archive=self.e.state(AGGREGATE)['journey']['history'][-1];self.assertEqual(4,archive['confirmed_subtotal']);self.assertEqual(18,len(archive['course_basis'][0]));self.assertEqual({'par':4,'published_yardage':380},archive['course_basis'][0]['11'])
