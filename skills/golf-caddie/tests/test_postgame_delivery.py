import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_postgame_summary as support
from postgame_delivery import handle,present,CHOICES
from postgame_summary import review
from journey import _apply_journey,view
class PostgameDeliveryTests(unittest.TestCase):
 def state(self):return support.PostgameSummaryTests().state('postgame')
 def send(self,s,text):return _apply_journey(s,dict(type='message',event_id='event-'+str(len(text)),text=text,_stroke_consistency_v111=True),s['version']+1,0)
 def test_brief_summary_and_complete_details_are_separate(self):
  s=self.state();r=self.send(s,'分析总结');self.assertIn('11杆',r['text']);self.assertLess(len(r['text']),260);self.assertNotIn('FIR',r['text']);self.assertNotIn('得分分布',r['text']);self.assertEqual(r['choices'],CHOICES)
  card=present(s);self.assertIn('得分分布',card['details']);self.assertIn('FIR',card['details']);self.assertIsNone(card['expand_event']);self.assertEqual(view(s)['round_review'],card);self.assertEqual(view(s)['choices'],CHOICES)
 def test_details_expand_in_card_instead_of_reading_all_stats(self):
  s=self.state();r=self.send(s,'看详细数据');self.assertIn('已展开',r['text']);self.assertLess(len(r['text']),80);self.assertIsNotNone(present(s)['expand_event'])
 def test_followup_hole_prompt_and_number(self):
  s=self.state();r=self.send(s,'复盘某一洞');self.assertIn('哪一洞',r['text']);r=self.send(s,'10');self.assertIn('第10洞7杆',r['text']);self.assertNotIn('postgame_followup',s['journey'])
 def test_direct_hole_request(self):
  s=self.state();r=self.send(s,'复盘第一洞');self.assertIn('第1洞4杆',r['text']);self.assertNotIn('全场',r['text'])
 def test_next_round_advice_does_not_enable_coaching(self):
  s=self.state();before=copy.deepcopy(s['journey']['coach']);r=self.send(s,'下场怎么打');self.assertIn('一个重点',r['text']);self.assertEqual(s['journey']['coach'],before)
 def test_one_main_focus(self):
  s=self.state();text=review(s);self.assertIn('推杆过程',text);self.assertNotIn('罚杆，最值得',text)
 def test_no_claim_about_putting_cause_or_promised_saved_strokes(self):
  s=self.state();text=review(s);self.assertNotIn('速度控制差',text);self.assertNotIn('能省',text)

 def test_default_summary_asks_followup_question(self):
  s=self.state();r=self.send(s,'分析总结');self.assertTrue(r['text'].endswith('您需要我给您播报一下详细数据，还是我们一起来复盘一下某一洞？'));self.assertIn('播报详细数据',r['choices'])
 def test_spoken_details_returns_full_statistics(self):
  for words in ('播报详细数据','播报一下详细数据','详细数据'):
   s=self.state();self.send(s,'分析总结');r=self.send(s,words);self.assertIn('得分分布',r['text']);self.assertIn('FIR',r['text']);self.assertIsNotNone(present(s)['expand_event'])
 def test_short_review_answer_after_summary_asks_which_hole(self):
  s=self.state();self.send(s,'分析总结');r=self.send(s,'复盘一下');self.assertIn('哪一洞',r['text']);self.assertNotIn('11杆',r['text'])

 def test_course_local_hole_aliases_use_current_route(self):
  for word in ('A5','a5','A #5','Ａ５','A区第5洞','复盘A5'):
   s=self.state();s['evidence']['map']['data']['holes'][0]['source_name']='A #5'
   self.send(s,'复盘某一洞');r=self.send(s,word)
   self.assertIn('A5 · 第1洞4杆',r['text']);self.assertNotIn('postgame_followup',s['journey'])
 def test_back_nine_alias_does_not_use_local_number_as_round_number(self):
  s=self.state();s['evidence']['map']['data']['holes'][1]['source_name']='B #1'
  r=self.send(s,'B1');self.assertIn('B1 · 第10洞7杆',r['text'])
 def test_unknown_course_alias_keeps_followup(self):
  s=self.state();r=self.send(s,'C5');self.assertIn('未找到C5',r['text']);self.assertEqual(s['journey']['postgame_followup'],'hole')
