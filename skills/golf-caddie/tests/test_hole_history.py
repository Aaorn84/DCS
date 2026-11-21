import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from hole_history import archive_current,records,assess,note,_signature
from round_state import canonical
from tee_geometry import planning_geometry_cache
class HoleHistoryTests(unittest.TestCase):
 def point(self,yards):return dict(latitude=yards*.9144/111195,longitude=0,accuracy_m=0)
 def state(self):
  tee=self.point(0);green=dict(self.point(400),kind='green_center');hole=dict(number=1,par=4,published_yardage=400,objects=[green],simulation_positions={'tee':tee,'green':green})
  return dict(facts={'context.course_snapshot':dict(value='map',valid=True),'context.active_hole':dict(value=1,valid=True),'context.device_position':dict(value=tee,valid=True,version=1)},evidence={'map':{'data':{'course_id':'course-a','holes':[hole]}}},journey=dict(round=dict(id='now',course='course-a',tee='蓝Tee',finished=False),history=[],ball_rules={},profile={},memory_allowed=True))
 def history(self,s,rid='old',cause='ob',club='一号木',origin=0,landing=260,phase='closed',cancelled=False):
  hole=s['evidence']['map']['data']['holes'][0]
  shot=dict(id='shot',club=club,origin=self.point(origin),landing=self.point(landing),hazards=[cause] if cause else [],landing_surface=None if cause else 'fairway',distance_kind='total_horizontal_not_carry')
  entry=dict(round=dict(id=rid,course='course-a',tee='蓝台',finished=True),hole_history={'1':dict(signature=_signature(hole),shots=[shot])})
  s['journey']['history'].append(entry);return entry
 def test_single_miss_is_note_without_weight(self):
  s=self.state();self.history(s);a=assess(s,1,self.point(0),self.point(260),'1号木')
  self.assertEqual(a['weight'],0);self.assertEqual(a['failures'],1);self.assertEqual('',note(s,1,self.point(0),self.point(260),'一号木'))
 def test_repeated_misses_raise_weight_without_changing_carry(self):
  s=self.state();self.history(s,'old1');self.history(s,'old2','water');old=copy.deepcopy(s['journey']['profile']);a=assess(s,1,self.point(0),self.point(260),'一号木')
  self.assertEqual(a['weight'],1);self.assertEqual(a['failures'],2);self.assertEqual(s['journey']['profile'],old)
 def test_same_round_and_duplicate_history_not_reused(self):
  s=self.state();self.history(s,'now');entry=self.history(s,'old');s['journey']['history'].append(copy.deepcopy(entry));self.assertEqual(assess(s,1,self.point(0),self.point(260),'一号木')['failures'],1)
 def test_wrong_course_tee_hole_geometry_and_position_are_isolated(self):
  for change in ('course','tee','hole','geometry','origin'):
   s=self.state();e=self.history(s)
   if change=='course':e['round']['course']='other'
   if change=='tee':e['round']['tee']='红台'
   if change=='hole':e['hole_history']['2']=e['hole_history'].pop('1')
   if change=='geometry':e['hole_history']['1']['signature']='changed'
   origin=self.point(100) if change=='origin' else self.point(0)
   self.assertEqual(assess(s,1,origin,self.point(260),'一号木')['weight'],0);self.assertEqual(assess(s,1,origin,self.point(260),'一号木')['samples'],0)
 def test_different_club_does_not_inherit_club_specific_failure(self):
  s=self.state();self.history(s,'old1');self.history(s,'old2');self.assertEqual(assess(s,1,self.point(0),self.point(240),'3号木')['weight'],0)
 def test_success_note_does_not_turn_total_distance_into_carry(self):
  s=self.state();self.history(s,cause=None);text=note(s,1,self.point(0),self.point(260),'一号木');self.assertEqual('',text);self.assertEqual(assess(s,1,self.point(0),self.point(260),'一号木')['weight'],0)
 def test_only_recent_five_matching_completed_rounds_affect_strategy(self):
  s=self.state()
  for i in range(3):self.history(s,'old'+str(i),cause='ob')
  for i in range(5):self.history(s,'recent'+str(i),cause=None)
  self.history(s,'other-course')['round']['course']='other'
  self.history(s,'other-tee')['round']['tee']='红Tee'
  self.history(s,'unfinished')['round']['finished']=False
  self.history(s,'now')
  self.assertEqual({f'recent{i}' for i in range(5)},{r['round_id'] for r in records(s,1)})
  result=assess(s,1,self.point(0),self.point(260),'一号木')
  self.assertEqual(5,result['samples']);self.assertEqual(0,result['failures']);self.assertEqual(0,result['weight'])
  self.assertEqual(12,len(s['journey']['history']))
 def test_missing_hole_or_changed_geometry_does_not_extend_window(self):
  s=self.state();self.history(s,'older-ob')
  for i in range(5):
   entry=self.history(s,'recent'+str(i),cause=None)
   if i==0:entry['hole_history']['1']['signature']='changed'
   if i==1:entry['hole_history']={}
  rows=records(s,1)
  self.assertEqual({'recent2','recent3','recent4'},{r['round_id'] for r in rows})
 def test_older_shot_archives_are_not_loaded_and_duplicates_do_not_use_slots(self):
  class Unreadable(dict):
   def get(self,*args):raise AssertionError('Older archive should not be read')
  s=self.state();self.history(s,'older')['hole_history']=Unreadable()
  for i in range(5):self.history(s,'recent'+str(i),cause=None)
  s['journey']['history'].append(copy.deepcopy(s['journey']['history'][-1]))
  @planning_geometry_cache
  def check():
   rows=records(s,1);self.assertEqual(5,len(rows));self.assertEqual(rows,records(s,1))
  check()
 def test_disabled_memory_ignores_records(self):
  s=self.state();self.history(s);s['journey']['memory_allowed']=False;self.assertEqual(records(s,1),[])
 def test_tee_comparison_uses_repeat_risk_but_not_single_error(self):
  from tee_next_shot_options import compare
  for misses,expected in [(1,'一号木'),(2,'3号木')]:
   s=self.state()
   for i in range(misses):self.history(s,'old'+str(i))
   targets=[dict(club_key=key,club=club,carry_yards=carry,aim_point=self.point(carry),width_m=30,crossing_m=None,offset=0,reference=None) for key,club,carry in [('driver','一号木',260),('three_wood','3号木',250)]]
   a=dict(course_evidence='map',hole=1,position_version=1)
   r=compare(s,a,targets,'码');self.assertEqual(r['options'][0]['club'],expected)
 def test_archive_excludes_cancelled_and_uncertain_incidents(self):
  for cancelled,penalty,expected in [(False,True,['ob']),(True,True,[]),(False,False,[])]:
   s=self.state();s['journey']['round'].update(id='old',finished=True);s['journey']['history']=[dict(round=copy.deepcopy(s['journey']['round']))]
   sequence=[dict(id='shot',kind='stroke',ball_id='original',club='一号木',origin=self.point(0),landing=self.point(260),active=True)]
   if penalty:sequence.append(dict(id='pen',kind='penalty',amount=1,ball_id='original',incident_id='incident',active=True))
   incident=dict(id='incident',shot_id='shot',cause='ob',phase='closed',status='cancelled' if cancelled else 'active')
   s['journey']['ball_rules'][canonical(['old','map',1])]=dict(scope=['old','map',1],sequence=sequence,incidents=[incident],balls={'original':{'status':'in_play'}},pending=None)
   archive_current(s);shots=s['journey']['history'][0]['hole_history']['1']['shots'];self.assertEqual(shots[0]['hazards'],expected)

