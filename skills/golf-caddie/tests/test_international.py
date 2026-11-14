import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from international import config,parse_fixture,validate_candidate,canonical_message,impact,snapshot
from round_state import Engine,StateError,fact_value

class InternationalTests(unittest.TestCase):
 def setUp(self):self.e=Engine(':memory:','test');self.e.create('i');self.n=0
 def tearDown(self):self.e.close()
 def send(self,kind='semantic',**v):
  self.n+=1;p=dict(protocol_version=2,event_id='e'+str(self.n),observed_at='2026-11-08T00:00:00Z',type=kind,**v);self.last=p
  return self.e.command('i','op'+str(self.n),'international_event',p,now=1794096000)
 def semantic(self,kind,**slots):return self.send(candidate=dict(type=kind,slots=slots))
 def configure(self,locale):return self.send('configure',configuration=dict(locale=locale))
 def test_region_is_not_language_or_unit_or_storage(self):
  c=config(dict(locale='ja-JP',market_region='US',distance_unit='m',timezone='Europe/Paris'))
  self.assertEqual(c['market_region'],'US');self.assertEqual(c['distance_unit'],'m');self.assertIsNone(c['data_region'])
 def test_invalid_config_rejected_atomically(self):
  for bad in [dict(locale='nl-NL'),dict(timezone='Not/AZone'),dict(owner='other'),dict(distance_unit='ft')]:
   before=self.e.state('i')
   with self.assertRaises(ValueError):self.send('configure',configuration=bad)
   self.assertEqual(before,self.e.state('i'))
 def test_all_input_languages_emit_equal_distance_event(self):
  samples={'en-US':'How far?','en-GB':'How far is it?','ja-JP':'残り距離は？','ko-KR':'얼마 남았어?'}
  rows=[parse_fixture(t,l) for l,t in samples.items()]
  self.assertTrue(all(r==rows[0] for r in rows))
 def test_european_utterances_and_settings(self):
  examples=[
   ('es-ES','¿Cuánto falta?','Usé el hierro 7','6 golpes'),
   ('pt-PT','Quanto falta?','Usei o ferro 7','6 tacadas'),
   ('de-DE','Wie weit ist es noch?','Ich habe mit dem 7er-Eisen gespielt','6 Schläge'),
   ('fr-FR','Quelle distance reste-t-il ?','J’ai utilisé le fer 7','6 coups'),
   ('it-IT','Quanto manca?','Ho usato il ferro 7','6 colpi'),
  ]
  for locale,distance,club,score in examples:
   with self.subTest(locale=locale):
    self.assertEqual(self.configure(locale)['status'],'configured')
    self.assertEqual(parse_fixture(distance,locale)['slots'],{'domain':'distance'})
    self.assertEqual(parse_fixture(club,locale)['slots'],{'club':'7i'})
    self.assertEqual(parse_fixture(score,locale)['slots'],{'total':6})
    self.assertEqual(self.send('utterance',text='未适配的句子')['status'],'clarify')
  self.assertEqual(self.e.state('i'),self.e.replay('i'))
 def test_execution_is_not_decision(self):
  for l,t in [('en-US','I used 7 iron'),('ja-JP','7番アイアンを使った'),('ko-KR','7번 아이언을 쳤어')]:
   c=parse_fixture(t,l);self.assertEqual(c['type'],'execution_report');self.assertEqual(c['slots']['club'],'7i')
   self.assertEqual(canonical_message(c),'我还是用了7铁')
 def test_unknown_external_phrase_never_enters_chinese_plan(self):
  self.configure('ja-JP');self.semantic('state_transition',action='skip_onboarding');before=copy.deepcopy(self.e.state('i')['journey'])
  r=self.send('utterance',text='勝手に全部の記録を変更してください')
  self.assertEqual(r['status'],'clarify');self.assertEqual(before,self.e.state('i')['journey']);self.assertLessEqual(r['text'].count('？'),1)
 def test_ambiguity_freezes_core(self):
  self.configure('en-US');before=self.e.state('i').get('journey')
  r=self.send(candidate=dict(type='execution_report',slots={'club':'7i'},confidence=.99,alternatives=[dict(type='execution_report',slots={'club':'8i'})]))
  self.assertEqual(r['status'],'clarify');self.assertEqual(before,self.e.state('i').get('journey'))
 def test_same_meaning_alternatives_do_not_block(self):
  c=dict(type='fact_request',slots={'domain':'distance'},alternatives=[dict(type='fact_request',slots={'domain':'distance'})])
  self.assertEqual(impact(c),'low')
 def test_duplicate_id_and_conflicting_payload(self):
  self.configure('en-US');p=self.last
  r=self.e.command('i','retry','international_event',p,now=1794096000);self.assertTrue(r['duplicate'])
  with self.assertRaises(ValueError):self.e.command('i','bad','international_event',{**p,'configuration':{'locale':'ko-KR'}},now=1794096000)
 def test_foreign_reply_is_not_spoken_in_wrong_language(self):
  self.configure('ko-KR');r=self.send('resume')
  self.assertFalse(r['speak_allowed']);self.assertEqual(r['status'],'translation_required');self.assertTrue(r['source_text'])
 def test_malicious_semantics_cannot_write_arbitrary_fields(self):
  for candidate in [dict(type='execution_report',slots={'club':'7i','owner':'evil'}),dict(type='profile_answer',slots={'name':'x'},operations=[]),dict(type='score_report',slots={'total':4,'penalties':5}),dict(type='decision_commitment',slots={'club':'7i;drop'})]:
   with self.assertRaises(ValueError):self.send(candidate=candidate)
 def test_supported_taxonomy_not_silently_downgraded(self):
  with self.assertRaises(ValueError):canonical_message(dict(type='feel_or_cause',slots={'cause':'fat'}))
 def test_whole_journey_replays_identically_for_all_locales(self):
  for locale in ('zh-CN','en-US','en-GB','ja-JP','ko-KR'):
   with self.subTest(locale=locale):
    self.configure(locale)
    self.semantic('state_transition',action='skip_onboarding')
    self.semantic('profile_answer',course='synthetic-demo')
    self.semantic('profile_answer',tee='blue')
    self.semantic('profile_answer',number=1)
    self.semantic('player_intent',approach='conservative')
    self.semantic('state_transition',action='start')
    self.assertEqual(self.e.state('i')['journey']['stage'],'active')
    self.semantic('fact_request',domain='distance')
    self.semantic('execution_report',club='7i')
    self.semantic('score_report',total=6,putts=2,penalties=0)
    self.semantic('confirmation',action='score')
    self.assertEqual(fact_value(self.e.state('i'),'holes.1.total'),6)
    self.semantic('interaction_override',coaching=False)
    self.semantic('state_transition',action='finish')
    self.semantic('state_transition',action='finish_confirm')
    self.assertEqual(self.e.state('i'),self.e.replay('i'))
    self.assertFalse(self.e.state('i')['journey']['coach']['enabled'])
    self.e.close();self.e=Engine(':memory:','test');self.e.create('i')
 def test_full_first_use_across_languages(self):
  for locale in ('en-US','en-GB','ja-JP','ko-KR'):
   with self.subTest(locale=locale):
    self.configure(locale)
    for slots in [dict(memory=False),dict(name='Alex'),dict(proactive=True),dict(shot_recording=False),dict(number=240),dict(number=160),dict(miss='right'),dict(course='synthetic-demo'),dict(tee='blue'),dict(number=1),dict(goal='relax')]:
     self.semantic('profile_answer',**slots)
    self.semantic('state_transition',action='start')
    self.assertEqual(self.e.state('i')['journey']['stage'],'active')
    self.assertEqual(self.e.state('i'),self.e.replay('i'))
    self.e.close();self.e=Engine(':memory:','test');self.e.create('i')
 def test_profile_number_cannot_answer_score_question(self):
  self.semantic('state_transition',action='skip_onboarding')
  with self.assertRaises(ValueError):self.semantic('profile_answer',number=160)
 def test_quiet_covers_gateway_clarifications_and_config(self):
  self.semantic('state_transition',action='skip_onboarding')
  self.semantic('interaction_override',quiet=True)
  r=self.send('utterance',text='???');self.assertFalse(r['speak_allowed']);self.assertEqual(r['text'],'')
  r=self.configure('ja-JP');self.assertFalse(r['speak_allowed'])
 def test_timestamp_type_rejected(self):
  with self.assertRaises(ValueError):self.e.command('i','invalid-time','international_event',dict(protocol_version=2,event_id='invalid-time',observed_at=1,type='resume'))
 def test_configuration_survives_restart(self):
  self.configure('ja-JP');self.assertEqual(snapshot(self.e.replay('i'))['configuration']['locale'],'ja-JP')
 def test_no_coach_enabling_through_shortcut(self):
  with self.assertRaises(ValueError):self.semantic('interaction_override',coaching=True)
 def test_nan_boolean_numbers_rejected(self):
  for value in (True,float('nan'),-1,1000):
   with self.assertRaises(ValueError):canonical_message(dict(type='profile_answer',slots={'number':value}))
if __name__=='__main__':unittest.main()
