import sys,unittest,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tee_dispersion import sync
class DispersionTests(unittest.TestCase):
 def fixture(self):
  origin={'latitude':0,'longitude':0,'accuracy_m':2};aim={'latitude':.002,'longitude':0};end={'latitude':.0019,'longitude':.0001,'accuracy_m':3}
  shot={'kind':'stroke','id':'shot','club':'5号木','active':True,'origin':origin,'landing':end,'confirmed_target':{'point':aim}}
  f={'scope':['r','m',1],'sequence':[shot]}
  s={'journey':{'memory_allowed':True},'evidence':{'m':{'data':{'holes':[{'number':1,'tee_bbox':[-.0001,-.0001,.0001,.0001]}]}}}}
  return s,f,shot
 def test_final_rest_deviation_and_no_duplicate(self):
  s,f,shot=self.fixture()
  with patch('projected_ledger.current',return_value=f):
   sync(s);sync(s)
   row=s['journey']['tee_dispersion_samples'][0];self.assertGreater(row['lateral_m'],0);self.assertLess(row['longitudinal_m'],0)
   self.assertEqual(1,len(s['journey']['tee_dispersion_samples']));self.assertFalse(s['journey']['tee_dispersion_summary']['5号木']['usable_for_safety_probability'])
   shot['active']=False;sync(s);self.assertEqual([],s['journey']['tee_dispersion_samples'])
 def test_missing_target_or_accuracy_excluded(self):
  for missing in ('target','accuracy'):
   s,f,shot=self.fixture()
   if missing=='target':shot.pop('confirmed_target')
   else:shot['landing'].pop('accuracy_m')
   with patch('projected_ledger.current',return_value=f):sync(s)
   self.assertEqual([],s['journey']['tee_dispersion_samples'])
 def test_simulation_does_not_calibrate_personal_model(self):
  s,f,shot=self.fixture();s['evidence']['m']['data']['reference_simulation']=True
  with patch('projected_ledger.current',return_value=f):sync(s)
  self.assertEqual({},s['journey']['tee_dispersion_summary'])
 def test_real_samples_continue_accumulating_across_next_round(self):
  from application import next_round
  s,f,shot=self.fixture();s['version']=1;s['journey'].update(stage='postgame',round={'id':'r','finished':True},profile={},history=[],number=1,coach={'enabled':False})
  source=copy.deepcopy(s['evidence']['m']['data'])
  with patch('projected_ledger.current',return_value=f):sync(s)
  next_round(s,{},2,0)
  s['journey']['round']={'id':'next','finished':False};s['evidence']={'new-map':{'data':source}}
  second=copy.deepcopy(f);second['scope']=['next','new-map',1];second['sequence'][0]['id']='second-opening'
  with patch('projected_ledger.current',return_value=second):sync(s);sync(s)
  self.assertEqual(2,len(s['journey']['tee_dispersion_samples']));self.assertEqual(2,s['journey']['tee_dispersion_summary']['5号木']['samples'])
