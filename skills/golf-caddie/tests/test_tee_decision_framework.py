import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tee_decision_framework import record,preference
class FrameworkTests(unittest.TestCase):
 def test_multiple_rounds_required_and_retries_do_not_add_samples(self):
  s={'journey':{'memory_allowed':True,'round':{'id':'r0'}}};offer={'options':[{'club':'一号木','carry_yards':260,'risk_factors':[0,1,0,0]},{'club':'5号木','carry_yards':200,'risk_factors':[0,0,0,0]}]}
  for i in range(6):
   s['journey']['round']['id']='r'+str(i//2)
   d={'source':'user_report','event_id':str(i),'hole':i%2+1,'club':'5号木'}
   record(s,offer,[d]);record(s,offer,[d])
   if i<4:self.assertEqual('unconfirmed',preference(s['journey']))
  self.assertEqual(6,len(s['journey']['tee_preference_samples']));self.assertEqual('control',preference(s['journey']))
 def test_no_memory_no_learning_and_single_option_not_choice_evidence(self):
  s={'journey':{'memory_allowed':False,'round':{'id':'r'}}};record(s,{},[]);self.assertNotIn('tee_preference_samples',s['journey'])
  s['journey']['memory_allowed']=True;record(s,{'options':[{'club':'一号木','carry_yards':260,'risk_factors':[0,1,0,0]}]},[{'club':'一号木','source':'user_report','event_id':'x'}]);self.assertNotIn('tee_preference_samples',s['journey'])

 def test_same_hole_reselection_replaces_sample(self):
  s={'journey':{'memory_allowed':True,'round':{'id':'r'}}}
  offer={'options':[{'club':'一号木','carry_yards':260,'risk_factors':[0,1,0,0]},{'club':'5号木','carry_yards':200,'risk_factors':[0,0,0,0]}]}
  for i in range(8):record(s,offer,[{'source':'user_report','event_id':str(i),'hole':1,'club':'5号木'}])
  self.assertEqual(1,len(s['journey']['tee_preference_samples']));self.assertEqual('unconfirmed',preference(s['journey']))
