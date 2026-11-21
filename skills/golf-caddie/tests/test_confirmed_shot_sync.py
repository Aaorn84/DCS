import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from confirmed_shot_sync import sync_flow
from round_state import canonical
from ball_rules import rows
class ConfirmedShotSyncTests(unittest.TestCase):
 def fixture(self):
  key=['r','c',4]
  points=[dict(latitude=31,longitude=121+n*.0005,accuracy_m=2) for n in range(3)]
  ends=[dict(id='p'+str(n),point=p,evidence_ids=['p'+str(n)]) for n,p in enumerate(points)]
  records=[dict(id='d'+str(n),scope=key,pair_ids=[ends[n]['id'],ends[n+1]['id']],endpoints=ends[n:n+2],valid=True,confirmation_event_id='yes'+str(n),total_horizontal_m=45+n,club=None) for n in range(2)]
  reports={canonical([*key,*records[n]['pair_ids']]):{'club':club} for n,club in enumerate(['7号铁','58度杆'])}
  state={'evidence':{p['id']:{'active':True,'phase':'final'} for p in ends},'journey':{'confirmed_shot_distances':records,'previous_club_reports':reports}}
  flow=dict(scope=key,revision=111,sequence=[],incidents=[],pending=None,balls={'original':{'status':'in_play'}},active_ball='original')
  return state,flow
 def test_two_explicit_confirmations_recover_club_and_distance(self):
  state,flow=self.fixture();sync_flow(state,flow)
  self.assertEqual(['7号铁','58度杆'],[r['club'] for r in rows(flow)])
  self.assertEqual([45,46],[r['total_horizontal_m'] for r in rows(flow)])
  before=copy.deepcopy(flow);sync_flow(state,flow);self.assertEqual(before,flow)
 def test_updates_existing_identity_without_duplicate(self):
  state,flow=self.fixture();sync_flow(state,flow)
  for stroke in flow['sequence']:stroke.update(club=None,distance_m=None)
  sync_flow(state,flow);self.assertEqual(2,len(flow['sequence']))
  self.assertEqual([45,46],[r['total_horizontal_m'] for r in rows(flow)])
 def test_revoked_and_score_inferred_are_not_execution(self):
  state,flow=self.fixture()
  state['journey']['confirmed_shot_distances'][0]['valid']=False
  state['journey']['confirmed_shot_distances'][1]['inferred_from_score']=True
  sync_flow(state,flow);self.assertEqual([],flow['sequence'])
 def test_does_not_assign_unmatched_record_to_incident_ball(self):
  state,flow=self.fixture();flow['incidents']=[{'id':'ob'}]
  sync_flow(state,flow);self.assertEqual([],flow['sequence'])
