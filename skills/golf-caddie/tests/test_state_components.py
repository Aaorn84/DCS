import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine,canonical,initial
from state_components import LazyList,TAG,materialize
from history_access import page,hole
class StateComponentsTests(unittest.TestCase):
 def setUp(self):self.engine=Engine(':memory:','owner');self.engine.create('j')
 def tearDown(self):self.engine.close()
 def fixture(self):
  s=initial();s['journey']=dict(stage='active',round={'id':'current'},history=[dict(round=dict(id='old',course='a',finished=True),confirmed_subtotal=80,confirmed_holes=18,scores=[dict(hole=1,total=4)],hole_history={'1':dict(signature='sig',shots=[dict(id='shot',club='7号铁',origin={'latitude':1,'longitude':2},landing={'latitude':3,'longitude':4})])})],ball_rules={})
  self.engine.db.execute('UPDATE rounds SET state=? WHERE owner=? AND id=?',(canonical(s),'owner','j'));return s
 def test_compaction_preserves_complete_domain_and_materialized_public_state(self):
  original=self.fixture();self.engine.compact('j');self.assertEqual(self.engine.state('j'),original)
  raw=json.loads(self.engine.db.execute('select state from rounds').fetchone()[0]);self.assertIn(TAG,raw['journey']['history'][0]['hole_history']['1']['shots'])
 def test_metadata_page_does_not_load_shot_or_score_components(self):
  self.fixture();self.engine.compact('j');s=self.engine.state('j',lazy=True);entry=s['journey']['history'][0];shots=entry['hole_history']['1']['shots'];scores=entry['scores'];p=page(s)
  self.assertFalse(shots.loaded);self.assertFalse(scores.loaded);self.assertNotIn('hole_history',p['rounds'][0]);self.assertNotIn('scores',p['rounds'][0])
  h=hole(s,'old',1);self.assertEqual(h['shots'][0]['club'],'7号铁');self.assertTrue(shots.loaded)
 def test_loaded_nested_mutation_is_saved_without_mutating_old_immutable_blob(self):
  original=self.fixture();self.engine.compact('j');s=self.engine.state('j',lazy=True);shots=s['journey']['history'][0]['hole_history']['1']['shots'];old=shots.digest;shots[0]['club']='6号铁'
  packed=self.engine.components.encode(s);self.engine.db.execute('UPDATE rounds SET state=?',(canonical(packed),));self.assertEqual(self.engine.state('j')['journey']['history'][0]['hole_history']['1']['shots'][0]['club'],'6号铁')
  self.assertEqual(json.loads(self.engine.components.read(old))[0]['club'],'7号铁')
 def test_unchanged_unread_components_are_not_materialized_on_save(self):
  self.fixture();self.engine.compact('j');s=self.engine.state('j',lazy=True);shots=s['journey']['history'][0]['hole_history']['1']['shots'];self.engine.components.encode(s);self.assertFalse(shots.loaded)
 def test_owner_cannot_read_another_owners_component(self):
  digest=self.engine.components.store([{'private':True}])[TAG]
  other=Engine(':memory:','other')
  try:
   with self.assertRaises(ValueError):other.components.read(digest)
  finally:other.close()
 def test_deep_copy_is_independent_and_json_is_complete(self):
  ref=self.engine.components.store([{'n':1}]);lazy=self.engine.components.decode(ref);cloned=copy.deepcopy(lazy);cloned[0]['n']=2
  self.assertEqual(json.loads(canonical(lazy)),[{'n':1}])
 def test_response_state_avoids_reload_and_checks_newer_version(self):
  self.engine.command('j','op','journey_event',dict(protocol_version=111,type='resume',event_id='resume',observed_at='2026-11-21T00:00:00Z'))
  current=self.engine.response_state('j');self.assertIs(current,self.engine._committed[1])
  raw=self.engine.state('j');raw['version']+=1;self.engine.db.execute('UPDATE rounds SET state=?',(canonical(raw),));self.assertEqual(self.engine.response_state('j')['version'],raw['version'])
 def test_receipt_lookup_and_update_do_not_load_the_whole_bucket(self):
  original=self.fixture();original['journey']['style_receipts']={str(i):'digest-'+str(i) for i in range(1000)}
  self.engine.db.execute('UPDATE rounds SET state=?',(canonical(original),));self.engine.compact('j');state=self.engine.state('j',lazy=True);receipts=state['journey']['style_receipts'];queries=[];self.engine.db.set_trace_callback(queries.append)
  self.assertEqual(receipts.get('500'),'digest-500');receipts['new']='new-digest';packed=self.engine.components.encode(state)
  self.assertEqual(len(receipts.values_cache),2);self.assertFalse(any('SELECT receipt_id,data' in q for q in queries))
  self.engine.db.execute('UPDATE rounds SET state=?',(canonical(packed),));restored=self.engine.state('j');self.assertEqual(len(restored['journey']['style_receipts']),1001)
 def test_receipt_nested_change_and_delete_are_saved(self):
  s=self.fixture();s['journey']['receipts']={'a':{'text':'old'},'b':'keep'};self.engine.db.execute('UPDATE rounds SET state=?',(canonical(s),));self.engine.compact('j');state=self.engine.state('j',lazy=True)
  state['journey']['receipts']['a']['text']='new';del state['journey']['receipts']['b'];self.engine.db.execute('UPDATE rounds SET state=?',(canonical(self.engine.components.encode(state)),))
  self.assertEqual(self.engine.state('j')['journey']['receipts'],{'a':{'text':'new'}})
 def test_receipts_are_separate_between_owners_and_aggregates(self):
  from state_components import ReceiptMap
  self.fixture();self.engine.components.aggregate='j';self.engine.components.encode({'journey':{'receipts':{'secret':'value'}}})
  self.assertIsNone(ReceiptMap(self.engine.components,'other-round','receipts').get('secret'))
  from state_components import Components
  other=Components(self.engine.db,'other-owner',self.engine.components.namespace)
  self.assertIsNone(ReceiptMap(other,'j','receipts').get('secret'))
