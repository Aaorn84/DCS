import unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from gps_transition import observe
from round_state import Engine
from datetime import datetime, timezone
C={'course_id':'track','map_version':'1','crs':'WGS84','holes':[
 {'number':1,'par':4,'bbox':[120.999,30.999,121.004,31.002],'green_bbox':[121.0015,30.9995,121.0025,31.0005],'objects':[{'id':'g1','kind':'green_center','latitude':31,'longitude':121.002}]},
 {'number':2,'par':4,'bbox':[121.004,30.999,121.009,31.002],'tee_bbox':[121.0045,30.9995,121.0055,31.0005],'objects':[{'id':'g2','kind':'green_center','latitude':31,'longitude':121.008}]}]}
def pos(x=121.005,accuracy=2):return dict(latitude=31,longitude=x,accuracy_m=accuracy)
class TrackTests(unittest.TestCase):
 def setUp(self):self.t={};self.c=copy.deepcopy(C)
 def fix(self,t,x=121.005,accuracy=2,now=None):return observe(self.t,self.c,pos(x,accuracy),t,t if now is None else now,1)
 def departure(self):self.fix(0,121.002);self.fix(15,121.004)
 def test_green_departure_then_dwell(self):
  self.departure();self.assertIsNone(self.fix(25)['confirmed_hole']);self.fix(33)
  self.assertEqual(self.fix(41)['confirmed_hole'],2)
 def test_single_fix_and_short_stop(self):
  self.departure();self.fix(25);self.fix(26);self.assertIsNone(self.fix(27)['confirmed_hole'])
 def test_no_green_history(self):
  for t in (0,8,16):self.assertEqual(self.fix(t)['reason'],'green_departure_not_observed')
 def test_duplicates_do_not_accumulate(self):
  self.departure();self.fix(25)
  for _ in range(4):self.assertEqual(self.fix(25)['reason'],'duplicate_fix')
  self.assertEqual(self.t['pending']['fixes'],1)
 def test_accuracy_breaks_dwell(self):
  self.departure();self.fix(25);self.fix(33,accuracy=30)
  self.fix(41);self.fix(49);self.assertEqual(self.t['pending']['fixes'],2)
 def test_gap_breaks_dwell(self):
  self.departure();self.fix(25);self.fix(60);self.assertEqual(self.t['pending']['fixes'],1)
 def test_passing_tee_resets(self):
  self.departure();self.fix(25);self.fix(33,121.006);self.fix(41)
  self.assertEqual(self.t['pending']['fixes'],1)
 def test_jump_does_not_move_last_fix(self):
  self.departure();r=self.fix(16,121.1)
  self.assertEqual(r['reason'],'implausible_jump');self.assertEqual(self.t['last']['timestamp'],15)
 def test_overlap_does_not_switch(self):
  self.departure();self.c['holes'][0]['tee_bbox']=self.c['holes'][1]['tee_bbox']
  self.assertEqual(self.fix(25)['reason'],'outside_or_ambiguous_tee')
 def test_missing_tee_geometry(self):
  self.c['holes'][1].pop('tee_bbox');self.assertEqual(self.fix(0)['reason'],'outside_or_ambiguous_tee')
 def test_stale_and_reverse_time(self):
  self.fix(10,121.002);self.assertFalse(self.fix(9)['accepted_position'])
  self.assertEqual(self.fix(20,now=100)['reason'],'stale_or_inaccurate')
 def test_uncertainty_at_boundary(self):
  self.departure();self.assertEqual(self.fix(25,121.0045)['reason'],'outside_or_ambiguous_tee')
 def test_no_green_map_allows_next_tee_evidence_only(self):
  self.c['holes'][0].pop('green_bbox')
  for t in (0,8):self.fix(t)
  self.assertEqual(self.fix(16)['confirmed_hole'],2)
class SessionTrackTests(unittest.TestCase):
 def test_prompt_once_and_replay(self):
  e=Engine(':memory:','test');e.create('r');n=0;base=1793923200
  def send(kind,t,**kw):
   nonlocal n
   n+=1
   return e.command('r',str(n),'session_event',dict(type=kind,event_id='e'+str(n),observed_at=datetime.fromtimestamp(base+t,timezone.utc).isoformat(),**kw),now=base+t)
  send('course',0,data=C);send('voice',0,text='换洞时提醒记分')
  send('gps',0,data=pos(121.002));send('gps',15,data=pos(121.004));send('gps',25,data=pos());send('gps',33,data=pos())
  r=send('gps',41,data=pos());self.assertIn('上一洞',r['text'])
  self.assertEqual(send('gps',49,data=pos())['text'],'')
  self.assertNotIn('holes.1.total',e.state('r')['facts']);self.assertEqual(e.state('r'),e.replay('r'));e.close()
if __name__=='__main__':unittest.main()
