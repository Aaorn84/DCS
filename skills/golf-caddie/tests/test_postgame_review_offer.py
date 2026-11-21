import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_postgame_summary as support
from journey import _apply_journey,view
class PostgameReviewOfferTests(unittest.TestCase):
 def apply(self,s,text):return _apply_journey(s,dict(type='message',text=text,event_id='event-'+str(s['version']),_stroke_consistency_v111=True),s['version']+1,0)
 def state(self):
  s=support.PostgameSummaryTests().state('finish_confirm');s.setdefault('session',{})['draft']=None;return s
 def test_finish_immediately_offers_review_without_feeling_question(self):
  s=self.state();r=self.apply(s,'确认结束');self.assertEqual(s['journey']['stage'],'review_offer');self.assertIn('需要对本场做个分析总结吗',r['text']);self.assertIn('分析总结本场',view(s)['choices']);self.assertTrue(s['journey']['round']['finished']);self.assertEqual(len(s['journey']['history']),1)
  r=self.apply(s,'可以');self.assertIn('11杆',r['text']);self.assertEqual(s['journey']['stage'],'postgame');self.assertFalse(s['journey']['coach']['enabled'])
 def test_decline_does_not_generate_analysis(self):
  s=self.state();self.apply(s,'确认结束');r=self.apply(s,'先不总结');self.assertEqual(s['journey']['stage'],'postgame');self.assertNotIn('得分分布',r['text'])
 def test_explicit_summary_answer_does_not_reask_offer(self):
  s=self.state();self.apply(s,'确认结束');r=self.apply(s,'分析总结本场');self.assertIn('11杆',r['text']);self.assertEqual(s['journey']['stage'],'postgame');self.assertNotIn('先不总结',r['choices'])
