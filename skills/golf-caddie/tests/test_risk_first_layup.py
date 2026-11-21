import copy,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from tee_strategy import par_five_routes
from journey_style_preferences import tee_note
from on_course_preferences import respond
class RiskFirstLayupTests(unittest.TestCase):
 def fixture(self):
  yard=.9144;meter=111195
  origin=dict(latitude=0,longitude=0,accuracy_m=2)
  green=dict(kind='green_center',latitude=208*yard/meter,longitude=0)
  state={'journey':{'profile':{},'memory_allowed':True},'facts':{},'evidence':{'map':{'data':{'holes':[{'number':10,'objects':[green]}]}}}}
  analysis=dict(course_evidence='map',hole=10,clubs={'long_iron':{'carry_yards':200}})
  return state,analysis,origin
 def test_reported_or_learned_leave_does_not_change_search_or_ranking(self):
  state,a,origin=self.fixture();seen=[]
  def targets(s,a,clubs,**kw):
   distances=[int(k) for k,v in clubs];seen.append(distances)
   return [dict(carry_yards=200,width_m=50,crossing_m=None,aim_point=dict(latitude=199*.9144/111195,longitude=20*.9144/111195,accuracy_m=0))]
  results=[]
  for value in (None,40,90,140):
   sample=copy.deepcopy(state)
   if value:sample['journey']['profile']['shot_style_preferences']={'value':{},'leave_distance':{'value':value,'unit':'码'}}
   with patch('tee_geometry.tee_targets',side_effect=targets),patch('tee_strategy.layup_risk_rank',return_value=(0,0,0)) as rank,patch('wedge_leave.suggested_leave',side_effect=AssertionError('Habitual leave must not be consulted')):
    result=par_five_routes(sample,a,[{'aim_point':origin,'crossing_m':None}],risk_first=True)
   self.assertNotIn('leave_error',result[0]);self.assertIn(200,seen[-1]);results.append(result)
  self.assertTrue(all(r==results[0] for r in results));self.assertTrue(all(s==seen[0] for s in seen))
 def test_habitual_leave_is_not_used_as_tee_recommendation_note(self):
  journey={'profile':{'shot_style_preferences':{'leave_distance':{'value':90,'unit':'码'}}}}
  routes=[dict(kind='conservative',risk='宽阔落区',remaining_yards=90)]
  self.assertIsNone(tee_note(journey,routes,use_leave=False))
 def test_generic_layup_question_no_longer_requests_habitual_distance(self):
  state,a,origin=self.fixture()
  self.assertIsNone(respond(state,'五杆洞第二杆怎么打','q',0,risk_first=True))
  text=respond(state,'五杆洞第二杆，两条落点都可用，可推进100或160码，怎么选？','q',0,risk_first=True)
  self.assertNotIn('留90',text);self.assertIn('障碍',text)
