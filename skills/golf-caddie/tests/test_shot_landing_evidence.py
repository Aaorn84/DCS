import sys,copy,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from shot_landing_evidence import classify,wording
from round_state import canonical
from hole_recap import review
import test_round_technical_stats as support
class LandingEvidenceTests(unittest.TestCase):
 def fixture(self):
  s,scores,pars,f=support.RoundTechnicalStatsTests().fixture();hole=s['evidence']['map']['data']['holes'][0];hole['surface_zones'][0]['surface']='bunker';s['journey']['profile']={};f['scope']=['r','map',1];f['incidents']=[]
  f['sequence'][0]['club']='P杆';f['sequence'][1]['club']='58度杆'
  for key,value in dict(total=4,putts=2,penalties=0).items():s['facts'][f'holes.1.{key}']=dict(value=value,valid=True)
  return s,hole,f
 def test_map_bunker_is_explicit_in_recap(self):
  s,h,f=self.fixture();a=classify(s,h,f['sequence'][0]);self.assertEqual(a['kind'],'bunker');self.assertIn('地图',wording(a));text=review(s,1);self.assertIn('关键落点是第1杆P杆',text);self.assertIn('沙坑内',text);self.assertIn('第2杆用58度杆从该沙坑位置打到果岭',text)
 def test_user_confirmation_overrides_map_and_survives_later_report(self):
  s,h,f=self.fixture();first=f['sequence'][0];first['landing_report']=dict(stroke_id=first['id'],scope=canonical(['r','map',1]),lie='长草');s['journey']['reported_landing']=dict(stroke_id='later',scope=canonical(['r','map',2]),lie='果岭')
  a=classify(s,h,first);self.assertEqual(a['kind'],'rough');self.assertEqual(a['source'],'user_report');self.assertNotIn('沙坑内',review(s,1))
 def test_wrong_scope_report_is_ignored(self):
  s,h,f=self.fixture();first=f['sequence'][0];first['landing_report']=dict(stroke_id=first['id'],scope=canonical(['other','map',1]),lie='果岭');self.assertEqual(classify(s,h,first)['kind'],'bunker')
 def test_explicit_green_report_can_count_before_gps_landing(self):
  from round_technical_stats import calculate
  s,h,f=self.fixture();last=f['sequence'][1];last['landing']=None;last['landing_report']=dict(stroke_id=last['id'],scope=canonical(['r','map',1]),lie='果岭')
  a=calculate(s,[dict(hole=1,total=4,putts=2)],{1:4});self.assertTrue(a['holes'][0]['gir'])

 def test_pending_green_is_not_a_confirmed_gir(self):
  from round_technical_stats import calculate
  s,h,f=self.fixture();last=f['sequence'][1]
  last['landing_report']=dict(stroke_id=last['id'],scope=canonical(['r','map',1]),lie='果岭',lie_type='green',source='user_report',confirmation='pending',green_status='unknown')
  self.assertIn('尚待核实',wording(classify(s,h,last)))
  a=calculate(s,[dict(hole=1,total=4,putts=2)],{1:4})
  self.assertIsNone(a['holes'][0]['gir'])
