import sys,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_technical_stats import calculate
from round_state import canonical
class RoundTechnicalStatsTests(unittest.TestCase):
 def fixture(self):
  def point(lat):return dict(latitude=lat,longitude=0,accuracy_m=0)
  def zone(id,surface,low,high):return dict(id=id,surface=surface,verified=True,source='test',geometry=dict(type='Polygon',coordinates=[[[-.0002,low],[.0002,low],[.0002,high],[-.0002,high],[-.0002,low]]]))
  tee,fair,green=point(0),point(.001),point(.002)
  hole=dict(number=1,par=4,simulation_positions={'tee':tee},surface_zones=[zone('f','fairway',.0005,.0015),zone('g','green',.0018,.0022)])
  seq=[dict(kind='stroke',id='a',ball_id='original',origin=tee,landing=fair),dict(kind='stroke',id='b',ball_id='original',origin=fair,landing=green)]
  flow=dict(sequence=seq,balls={'original':{'status':'active'}})
  s=dict(facts={'context.course_snapshot':dict(value='map',valid=True)},evidence={'map':{'data':{'holes':[hole]}}},journey={'round':{'id':'r'},'ball_rules':{canonical(['r','map',1]):flow}})
  score=[dict(hole=1,total=4,putts=2)]
  return s,score,{1:4},flow
 def test_fir_gir_and_putts_from_actual_shots(self):
  s,scores,pars,f=self.fixture();r=calculate(s,scores,pars)
  self.assertEqual(r['fir']['value'],1);self.assertEqual(r['gir']['value'],1);self.assertEqual(r['holes'][0]['green_stroke'],2);self.assertEqual(r['putts_per_gir']['value'],2)
 def test_penalty_counts_before_green(self):
  s,scores,pars,f=self.fixture();f['sequence'].insert(1,dict(kind='penalty',id='p',ball_id='original',amount=1));scores[0].update(total=5)
  r=calculate(s,scores,pars);self.assertEqual(r['holes'][0]['green_stroke'],3);self.assertEqual(r['gir']['value'],0)
 def test_discarded_provisional_does_not_enter_count(self):
  s,scores,pars,f=self.fixture();f['balls']['provisional']={'status':'discarded'};extra=dict(f['sequence'][0],id='p',ball_id='provisional');f['sequence'].insert(1,extra)
  self.assertEqual(calculate(s,scores,pars)['holes'][0]['green_stroke'],2)
 def test_unknown_earlier_landing_cannot_establish_gir_miss(self):
  s,scores,pars,f=self.fixture();f['sequence'][0]['landing']=None;f['sequence'].insert(1,dict(f['sequence'][0],id='extra'))
  r=calculate(s,scores,pars);self.assertIsNone(r['gir']['value']);self.assertIsNone(r['fir']['value'])
 def test_scores_alone_do_not_invent_gir(self):
  s,scores,pars,f=self.fixture();f['sequence']=[];r=calculate(s,scores,pars);self.assertIsNone(r['gir']['value']);self.assertEqual(r['gir']['missing_holes'],[1])
 def test_first_green_not_last_green_is_used(self):
  s,scores,pars,f=self.fixture();f['sequence'][0]['landing']=f['sequence'][1]['landing'];f['sequence'].append(dict(f['sequence'][1],id='c'));self.assertEqual(calculate(s,scores,pars)['holes'][0]['green_stroke'],1)
 def test_missing_tee_start_does_not_mislabel_later_shot_as_drive(self):
  s,scores,pars,f=self.fixture();f['sequence'].pop(0);r=calculate(s,scores,pars);self.assertIsNone(r['fir']['value']);self.assertIsNone(r['gir']['value'])
