import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import initial
from journey import _apply_journey
class SkipGoalTests(unittest.TestCase):
 def state(self,stage):
  s=initial();s['journey']={'stage':stage,'profile':{},'quiet':False,'round':{'id':'r','course':'synthetic-journey','goal':'existing'}};return s
 def turn(self,s,kind,text=''):
  return _apply_journey(s,dict(type=kind,event_id='skip-goal',text=text,observed_at='1970-01-01T00:00:00+00:00'),1,0)
 def test_hole_selection_goes_directly_to_ready(self):
  s=self.state('start_hole');r=self.turn(s,'message','1')
  self.assertEqual('ready',s['journey']['stage']);self.assertNotIn('今天想怎样打',r['text'])
 def test_existing_pending_goal_resumes_ready_and_keeps_history(self):
  s=self.state('goal');r=self.turn(s,'resume')
  self.assertEqual('ready',s['journey']['stage']);self.assertEqual('existing',s['journey']['round']['goal']);self.assertNotIn('今天想怎样打',r['text'])
