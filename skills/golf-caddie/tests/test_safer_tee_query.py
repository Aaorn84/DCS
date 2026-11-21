import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from safer_tee_query import handle
class SaferTeeTests(unittest.TestCase):
 def test_missing_long_clubs_are_asked_before_falling_back_to_seven(self):
  with patch('tee_strategy.analyze',return_value={'par':4}):
   for phrase in ('有没有安全一点的方案','稳一点','保守一点的打法'):
    text=handle({'journey':{'profile':{}}},phrase,0)
    for name in ('3号木','5号木','铁木杆','Carry'):self.assertIn(name,text)
 def test_not_a_commitment(self):self.assertIsNone(handle({},'好，1号木',0))

 def test_alternative_phrases(self):
  with patch('tee_strategy.analyze',return_value={'par':4}):
   for phrase in ('有没有其它方案','有没有其它路线','有没有其它开球方案','有没有其他方案？','还有别的打法吗','另一种开球方案','看看其他路线'):
    with self.subTest(phrase=phrase):self.assertIn('Carry',handle({'journey':{'profile':{}}},phrase,0))
 def test_unrelated_chat(self):
  self.assertIsNone(handle({},'其他球场怎么样',0))

 def test_carry_reply_is_saved_and_replans_without_reasking_all_clubs(self):
  s={'journey':{'profile':{}}}
  with patch('tee_strategy.analyze',return_value={'par':4}),patch('tee_geometry.tee_targets',return_value=[]),patch('tee_next_shot_options.compare',return_value=None):
   handle(s,'有没有其它方案',0,'ask')
   for phrase,key,distance in [('3号木210码','three_wood',210),('五号木200','five_wood',200)]:
    text=handle(s,phrase,0,'reply');self.assertIn('已记录',text)
    self.assertEqual(distance,s['journey']['profile'][key]['value']['distance'])
    self.assertEqual('carry',s['journey']['profile'][key]['value']['distance_type'])

 def test_strategy_followups_do_not_repeat_original_advice(self):
  with patch('tee_strategy.analyze',return_value={'par':4}):
   for phrase in ('还有其它策略吗','还有更安全的策略吗？','有没有更稳妥的策略','还有其他开球策略吗','还有没有保守一点的策略'):
    with self.subTest(phrase=phrase):
     s={'journey':{'profile':{}}};reply=handle(s,phrase,0,'ask')
     self.assertIsNotNone(reply);self.assertIn('Carry',reply)
     self.assertIn('tee_alternative_carry',s['journey'])

 def test_multi_club_reply_is_saved_as_carry(self):
  s={'journey':{'profile':{}}}
  with patch('tee_strategy.analyze',return_value={'par':4}),patch('tee_geometry.tee_targets',return_value=[]),patch('tee_next_shot_options.compare',return_value=None):
   handle(s,'有其它策略吗',0,'ask');reply=handle(s,'3号木210，5号木200',0,'answer')
  self.assertIn('已记录',reply)
  for key,value in [('three_wood',210),('five_wood',200)]:self.assertEqual(value,s['journey']['profile'][key]['value']['distance'])
 def test_trusted_club_reply_does_not_revert_to_driver(self):
  s={'journey':{'profile':{}}}
  with patch('tee_strategy.analyze',return_value={'par':4}):handle(s,'有其它策略吗',0,'ask')
  with patch('tee_strategy.analyze',return_value={'par':4}),patch('tee_strategy.reported_carry_clubs',return_value={'five_wood':{'label':'5号木','carry_yards':200}}),patch('tee_geometry.tee_targets',return_value=[{}]),patch('tee_next_shot_options.compare',return_value={'text':'5号木Carry约200码','options':[]}):
   reply=handle(s,'比较稳定的是5号木吧，有点小右曲',0,'stable')
  self.assertIn('5号木Carry约200码',reply);self.assertNotIn('一号木',reply)
  self.assertEqual('右曲',s['journey']['profile']['trusted_tee_club']['value']['usual_curve'])

 def test_new_alternative_omits_previously_spoken_driver(self):
  from safer_tee_query import new_alternative_text
  text=new_alternative_text('已记录这几支杆的Carry。一号木方案：Carry约240码。\n3号木方案：Carry约210码。你想选哪支杆？')
  self.assertNotIn('一号木',text);self.assertIn('3号木Carry约210码',text);self.assertNotIn('3号木方案',text)

 def test_direct_conservative_request_only_speaks_alternative(self):
  s={'journey':{'profile':{'five_wood':{'value':{'distance':220,'units':'码','distance_type':'carry'}}}}}
  offer={'text':'一号木方案：Carry约260码。\n5号木方案：Carry约220码。','options':[{'club':'一号木'},{'club':'5号木'}]}
  with patch('tee_strategy.analyze',return_value={'par':4}),patch('tee_geometry.tee_targets',return_value=[{}]),patch('tee_next_shot_options.compare',return_value=offer):
   reply=handle(s,'有没有保守方案',0,'safer')
  self.assertNotIn('一号木',reply);self.assertTrue(reply.startswith('5号木Carry约220码'))
  self.assertNotIn('方案：',reply);self.assertIn('你想用这支杆吗',reply)


 def test_already_presented_five_wood_is_not_presented_as_new(self):
  options=[{'club':'一号木','club_key':'driver','carry_yards':240},{'club':'5号木','club_key':'five_wood','carry_yards':200}]
  s={'journey':{'profile':{'five_wood':{'value':{'distance':200,'units':'码','distance_type':'carry'}}},'consultation':{'last_offer':{'options':options,'comparison_context':'same'},'phase':'tee_commit'}}}
  offer={'text':'一号木方案：Carry约240码。\n5号木方案：Carry约200码。','options':options,'comparison_context':'same'}
  with patch('tee_strategy.analyze',return_value={'par':4}),patch('tee_geometry.tee_targets',return_value=[{}]),patch('tee_next_shot_options.compare',return_value=offer):reply=handle(s,'还有其他方案吗？',0,'again')
  self.assertIn('刚才已介绍',reply);self.assertIn('没有核对到',reply);self.assertNotIn('Carry约',reply)
  self.assertEqual(options,s['journey']['consultation']['last_offer']['options'])

 def test_multi_carry_computes_once_after_all_reports(self):
  s={'journey':{'profile':{},'tee_alternative_carry':[None,None,None]}}
  with patch('tee_strategy.analyze',return_value={'par':4}),patch('tee_geometry.tee_targets',return_value=[]),patch('tee_next_shot_options.compare',return_value=None) as compute:
   handle(s,'3号木210，5号木200',0,'multi')
  self.assertEqual(1,compute.call_count)
