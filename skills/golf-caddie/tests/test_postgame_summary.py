import sys,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from postgame_summary import review,detailed_review,requested
from journey import _apply_journey
from round_state import initial
class PostgameSummaryTests(unittest.TestCase):
 def state(self,stage='coach_consent'):
  s=initial();s['journey']=dict(stage=stage,quiet=False,round=dict(id='r',finished=True),profile={},memory_allowed=True,coach=dict(enabled=False,plan=None),history=[],number=1)
  s['facts'].update({'context.course_snapshot':dict(value='map',valid=True)})
  s['evidence']['map']={'data':{'holes':[dict(number=1,par=4),dict(number=10,par=5)]}}
  for hole,total,putts,penalties in [(1,4,2,0),(10,7,3,1)]:
   for key,value in dict(total=total,putts=putts,penalties=penalties).items():s['facts'][f'holes.{hole}.{key}']=dict(value=value,valid=True)
  return s
 def test_summary_is_factual_and_partial(self):
  text=detailed_review(self.state());self.assertIn('11杆、5推、1罚杆',text);self.assertIn('前九（已记1/9洞）',text);self.assertIn('后九（已记1/9洞）',text);self.assertIn('第1洞，平标准杆',text);self.assertIn('三推',text);self.assertIn('尚未记分',text)
 def test_review_does_not_answer_coach_consent_or_modify_scores(self):
  for stage in ('coach_consent','postgame'):
   s=self.state(stage);before=copy.deepcopy(s)
   r=_apply_journey(s,dict(type='message',text='给这场球做个分析总结。',event_id='summary',observed_at='2026-11-20T12:00:00Z',_stroke_consistency_v111=True),s['version']+1,0)
   self.assertIn('11杆',r['text']);self.assertEqual(s['journey']['stage'],stage);self.assertEqual(s['journey']['coach'],before['journey']['coach']);self.assertEqual(s['facts'],before['facts'])
 def test_unknown_reply_is_not_coach_rejection(self):
  s=self.state();r=_apply_journey(s,dict(type='message',text='先聊聊',event_id='other',_stroke_consistency_v111=True),1,0)
  self.assertEqual(s['journey']['stage'],'coach_consent');self.assertNotIn('好，不开启',r['text'])
 def test_natural_phrases(self):
  for text in ('给这场球做个分析总结。','分析一下今天打得怎么样','本场复盘','赛后总结','分析总结','分析','总结','复盘','分析总结一下'):self.assertTrue(requested(text))
  self.assertFalse(requested('我不想总结'));self.assertFalse(requested('不需要分析本场'));self.assertFalse(requested('先不总结本场'))
 def test_missing_is_not_zero(self):
  s=self.state();s['facts'].pop('holes.10.putts');self.assertIn('2推（1洞未报）',detailed_review(s))

class ShortSummaryRequestTests(PostgameSummaryTests):
 def test_bare_summary_in_postgame(self):
  s=self.state('postgame')
  r=_apply_journey(s,dict(type='message',text='分析总结',event_id='short-summary',_stroke_consistency_v111=True),s['version']+1,0)
  self.assertIn('11杆',r['text']);self.assertNotIn('我在听',r['text'])