class HoleHistoryReplayTests(unittest.TestCase):
 def test_finished_round_archive_survives_next_round_and_replays(self):
  import test_stroke_consistency as support
  from phoenix_demo import preview
  f=support.StrokeConsistencyTests();f.setUp()
  try:
   f.start();f.select_and_sound();f.send('果岭上');f.send(type='gps',data=dict(preview(4)['positions']['green'],simulation_source='map_click'))
   f.send('结束球局');f.send('确认结束')
   state=f.e.state('j');self.assertEqual(state['journey']['stage'],'review_offer')
   history=state['journey']['history'][-1];self.assertTrue(history['hole_history'].get('4',{}).get('shots'))
   old=copy.deepcopy(history['hole_history']);f.send('先不总结')
   from journey import _apply_journey
   legacy=copy.deepcopy(f.e.state('j'));legacy['journey']['history'][-1].pop('hole_history');legacy['journey']['history'][-1].pop('hole_history_version')
   _apply_journey(legacy,dict(type='next_round',event_id='legacy-archive',_stroke_consistency_v111=True),legacy['version']+1,0)
   self.assertEqual(legacy['journey']['history'][-1]['hole_history'],old)
   f.send(type='next_round')
   state=f.e.state('j');self.assertEqual(state['journey']['history'][-1]['hole_history'],old);self.assertEqual(state,f.e.replay('j'))
  finally:f.tearDown()

class SilentHistoryTests(unittest.TestCase):
 point=HoleHistoryTests.point
 state=HoleHistoryTests.state
 history=HoleHistoryTests.history
 def test_repeated_risk_still_affects_rank_without_narration(self):
  from hole_history import selection_note
  s=self.state();self.history(s,'a');self.history(s,'b')
  self.assertGreater(assess(s,1,self.point(0),self.point(260),'一号木')['weight'],0)
  self.assertEqual('',note(s,1,self.point(0),self.point(260),'一号木'))
  self.assertEqual('',selection_note(s,1,self.point(0),[],{}))
