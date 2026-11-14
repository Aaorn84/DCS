import unittest,sys,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from iron_estimates import iron_table,present_iron_option
class IronEstimatesTests(unittest.TestCase):
 def profile(self,units='码',distance=160):return {'seven':{'value':{'distance':distance,'units':units,'distance_type':'carry'}}}
 def test_gap_and_no_wedges(self):
  table=iron_table(self.profile());self.assertEqual(set(table),set(range(2,10)));self.assertEqual(table[8]['carry_yards'],150);self.assertEqual(table[9]['carry_yards'],140);self.assertEqual(table[6]['carry_yards'],170)
 def test_units_and_explicit_override(self):
  p=self.profile('米',146.304);p['long_iron']={'value':{'club_name':'5铁','distance':185,'units':'码','distance_type':'carry'}}
  table=iron_table(p);self.assertAlmostEqual(table[8]['carry_yards'],150);self.assertEqual(table[5]['carry_yards'],185);self.assertEqual(table[5]['source'],'user_report')
 def test_missing_or_total_distance_not_used(self):
  self.assertEqual(iron_table({}),{});p=self.profile();p['seven']['value']['distance_type']='total';self.assertEqual(iron_table(p),{})
 def test_145_yards_prefers_9iron_without_learning(self):
  state={'journey':{'profile':self.profile(),'consultation':{'lie_report':'球道'}},'evidence':{'map':{'data':{'holes':[{'number':1,'objects':[{'kind':'green_center'}]}]}}}}
  original=copy.deepcopy(state)
  with patch('iron_estimates.fresh_position',return_value={'value':{}}),patch('iron_estimates.fact_value',side_effect=lambda s,k:'map' if k=='context.course_snapshot' else 1),patch('iron_estimates.haversine',return_value=145*.9144):
   text,candidate=present_iron_option(state,'到果岭参考点约145码。建议用熟悉的短杆控制距离。',0)
   self.assertEqual(candidate['club'],'9号铁');self.assertIn('估算',text);self.assertTrue(candidate['not_for_learning']);self.assertEqual(state,original)
   state['journey']['consultation']['lie_report']='沙坑';self.assertIsNone(present_iron_option(state,'到果岭参考点约145码。建议用熟悉的短杆控制距离。',0)[1])

 def test_pin_yardage_controls_estimated_iron(self):
  state={'journey':{'profile':self.profile(),'consultation':{'lie_report':'球道'}}}
  with patch('iron_estimates.fresh_position',return_value={'value':{}}):
   text,candidate=present_iron_option(state,'到旗位约150码。建议用熟悉的短杆控制距离。',0,
      pin={'min_m':145*.9144,'max_m':155*.9144})
  self.assertEqual(candidate['club'],'8号铁')
  self.assertIn('到旗位约150码',text)

 def test_135_yard_pin_prefers_130_yard_carry(self):
  state={'journey':{'profile':self.profile(),'consultation':{'lie_report':'球道'}}}
  with patch('iron_estimates.fresh_position',return_value={'value':{}}):
   text,candidate=present_iron_option(state,'到旗位约135码。建议用熟悉的短杆控制距离。',0,
      pin={'min_m':133*.9144,'max_m':137*.9144})
  self.assertEqual(candidate['club'],'P杆')
  self.assertEqual(candidate['carry_yards'],130)
  self.assertIn('落地后还可能前滚',text)

 def test_between_club_preference_requires_memory_and_clean_lie(self):
  profile=self.profile()
  profile['shot_style_preferences']={'between_clubs':{'value':'长一号收着打'}}
  journey={'profile':profile,'memory_allowed':True,'consultation':{'lie_report':'球道'}}
  source='到旗位约135码。建议用熟悉的短杆控制距离。'
  pin={'min_m':133*.9144,'max_m':137*.9144}
  with patch('iron_estimates.fresh_position',return_value={'value':{}}):
   text,candidate=present_iron_option({'journey':journey},source,0,pin=pin)
   self.assertIn('可先看9号铁',text)
   self.assertEqual(candidate['club'],'P杆')
   journey['memory_allowed']=False
   self.assertNotIn('收着打',present_iron_option({'journey':journey},source,0,pin=pin)[0])
   journey['memory_allowed']=True
   journey['consultation']['lie_report']='沙坑'
   self.assertEqual(present_iron_option({'journey':journey},source,0,pin=pin),(source,None))

 def test_spoken_wedge_bag(self):
  from iron_estimates import parse_spoken_wedge_bag
  lofts, ranges, uses = parse_spoken_wedge_bag('48，110码，52，0到85，58，沙坑', '码')
  self.assertEqual(lofts,[48,52,58])
  self.assertEqual(ranges,{'48':{'low':110,'high':110,'units':'码'},
                          '52':{'low':0,'high':85,'units':'码'}})
  self.assertEqual(uses,{'58':'沙坑'})

 def test_wedge_distance_gap_suggests_only_a_club_that_can_reach(self):
  profile=self.profile(distance=165)
  profile['lofted_wedge_ranges']={'value':{'48':{'low':110,'high':110,'units':'码'}}}
  state={'journey':{'profile':profile,'consultation':{'lie_report':'球道'}}}
  source='到旗位约125码。建议用熟悉的短杆控制距离。'
  with patch('iron_estimates.fresh_position',return_value={'value':{}}):
   text,candidate=present_iron_option(state,source,0,pin={'min_m':124*.9144,'max_m':126*.9144})
   self.assertEqual(candidate['club'],'P杆')
   self.assertEqual(candidate['carry_yards'],135)
   self.assertIn('控到约125码',text)
   self.assertNotIn('48度杆',text)

 def test_rough_approach_uses_current_bunker_distance(self):
  from approach_dialogue import advise
  state={'journey':{'profile':{}}}
  pin={'min_m':29*.9144,'max_m':31*.9144}
  def bunker(s, request, now):
   s['journey']['last_hazard_route']={'kind':'bunker','position_version':1,
     'course_evidence':'map','far_m':19*.9144}
  with patch('short_pin_distance.estimate',return_value=pin), patch(
      'short_pin_distance.pin_distance_wording',return_value='到旗约30码'), patch(
      'approach_dialogue.detailed_advise',return_value={'text':'先保证脱困','distance_m':35*.9144}), patch(
      'hazard_route.answer',side_effect=bunker), patch(
      'approach_dialogue.fresh_position',return_value={'version':1}), patch(
      'approach_dialogue.fact_value',return_value='map'):
   text=advise(state,{'lie_report':'长草'},0,practical_rough=True)['text']
   marginal=advise(state,{'lie_report':'长草'},0,practical_rough=True,confirm_landing=True,use_landing_depth=True)['text']
   pin['min_m']=34*.9144
   pin['max_m']=36*.9144
   advice=advise(state,{'lie_report':'长草'},0,practical_rough=True,confirm_landing=True,use_landing_depth=True)['text']
  self.assertIn('够宽',marginal)
  self.assertIn('Carry先瞄约25码',advice)
  self.assertNotIn('？',advice)
  self.assertIn('过沙约20码',text)
  self.assertIn('沙杆或挖起杆抛切',text)
  self.assertIn('球埋得深',text)

 def test_back_pin_selects_carry_short_of_all_lateral_positions(self):
  state={'journey':{'profile':self.profile(),'consultation':{'lie_report':'球道'}}}
  with patch('iron_estimates.fresh_position',return_value={'value':{}}):
   for side in ('左','中','右'):
    text,candidate=present_iron_option(state,'到旗位约140码。建议用熟悉的短杆控制距离。',0,
      strategy=True,pin={'min_m':139*.9144,'max_m':141*.9144,'depth':'后','side':side})
    self.assertIn('130–135码',text)
    self.assertEqual(candidate['club'],'P杆')

 def test_back_pin_declines_when_bunker_blocks_carry_window(self):
  state={'journey':{'profile':self.profile(),'consultation':{'lie_report':'球道'}}}
  pin={'min_m':139*.9144,'max_m':141*.9144,'depth':'后','side':'右'}
  line={'front_m':120*.9144,'back_m':150*.9144,'target_m':140*.9144,
        'hazards':{'bunker':136*.9144,'water':None},'accuracy_m':2}
  with patch('iron_estimates.fresh_position',return_value={'value':{}}), patch(
      'short_pin_distance.estimate',return_value={'aim':{'latitude':1,'longitude':1}}), patch(
      'hazard_route.landing_line',return_value=line):
   text,candidate=present_iron_option(state,'到旗位约140码。',0,pin=pin,strategy=True,verified_lines=True)
  self.assertIsNone(candidate)
  self.assertIn('分段打',text)

 def test_same_ray_intersects_only_hazards_on_that_line(self):
  from hazard_route import landing_line
  def zone(kind, west, south, east, north):
   ring=[[west,south],[east,south],[east,north],[west,north],[west,south]]
   return {'surface':kind,'verified':True,'source':'test','geometry':{'type':'Polygon','coordinates':[ring]}}
  hole={'number':1,'objects':[{'kind':'green_center','longitude':0,'latitude':.001}],
        'surface_zones':[zone('green',-.0005,.0009,.0005,.0013),
                         zone('bunker',.00014,.0006,.00028,.0007)]}
  state={'evidence':{'map':{'active':True,'phase':'final','data':{'holes':[hole]}}}}
  with patch('hazard_route.fresh_position',return_value={'value':{'longitude':0,'latitude':0,'accuracy_m':1}}), patch(
      'hazard_route.fact_value',side_effect=lambda s,k:'map' if k.endswith('snapshot') else 1):
   center=landing_line(state,0)
   right=landing_line(state,0,{'longitude':.00035,'latitude':.0011})
  self.assertIsNone(center['hazards']['bunker'])
  self.assertGreater(right['hazards']['bunker'],0)
  self.assertLess(right['hazards']['bunker'],right['front_m'])
