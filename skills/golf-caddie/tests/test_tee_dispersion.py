import sys,unittest,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tee_dispersion import sync,capture
class DispersionTests(unittest.TestCase):
 def fixture(self):
  origin={'latitude':0,'longitude':0,'accuracy_m':2};aim={'latitude':.002,'longitude':0};end={'latitude':.0019,'longitude':.0001,'accuracy_m':3}
  shot={'kind':'stroke','id':'shot','club':'5号木','active':True,'origin':origin,'landing':end,'confirmed_target':{'point':aim}}
  f={'scope':['r','m',1],'sequence':[shot]}
  s={'journey':{'memory_allowed':True},'evidence':{'m':{'data':{'holes':[{'number':1,'tee_bbox':[-.0001,-.0001,.0001,.0001]}]}}}}
  return s,f,shot
 def test_final_rest_deviation_and_no_duplicate(self):
  s,f,shot=self.fixture()
  with patch('ball_rules.current',return_value=f):
   sync(s);sync(s)
   row=s['journey']['tee_dispersion_samples'][0];self.assertGreater(row['lateral_m'],0);self.assertLess(row['longitudinal_m'],0)
   self.assertEqual(1,len(s['journey']['tee_dispersion_samples']));self.assertFalse(s['journey']['tee_dispersion_summary']['5号木']['usable_for_safety_probability'])
   shot['active']=False;sync(s);self.assertEqual([],s['journey']['tee_dispersion_samples'])
 def test_missing_target_or_accuracy_excluded(self):
  for missing in ('target','accuracy'):
   s,f,shot=self.fixture()
   if missing=='target':shot.pop('confirmed_target')
   else:shot['landing'].pop('accuracy_m')
   with patch('ball_rules.current',return_value=f):sync(s)
   self.assertEqual([],s['journey']['tee_dispersion_samples'])
 def test_simulation_does_not_calibrate_personal_model(self):
  s,f,shot=self.fixture();s['evidence']['m']['data']['reference_simulation']=True
  with patch('ball_rules.current',return_value=f):sync(s)
  self.assertEqual({},s['journey']['tee_dispersion_summary'])
 def test_capture_requires_final_scope_club_and_position(self):
  s,f,shot=self.fixture();j=s['journey'];j['last_consultation']={'decision':{'aim_point':shot['confirmed_target']['point'],'club':'5号木','hole':1,'position_version':2}}
  j['player_decisions']=[{'round_scope':f['scope'],'club':'5号木','event_id':'decision'}];s['facts']={'context.device_position':{'version':2}}
  f['open_shot']={'club':'5号木','origin':shot['origin']};capture(s,f);self.assertIn('confirmed_target',f['open_shot'])
  f['open_shot'].pop('confirmed_target');s['facts']['context.device_position']['version']=3;capture(s,f);self.assertNotIn('confirmed_target',f['open_shot'])
