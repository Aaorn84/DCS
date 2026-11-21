import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from fairway_finder import handle
class FinderTests(unittest.TestCase):
 def test_set_and_complete_carry_without_creating_shot(self):
  s={'journey':{'round':{'id':'r'},'profile':{}}}
  self.assertIn('哪支杆',handle(s,'设置保底开球杆','a'))
  self.assertIn('Carry',handle(s,'5号木','b'))
  self.assertIn('已补充',handle(s,'200','c'))
  self.assertEqual(200,s['journey']['profile']['five_wood']['value']['distance'])
  self.assertEqual('five_wood',s['journey']['profile']['fairway_finder']['value']['club_key'])
  self.assertNotIn('player_decisions',s['journey'])
  handle(s,'取消保底开球杆','d');self.assertNotIn('fairway_finder',s['journey']['profile'])
 def test_not_intercept_ordinary_choice(self):self.assertIsNone(handle({'journey':{}},'5号木','a'))
 def test_onboarding_asks_once_and_remembers_choice(self):
  from round_state import initial
  from journey import _apply_journey
  s=initial();s['journey']={'stage':'miss','profile':{},'round':None,'quiet':False}
  def send(text):return _apply_journey(s,dict(type='message',text=text,event_id=__import__("uuid").uuid4().hex,observed_at='1970-01-01T00:00:00+00:00',protocol_version=111),1,0)
  self.assertIn('保底开球杆',send('偏右')['text'])
  send('5号木');self.assertEqual('five_wood',s['journey']['profile']['fairway_finder']['value']['club_key'])
  s['journey']['stage']='miss';self.assertNotIn('最信任',send('偏右')['text'])
 def test_existing_user_backfill_once_and_saved_choice_not_reasked(self):
  from round_state import initial
  from journey import _apply_journey
  s=initial();s['journey']={'stage':'ready','profile':{},'round':{'id':'r'},'quiet':False}
  def turn(kind,text=''):
   return _apply_journey(s,dict(type=kind,text=text,event_id=__import__('uuid').uuid4().hex,observed_at='1970-01-01T00:00:00+00:00'),1,0)
  self.assertIn('保底开球杆',turn('resume')['text'])
  turn('message','5号木')
  self.assertEqual('five_wood',s['journey']['profile']['fairway_finder']['value']['club_key'])
  self.assertNotIn('补充了解',turn('resume')['text'])
 def test_optional_backfill_does_not_block_other_messages(self):
  s={'journey':{'round':{'id':'r'},'finder_pending':{'round':'r','phase':'club','optional':True},'profile':{}}}
  self.assertIsNone(handle(s,'这杆怎么打','x'));self.assertNotIn('finder_pending',s['journey'])

 def test_setting_aliases_are_not_taken_as_current_shot_choice(self):
  from round_state import initial
  from journey import _apply_journey
  for phrase in ('保底球杆设置','保底开球杆设置','设置保底球杆','修改保底开球杆'):
   with self.subTest(phrase=phrase):
    s=initial();s['journey']={'stage':'active','profile':{},'round':{'id':'r'},'quiet':False,'consultation':{'phase':'tee_commit','last_offer':{'options':[{'club':'一号木'},{'club':'3号木'}]}}}
    r=_apply_journey(s,dict(type='message',text=phrase,event_id='finder-alias',observed_at='1970-01-01T00:00:00+00:00'),1,0)
    self.assertIn('哪支杆是你最信任',r['text']);self.assertEqual('club',s['journey']['finder_pending']['phase'])
    self.assertNotIn('player_decisions',s['journey'])
    _apply_journey(s,dict(type='message',text='5号木',event_id='finder-choice',observed_at='1970-01-01T00:00:00+00:00'),2,0)
    self.assertEqual('five_wood',s['journey']['profile']['fairway_finder']['value']['club_key'])
    self.assertNotIn('player_decisions',s['journey'])

 def test_combined_finder_and_carry_onboarding_and_settings(self):
  from round_state import initial
  from journey import _apply_journey
  for context in ('onboarding','settings'):
   with self.subTest(context=context):
    s=initial();s['journey']={'stage':'course' if context=='onboarding' else 'active','profile':{},'round':None,'quiet':False}
    if context=='onboarding':s['journey']['finder_onboarding_pending']=True
    else:handle(s,'设置保底开球杆','ask')
    r=_apply_journey(s,dict(type='message',text='5号木200码',event_id='combined',observed_at='1970-01-01T00:00:00+00:00'),1,0)
    profile=s['journey']['profile'];self.assertEqual('five_wood',profile['fairway_finder']['value']['club_key'])
    self.assertEqual(200,profile['five_wood']['value']['distance']);self.assertEqual('carry',profile['five_wood']['value']['distance_type'])
    self.assertNotIn('finder_pending',s['journey']);self.assertNotIn('大概多少',r['text'])
