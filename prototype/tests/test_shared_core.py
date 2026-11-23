import concurrent.futures,unittest
from services.api.server import Engine
from shared_core import call,_pool,CORE_VERSION
from shared_core import create_local_round,apply_local_command
from round_state import StateError

class SharedCoreTests(unittest.TestCase):
 def pack(self,rid='r'):
  return dict(schema=1,core_version=CORE_VERSION,round=dict(id=rid,tee='蓝Tee'),course=dict(course_id='c',holes=[dict(number=i,par=4) for i in range(1,19)]))
 def test_worker_is_reused_and_recovers_without_a_second_rule_implementation(self):
  _runtime=_pool.workers[0]
  self.assertEqual(CORE_VERSION,call('capabilities')['core_version']);process=_runtime.process
  a=create_local_round(self.pack());self.assertIs(process,_runtime.process)
  process.kill();process.wait();b=create_local_round(self.pack());self.assertEqual(a,b);self.assertIsNot(process,_runtime.process)
 def test_parallel_accounts_do_not_share_state(self):
  def execute(n):
   s=create_local_round(self.pack('r'+str(n)));return apply_local_command(s,dict(v=1,semantics=2,id='start',at='2026-01-01T00:00:00Z',expected_revision=0,command='start',data={}))
  with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:states=list(pool.map(execute,range(12)))
  self.assertEqual(12,len({s['round_id'] for s in states}));self.assertTrue(all(s['revision']==1 for s in states))
 def test_version_and_invalid_commands_fail_closed(self):
  p=self.pack();p['core_version']='old';
  with self.assertRaisesRegex(StateError,'version mismatch'):create_local_round(p)
  s=create_local_round(self.pack())
  with self.assertRaisesRegex(StateError,'start round first'):apply_local_command(s,dict(v=1,semantics=2,id='bad',at='2026-01-01T00:00:00Z',expected_revision=0,command='record_stroke',data={'club':'7号铁'}))
 def test_cached_packages_are_scoped_bounded_and_reload_after_worker_restart(self):
  from shared_core import plan
  _runtime=_pool.workers[_pool.index('account-a|a|hash-a')]
  calls=[]
  def package(rid):
   calls.append(rid);return self.pack(rid)
  a=create_local_round(self.pack('a'));b=create_local_round(self.pack('b'))
  first=plan('account-a|a|hash-a',lambda:package('a'),a)
  self.assertEqual(first,plan('account-a|a|hash-a',lambda:package('a'),a));self.assertEqual(['a'],calls)
  plan('account-b|b|hash-b',lambda:package('b'),b);self.assertEqual(['a','b'],calls)
  for n in range(10):
   state=create_local_round(self.pack('n'+str(n)));plan('other-'+str(n),lambda n=n:package('n'+str(n)),state)
  self.assertLessEqual(len(_runtime.registered),8)
  _runtime.process.kill();_runtime.process.wait();self.assertEqual(first,plan('account-a|a|hash-a',lambda:package('a'),a));self.assertEqual('a',calls[-1])
 def test_old_and_new_cores_share_worker_but_never_state_or_cached_package_versions(self):
  from shared_core import plan,web_turn,SUPPORTED_CORES
  self.assertEqual(list(SUPPORTED_CORES),call('capabilities')['supported_core_versions'])
  old=self.pack('old-round');old['core_version']='1.4.0';old_state=create_local_round(old)
  self.assertEqual('1.4.0',old_state['core_version'])
  cmd=dict(v=1,semantics=2,id='start-old',at='2026-01-01T00:00:00Z',expected_revision=0,command='start',data={})
  old_state=apply_local_command(old_state,cmd)
  with self.assertRaisesRegex(StateError,'unsupported local command'):apply_local_command(old_state,dict(cmd,id='pref',expected_revision=1,command='set_strategy_preference',data={'preference':'control'}))
  first=plan('old-version-scope',lambda:old,old_state);self.assertEqual('1.4.0',first['core_version']);self.assertNotIn('policy_version',first)
  current=create_local_round(self.pack('current-round'));self.assertEqual(CORE_VERSION,current['core_version'])
  with self.assertRaisesRegex(StateError,'version mismatch'):plan('old-version-scope',lambda:old,current)
  resumed=web_turn('old-web-scope',lambda:old,old_state,dict(type='resume',event_id='resume-old',observed_at='2026-01-01T00:00:00Z'),{})
  self.assertEqual('1.4.0',resumed['model']['core_version'])
  self.assertEqual('1.4.0',plan('old-version-scope',lambda:old,old_state)['core_version'])
