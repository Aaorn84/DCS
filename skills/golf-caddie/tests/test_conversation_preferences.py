import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine
from journey import view
from conversation_preferences import preferred_unit,agreement
STAMP='2026-11-07T00:00:00+08:00'
class NaturalPreferenceTests(unittest.TestCase):
 def setUp(self):self.e=Engine(':memory:','test');self.e.create('j');self.n=0
 def tearDown(self):self.e.close()
 def send(self,text='',version=5,type='message'):
  self.n+=1;p=dict(type=type,event_id='e'+str(self.n),observed_at=STAMP)
  if type=='message':p['text']=text
  if version in (2,3,4,5):p['protocol_version']=version
  return self.e.command('j',str(self.n),'journey_event',p)
 def stage(self):return view(self.e.state('j'))['stage']
 def setup_proactive(self):self.send('可以记住');self.send('测试球友')
 def test_default_yards_without_question(self):
  self.setup_proactive();self.assertEqual(self.stage(),'proactive')
  self.assertNotIn('units',self.e.state('j')['journey']['profile']);self.assertEqual(view(self.e.state('j'))['distance_unit'],'码')
 def test_natural_affirmatives(self):
  for text in ['当然','当然可以','可以','Ok','OK!','ＯＫ','好','好的','no problem','No Problem.','没问题','嗯，可以','可以，谢谢']:
   with self.subTest(text=text):self.assertIs(agreement(text),True)
 def test_natural_negatives(self):
  for text in ['不可以','不要','不用提醒','No','not ok']:
   with self.subTest(text=text):self.assertIs(agreement(text),False)
 def test_questions_and_hedges_are_not_permission(self):
  for text in ['可以吗？','好像可以','也许吧','看情况','OK但不要提醒','他说可以','no problem?']:
   with self.subTest(text=text):self.assertIsNone(agreement(text))
 def test_affirmatives_advance_only_current_agreement(self):
  for text in ['当然','可以','Ok','好','no problem']:
   self.e.create(text)
   for i,t in enumerate(['可以记住','测试球友',text]):
    self.e.command(text,str(i),'journey_event',dict(type='message',protocol_version=5,event_id='x'+str(i),observed_at=STAMP,text=t))
   s=self.e.state(text);self.assertEqual(view(s)['stage'],'shot_recording');self.assertTrue(s['journey']['profile']['proactive']['value']);self.assertFalse(s['journey']['coach']['enabled'])
 def test_ambiguous_reply_does_not_advance(self):
  self.setup_proactive();r=self.send('可以吗？');self.assertEqual(self.stage(),'proactive');self.assertNotIn('proactive',self.e.state('j')['journey']['profile']);self.assertEqual(r['text'].count('？'),1)
 def test_explicit_refusal_is_respected(self):
  self.setup_proactive();self.send('no');self.assertFalse(self.e.state('j')['journey']['profile']['proactive']['value']);self.assertEqual(self.stage(),'shot_recording')
 def test_units_natural_language_and_negation(self):
  examples={'我不习惯使用码，我更喜欢或习惯使用米':'米','我更习惯用米':'米','我更喜欢使用米':'米','距离改用米':'米','以后用米':'米','改回码':'码','我不喜欢米，还是用码':'码','用米，不要用码':'米','不习惯使用码':None,'不使用米':None,'还有多少米':None}
  for text,expected in examples.items():
   with self.subTest(text=text):self.assertEqual(preferred_unit(text),expected)
 def test_unit_override_preserves_pending_question(self):
  self.setup_proactive();r=self.send('我不习惯使用码，我更喜欢或习惯使用米');self.assertEqual(self.stage(),'proactive');self.assertEqual(view(self.e.state('j'))['distance_unit'],'米');self.assertEqual(r['text'].count('？'),1);self.send('当然');self.assertEqual(self.stage(),'shot_recording')
 def test_combined_units_and_consent(self):
  self.setup_proactive();self.send('我更习惯用米，当然可以');j=self.e.state('j')['journey'];self.assertEqual(j['profile']['units']['value'],'米');self.assertTrue(j['profile']['proactive']['value']);self.assertEqual(self.stage(),'shot_recording')
 def test_unit_change_does_not_reinterpret_existing_distances(self):
  self.setup_proactive()
  for t in ['好','不记录击球','230']:self.send(t)
  self.send('以后用米');self.assertEqual(self.e.state('j')['journey']['profile']['driver']['value']['units'],'码');self.assertEqual(self.stage(),'seven');self.send('130');self.assertEqual(self.e.state('j')['journey']['profile']['seven']['value']['units'],'米')
 def test_legacy_pending_unit_migration_does_not_grant_unseen_permission(self):
  self.send('可以记住',version=1);self.send('测试球友',version=1)
  self.assertEqual(self.e.state('j')['journey']['stage'],'units')
  self.send('当然');self.assertEqual(self.stage(),'proactive');self.assertNotIn('proactive',self.e.state('j')['journey']['profile'])
  self.send('当然');self.assertEqual(self.stage(),'shot_recording');self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_legacy_unit_button_preserved(self):
  self.send('可以记住',version=1);self.send('测试球友',version=1);self.send('米');self.assertEqual(view(self.e.state('j'))['distance_unit'],'米');self.assertEqual(self.stage(),'proactive');self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_legacy_history_replay_unchanged(self):
  for t in ['可以记住','测试球友','码','可以提醒','不记录击球','230','总距离','140','落地','偏右']:self.send(t,version=1)
  before=self.e.state('j');self.assertEqual(before,self.e.replay('j'));self.send('我更习惯用米');self.assertEqual(self.stage(),'course');self.assertEqual(self.e.state('j'),self.e.replay('j'))
if __name__=='__main__':unittest.main()
