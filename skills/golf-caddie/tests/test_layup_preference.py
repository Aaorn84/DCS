import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from approach_dialogue import advise,wants_layup
from hazard_route import green_crossing_advice
class LayupPreferenceTests(unittest.TestCase):
 def test_explicit_risk_avoidance_overrides_ambiguous_two_on(self):
  self.assertTrue(wants_layup('直攻风险太大，考虑两上'))
  self.assertTrue(wants_layup('先过渡，稳一点'))
  self.assertFalse(wants_layup('直攻风险大吗？'))
  self.assertFalse(wants_layup('两上方案'))
 def test_layup_request_does_not_repeat_direct_attack(self):
  state={'facts':{},'evidence':{},'journey':{'profile':{}}}
  c=dict(ball_position_report='user_confirmed',lie_report='球道',approach_preference='layup')
  with patch('approach_dialogue.detailed_advise',return_value={'text':'到果岭205码。','distance_m':205*.9144}),patch('short_pin_distance.estimate',return_value=None),patch('tee_strategy.actual_position_layup',return_value='第二杆目标Carry105码，预计第三杆约100码。可考虑48度杆。') as layup,patch('hazard_route.green_crossing_advice') as direct:
   result=advise(state,c,0,assess_lie=True,carry_crossing=True,verify_playability=True)
  direct.assert_not_called();layup.assert_called_once_with(state,0,compare_safety=True,allow_other_par=True)
  self.assertIn('先过渡',result['text']);self.assertIn('预计下一杆',result['text'])
  self.assertNotIn('直接攻',result['text']);self.assertNotIn('第二杆',result['text'])
 def test_attack_never_invents_two_iron_and_prefers_known_wood(self):
  state={'journey':{'profile':{'seven':{'value':{'distance':160,'units':'码','distance_type':'carry'}},'hybrid':{'value':{'distance':210,'units':'码','distance_type':'carry'}}}}}
  line=dict(front_m=204*.9144,back_m=220*.9144,target_m=205*.9144,accuracy_m=1,hazards={'water':179*.9144,'bunker':None,'ob':None})
  with patch('hazard_route.landing_line',return_value=line):result=green_crossing_advice(state,0,lie='球道',verify_playability=True,assess_lie=True)
  self.assertNotIn('2号铁',result['text']);self.assertIn('铁木杆',result['text'])

class LayupDecisionTests(unittest.TestCase):
 def test_risk_request_and_wedge_choice_keep_fairway_target(self):
  import test_stroke_consistency as support
  from journey import _apply_journey
  fixture=support.StrokeConsistencyTests();fixture.setUp()
  try:
   fixture.start();fixture.point()
   state=fixture.e.state('j')
   state['journey']['consultation']=dict(phase='plan',ball_position_report='user_confirmed',lie_report='球道',lie_evidence={'source':'user_report'})
   event=dict(type='message',text='直攻风险太大，考虑两上',event_id='layup-request',observed_at=fixture.clock.isoformat(),_stroke_consistency_v111=True,_approach_lie_v109=True,_carry_crossing_v96=True,_carry_playability_v99=True,_dialogue_v69=True,_dialogue_v70=True)
   with patch('tee_strategy.analyze',return_value=None),patch('tee_strategy.actual_position_layup',return_value='可考虑48度杆，第二杆目标Carry105码，预计第三杆100码。'):
    reply=_apply_journey(state,event,state['version']+1,fixture.clock.timestamp())
   self.assertIn('先过渡',reply['text']);self.assertEqual('layup',state['journey']['consultation']['approach_preference'])
   with patch('tee_strategy.analyze',return_value=None):
    reply=_apply_journey(state,dict(event,event_id='layup-club',text='48'),state['version']+1,fixture.clock.timestamp())
   self.assertIn('过渡落点',reply['text'])
   self.assertEqual('fairway',state['journey']['player_decisions'][-1]['target'])
  finally:fixture.tearDown()

class BroadLayupSearchTests(unittest.TestCase):
 def test_fixed_ninety_yard_leave_does_not_hide_large_forward_fairway(self):
  from tee_strategy import par_five_routes
  yard=.9144;meter=111195
  origin=dict(latitude=0,longitude=0,accuracy_m=2)
  green=dict(kind='green_center',latitude=208*yard/meter,longitude=0)
  state={'journey':{'profile':{}},'evidence':{'map':{'data':{'holes':[{'number':10,'objects':[green]}]}}}}
  analysis=dict(course_evidence='map',hole=10,clubs={'long_iron':{'carry_yards':200}})
  seen=[]
  def targets(s,a,clubs,**kw):
   distances=[int(key) for key,value in clubs];seen.append(distances)
   if 200 not in distances:return []
   return [dict(carry_yards=200,width_m=50,crossing_m=None,aim_point=dict(latitude=199*yard/meter,longitude=20*yard/meter,accuracy_m=0))]
  with patch('tee_geometry.tee_targets',side_effect=targets):
   narrow=par_five_routes(state,analysis,[{'aim_point':origin,'crossing_m':None}])
   broad=par_five_routes(state,analysis,[{'aim_point':origin,'crossing_m':None}],broad=True)
  self.assertEqual([],narrow);self.assertNotIn(200,seen[0]);self.assertIn(200,seen[1])
  self.assertEqual(1,len(broad));self.assertGreater(broad[0]['leave_yards'],10)
