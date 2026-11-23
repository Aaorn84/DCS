from testing.database import TestDatabase
"""The retained app services cannot execute on-course commands or old protocols."""
import copy,unittest,tempfile,ast
from pathlib import Path
from datetime import datetime,timezone
from services.api.server import Engine
from round_state import StateError,Conflict,canonical

class ApplicationServiceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=TestDatabase();self.e=Engine(self.tmp.url,'owner');self.e.create('app');self.n=0
 def tearDown(self):self.e.close();self.tmp.cleanup()
 def send(self,text=None,kind='message',operation=None,**extra):
  self.n+=1;p=dict(type=kind,event_id='event'+str(self.n),observed_at=datetime.now(timezone.utc).isoformat(),**extra)
  if text is not None:p['text']=text
  return self.e.command('app',operation or 'op'+str(self.n),'application_event',p)
 def save(self,state):self.e.db.execute('UPDATE rounds SET state=%s WHERE owner=%s AND id=%s',(canonical(state),'owner','app'))
 def ready(self):
  for text in ('可以记住','球友','好','好','240','150','偏右','5号木200码','东莞凤凰山（A+B蓝台演示）','蓝Tee','1'):
   # Tee name normalization normally belongs to the HTTP boundary.
   self.send(text.replace('蓝Tee','蓝台'))
  return self.e.state('app')
 def test_first_questions_store_finder_and_carry_without_golf_model(self):
  state=self.ready();j=state['journey'];self.assertEqual('ready',j['stage']);self.assertEqual(200,j['profile']['five_wood']['value']['distance']);self.assertEqual('five_wood',j['profile']['fairway_finder']['value']['club_key']);self.assertNotIn('offline_local_round',j);self.assertEqual(state,self.e.replay('app'))
 def test_resuming_configured_user_never_repeats_finder_question(self):
  self.ready();reply=self.send(kind='resume');self.assertNotIn('保底',reply['text']);self.assertNotIn('finder_pending',self.e.state('app')['journey'])
 def test_backfill_question_is_only_asked_once(self):
  state=self.ready();j=state['journey'];j['profile'].pop('fairway_finder');j.pop('finder_onboarding_asked');self.save(state)
  self.assertIn('保底',self.send(kind='resume')['text']);self.send('跳过');self.assertNotIn('保底',self.send(kind='resume')['text'])
 def test_application_cannot_handle_active_golf_or_start_round(self):
  state=self.ready();state['journey']['stage']='active';self.save(state);before=self.e.state('app')
  for text in ('确认出界','这洞六杆','已回原位','这杆怎么打'):
   with self.assertRaises(StateError):self.send(text)
   self.assertEqual(before,self.e.state('app'))
 def test_old_reducer_kinds_are_rejected_transactionally(self):
  for kind in ('journey_event','session_event','attribution_event','evidence','patch'):
   with self.assertRaises(StateError):self.e.command('app',kind,kind,{})
  self.assertEqual(0,self.e.state('app')['version']);self.assertEqual(0,self.e.db.execute('select count(*) from commands').fetchone()[0])
 def test_unknown_control_fields_are_rejected_without_receipt(self):
  with self.assertRaises(StateError):self.send('可以记住',protocol_version=111)
  self.assertEqual(0,self.e.state('app')['version'])
 def test_no_old_protocol_retry_rewriting(self):
  p=dict(type='resume',event_id='same',observed_at=datetime.now(timezone.utc).isoformat())
  first=self.e.command('app','op','application_event',p)
  self.assertEqual(first,self.e.command('app','op','application_event',p))
  with self.assertRaises(Conflict):self.e.command('app','op','application_event',dict(p,protocol_version=111))
 def test_postgame_analysis_does_not_change_coach_consent(self):
  state=self.ready();j=state['journey'];j['stage']='coach_consent';j['round']['finished']=True;state['facts']['holes.1.total']=dict(value=4,valid=True);state['facts']['holes.1.putts']=dict(value=2,valid=True);state['facts']['holes.1.penalties']=dict(value=0,valid=True);self.save(state)
  reply=self.send('给这场球做个分析总结');self.assertIn('4杆',reply['text']);self.assertFalse(self.e.state('app')['journey']['coach']['enabled'])
 def test_next_round_drops_golf_state_and_keeps_consented_profile(self):
  state=self.ready();j=state['journey'];j['stage']='postgame';j['round']['finished']=True;j['offline_local_round']={'round_id':j['round']['id']};j['shared_web_context']={'stale':True};self.save(state)
  self.send(kind='next_round');j=self.e.state('app')['journey'];self.assertEqual('course',j['stage']);self.assertNotIn('offline_local_round',j);self.assertNotIn('shared_web_context',j);self.assertEqual(200,j['profile']['five_wood']['value']['distance'])
 def test_memory_opt_out_is_respected_on_next_round(self):
  state=self.ready();state['journey']['stage']='postgame';state['journey']['round']['finished']=True;self.save(state)
  self.send('关闭跨场记忆');self.send(kind='next_round');j=self.e.state('app')['journey'];self.assertEqual({},j['profile']);self.assertFalse(j['coach']['enabled'])
 def test_supported_backend_imports_do_not_reach_retired_implementations(self):
  root=Path(__file__).resolve().parents[1]/'services/api'
  removed={'journey','ball_rules','local_round_engine','round_session','shot_chain','tee_strategy','tee_geometry','approach_strategy'}
  for path in root.glob('*.py'):
   tree=ast.parse(path.read_text())
   for node in ast.walk(tree):
    if isinstance(node,ast.ImportFrom):self.assertNotIn(node.module,removed,path.name)
  for name in removed:self.assertFalse((root/(name+'.py')).exists(),name)
 def test_next_round_keeps_consented_dispersion_and_exports_it(self):
  from services.api.offline_package import build
  state=self.ready();j=state['journey'];j['stage']='postgame';j['round']['finished']=True
  samples=[dict(scope='prior-round',stroke_id='opening',club='5号木',lateral_m=3,longitudinal_m=-2)]
  summary={'5号木':dict(samples=30,lateral_p10_m=-8,lateral_p90_m=10,lateral_median_m=1)}
  j.update(tee_dispersion_samples=samples,tee_dispersion_summary=summary,tee_dispersion_token='old-token');self.save(state)
  self.send(kind='next_round');j=self.e.state('app')['journey']
  self.assertEqual(samples,j['tee_dispersion_samples']);self.assertEqual(summary,j['tee_dispersion_summary']);self.assertNotIn('tee_dispersion_token',j)
  for word in ('东莞凤凰山（A+B蓝台演示）','蓝台','1'):self.send(word)
  self.assertEqual(summary,build(self.e.state('app'))['package']['dispersion'])
 def test_next_round_discards_dispersion_without_memory_consent(self):
  state=self.ready();j=state['journey'];j['stage']='postgame';j['round']['finished']=True
  j.update(tee_dispersion_samples=[{'club':'5号木'}],tee_dispersion_summary={'5号木':{'samples':30}});self.save(state)
  self.send('关闭跨场记忆');self.send(kind='next_round');j=self.e.state('app')['journey']
  self.assertNotIn('tee_dispersion_samples',j);self.assertNotIn('tee_dispersion_summary',j)
