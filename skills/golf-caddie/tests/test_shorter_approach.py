import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_stroke_consistency as support
from journey import _apply_journey
from shorter_approach import respond
class ShorterApproachTests(unittest.TestCase):
 def test_shorter_then_wedge_suffix_commits_club_not_stroke(self):
  f=support.StrokeConsistencyTests();f.setUp()
  try:
   f.start();f.point();s=f.e.state('j');j=s['journey']
   j['consultation']=dict(phase='plan',ball_position_report='user_confirmed',lie_report='发球台')
   j['profile']['lofted_wedge_ranges']={'value':{'48':dict(low=110,high=110,units='码')}}
   event=dict(type='message',event_id='shorter',text='想打短一点',observed_at=f.clock.isoformat(),_stroke_consistency_v111=True,_dialogue_v69=True,_dialogue_v70=True)
   r=_apply_journey(s,event,s['version']+1,f.clock.timestamp())
   self.assertIn('更短的落点',r['text']);self.assertFalse(j.get('player_decisions'))
   with patch('tee_strategy.analyze',return_value=None):
    r=_apply_journey(s,dict(event,event_id='wedge',text='48吧'),s['version']+1,f.clock.timestamp())
   self.assertIn('48度杆',r['text']);self.assertIn('110码',r['text'])
   d=j['player_decisions'][-1];self.assertEqual(d['club'],'48度杆');self.assertFalse(d['execution_confirmed'])
   self.assertEqual(d['target'],'shorter_landing')
  finally:f.tearDown()
 def test_not_parsed_as_completed_shot_or_question(self):
  for text in ('刚才打短了一点','想打短一点可以吗','不想打短一点'):
   self.assertIsNone(respond({'journey':{'consultation':{'phase':'plan'}}},text))
