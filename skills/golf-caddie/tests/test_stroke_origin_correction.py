import sys,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_hole_recap as support
from stroke_origin_correction import apply
from shot_review_evidence import replay_origin_conflicts
from round_state import canonical
from shot_evidence import haversine
from journey import round_records
class StrokeOriginCorrectionTests(unittest.TestCase):
 def fixture(self):
  s,f=support.HoleRecapTests().state();s['journey']['profile']={};s['version']=1;f['revision']=111
  shot=f['sequence'][2];shot.update(pair_ids=['bad','end'],confirmation_record_id='confirmation')
  origin=dict(round_id='r',course='map',hole=1,id='bad',origin='rules_relief_position',point=copy.deepcopy(shot['origin']),evidence_ids=['bad'])
  end=dict(origin,id='end',point=copy.deepcopy(shot['landing']),evidence_ids=['end'])
  for key,point in [('bad',shot['origin']),('end',shot['landing'])]:s['evidence'][key]=dict(active=True,phase='final',revision=1,observed_at='2026-11-19T00:00:00Z',data=copy.deepcopy(point))
  s['journey'].update(confirmed_shot_distances=[dict(id='confirmation',scope=['r','map',1],valid=True,pair_ids=['bad','end'],endpoints=[copy.deepcopy(origin),copy.deepcopy(end)],total_horizontal_m=61,simulated_landing=True)],shot_location_candidates=[copy.deepcopy(origin),copy.deepcopy(end)],previous_club_reports={canonical(['r','map',1,'bad','end']):{'club':'一号木'}})
  event=dict(type='correct_stroke_origin_to_tee',event_id='fix-tee',protocol_version=111,observed_at='2026-11-21T00:00:00Z',data=dict(round_id='r',hole=1,stroke_number=3,stroke_id='b'))
  return s,f,event
 def test_updates_origin_distance_and_all_live_references(self):
  s,f,e=self.fixture();before=copy.deepcopy(s);shot=f['sequence'][2];landing=copy.deepcopy(shot['landing']);tee=s['evidence']['map']['data']['holes'][0]['simulation_positions']['tee'];expected=haversine(tee,landing)
  apply(s,e,0);self.assertEqual(shot['landing'],landing);self.assertAlmostEqual(shot['distance_m'],expected);self.assertEqual(replay_origin_conflicts(f),{})
  record=s['journey']['confirmed_shot_distances'][0];self.assertEqual(record['pair_ids'],shot['pair_ids']);self.assertAlmostEqual(record['total_horizontal_m'],expected)
  self.assertEqual(record['endpoints'][0]['point']['latitude'],tee['latitude']);self.assertEqual(s['facts'],before['facts']);self.assertEqual(f['sequence'][0],before['journey']['ball_rules'][canonical(['r','map',1])]['sequence'][0])
  rows=round_records(s)['clubs'];row=next(r for r in rows if r.get('stroke_number')==3);self.assertAlmostEqual(row['total_horizontal_m'],expected)
  self.assertEqual(s['evidence']['bad'],before['evidence']['bad'])
 def test_wrong_round_rejected_before_mutation(self):
  s,f,e=self.fixture();e['data']['round_id']='other';before=copy.deepcopy(s)
  with self.assertRaises(ValueError):apply(s,e,0)
  self.assertEqual(s,before)
