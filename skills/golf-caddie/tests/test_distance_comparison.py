import unittest,sys,copy
from pathlib import Path
from datetime import timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_projection as projection_tests
from journey_distance_comparison import comparison_query
class DistanceComparisonTests(unittest.TestCase):
 setUp=projection_tests.ProjectionTests.setUp
 tearDown=projection_tests.ProjectionTests.tearDown
 begin=projection_tests.ProjectionTests.begin
 def send(self,text='',gps=None):
  self.n+=1;self.clock+=timedelta(seconds=1);p=dict(protocol_version=36,type='gps' if gps else 'message',event_id='c'+str(self.n),observed_at=self.clock.isoformat(),**({'data':gps} if gps else {'text':text}));self.last=p
  return self.e.command('j','op'+str(self.n),'journey_event',p,now=self.clock.timestamp())
 def test_entire_reported_comparison_sequence(self):
  self.begin();before=copy.deepcopy(self.e.state('j'))
  for text,key in [('用一号木，下一杆还剩多少？','driver'),('下一杆还剩多少？','driver'),('3号木，下一杆还剩多少','three_wood'),('长铁杆，下一杆还剩多少？','long_iron')]:
   out=self.send(text);self.assertEqual(out['projection']['club_key'],key,text);self.assertIn('预计还剩',out['text']);self.assertNotIn('不能可靠判断',out['text'])
  after=self.e.state('j');self.assertEqual(before['facts'],after['facts']);self.assertEqual(before['journey']['profile'],after['journey']['profile']);self.assertEqual(before['journey']['consultation'],after['journey']['consultation']);self.assertEqual(after,self.e.replay('j'))
 def test_parser_understands_club_and_question_as_one_unit(self):
  for t,club in [('用一号木，下一杆还剩多少？','一号木'),('3号木，下一杆还有多远','3号木'),('长铁杆，下一杆还剩多少？','长铁杆'),('如果用三号木开球，下一杆距离多少','3号木')]:self.assertEqual(comparison_query(t)['club'],club)
 def test_plain_followup_still_uses_current_proposal(self):
  self.begin();out=self.send('下一杆还剩多少？');self.assertEqual(out['projection']['club_key'],'long_iron')
 def test_formatting_characters_are_not_unknown_intent(self):
  self.begin();out=self.send('下\u200b一杆还剩多少？');self.assertEqual(out['projection']['club_key'],'long_iron')
 def test_unicode_fullwidth_wood_query(self):
  self.begin();out=self.send('３号木，下一杆还剩多少？');self.assertEqual(out['projection']['club_key'],'three_wood')
 def test_meters_does_not_change_original_club_carry(self):
  self.begin();out=self.send('用一号木，下一杆还剩多少米？');self.assertIn('米',out['text']);self.assertEqual(out['projection']['carry_yards'],260)
 def test_other_question_types_are_not_compound_comparisons(self):
  for t in ['一号木用了多少次','用一号木，过沙需要多少','上一杆长铁打了多少','还有多少','我决定用一号木']:self.assertIsNone(comparison_query(t),t)
 def test_scores_keep_separator_and_can_be_confirmed(self):
  self.begin();out=self.send('这洞6杆，2推，0罚杆');self.assertIn('6杆',out['text']);self.send('确认记录');from round_state import fact_value
  self.assertEqual(fact_value(self.e.state('j'),'holes.1.total'),6)
 def test_acknowledgement_does_not_select_compared_driver(self):
  self.begin();before=copy.deepcopy(self.e.state('j')['journey']['consultation']);self.send('用一号木，下一杆还剩多少');self.send('好');self.assertEqual(before,self.e.state('j')['journey']['consultation'])
 def test_missing_club_carry_can_be_supplied_after_compound_query(self):
  self.begin(False);out=self.send('用一号木，下一杆还剩多少');self.assertEqual(out.get('missing_club'),'driver');out=self.send('260');self.assertEqual(out['projection']['club_key'],'driver')
 def test_dedup_rejects_reuse_for_different_club(self):
  self.begin();self.send('用一号木，下一杆还剩多少');p=copy.deepcopy(self.last);out=self.e.command('j','retry','journey_event',p,now=self.clock.timestamp());self.assertTrue(out['duplicate']);p['text']='3号木，下一杆还剩多少'
  with self.assertRaises(ValueError):self.e.command('j','bad','journey_event',p,now=self.clock.timestamp())
 def test_frozen_protocol_keeps_old_compound_query_result(self):
  self.begin();self.n+=1;self.clock+=timedelta(seconds=1);out=self.e.command('j','old','journey_event',dict(protocol_version=35,type='message',event_id='old-comparison',text='用一号木，下一杆还剩多少',observed_at=self.clock.isoformat()),now=self.clock.timestamp());self.assertIn('不能可靠判断',out['text']);self.assertEqual(self.e.state('j'),self.e.replay('j'))
if __name__=='__main__':unittest.main()
