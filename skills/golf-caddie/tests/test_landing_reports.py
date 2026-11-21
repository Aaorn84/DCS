import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from landing_reports import parse
import test_stroke_consistency as support
from journey import view

class LandingPhraseTests(unittest.TestCase):
 def test_examples(self):
  cases={'看到了':'seen','球在':'seen','找到了':'seen','能找到':'seen','球道中间':'lie','在球道上':'lie','上球道了':'lie','偏右，还在球道':'lie','果岭上':'lie','上去了':'context_green','上果岭了':'lie','停在果岭左边':'green_edge','右边长草':'lie','进草了':'lie','浅草里':'lie','草有点深':'lie','进沙坑了':'lie','右侧沙坑':'lie','掉坑里了':'lie','没上去，在前沿':'lie','过了果岭':'lie','果岭外左边':'lie','停在环上':'lie','没看清':'unknown','只看到往右飞':'unknown','大概在沙坑附近':'lie','落下后看不到了':'unknown','可能OB了':'hazard','好像下水了':'hazard','可能找不到':'hazard','不确定有没有越界':'hazard','确认出界':'hazard','确定下水':'hazard','找到了，在界内':'boundary','刚才看错了，在长草里':'lie','不是沙坑，是旁边球道':'lie'}
  for text,kind in cases.items():
   with self.subTest(text=text):self.assertEqual(kind,parse(text)['kind'])

class LandingJourneyTests(unittest.TestCase):
 protocol_version=111
 setUp=support.StrokeConsistencyTests.setUp
 tearDown=support.StrokeConsistencyTests.tearDown
 send=support.StrokeConsistencyTests.send
 onboard=support.StrokeConsistencyTests.onboard
 start=support.StrokeConsistencyTests.start
 select_and_sound=support.StrokeConsistencyTests.select_and_sound
 def test_compound_and_correction_do_not_duplicate(self):
  self.start();self.select_and_sound()
  self.assertIn('边界仍待',self.send('看到了，右边长草，应该没出界')['text'])
  self.assertIn('已更正',self.send('刚才看错了，在果岭上')['text'])
  state=self.e.state('j');self.assertEqual('果岭',state['journey']['reported_landing']['lie'])
  from ball_rules import current
  stroke=next(r for r in current(state)['sequence'] if r['kind']=='stroke')
  self.assertEqual(stroke['landing_report']['lie'],'果岭')
  self.assertEqual(stroke['landing_report']['stroke_id'],stroke['id'])
  self.assertEqual(1,len(view(state)['round_records']['clubs']))
  self.assertEqual(state,self.e.replay('j'))
 def test_uncertain_and_edge_do_not_claim_green(self):
  self.start();self.select_and_sound()
  self.assertIn('以内',self.send('停在果岭左边')['text'])
  self.assertNotIn('reported_landing',self.e.state('j')['journey'])
  self.assertIn('落点还未确认',self.send('大概在沙坑附近')['text'])
  self.assertNotIn('reported_landing',self.e.state('j')['journey'])
  self.assertIn('球位类型待确认',self.send('果岭外左边')['text'])
 def test_greenside_followup_saves_compact_structured_location(self):
  self.start();self.select_and_sound()
  self.send('果岭边')
  from ball_rules import current
  state=self.e.state('j');stroke=next(r for r in current(state)['sequence'] if r['kind']=='stroke')
  self.assertEqual('unknown',stroke['landing_location']['lie_type'])
  self.assertEqual('pending',stroke['landing_location']['confirmation'])
  self.assertNotIn('普通聊天',self.send('果岭边长草')['text'])
  state=self.e.state('j');stroke=next(r for r in current(state)['sequence'] if r['kind']=='stroke')
  self.assertEqual('rough',stroke['landing_location']['lie_type'])
  self.assertEqual('greenside',stroke['landing_location']['area'])
  self.assertEqual('user_report',stroke['landing_location']['source'])
  self.assertEqual('confirmed',stroke['landing_location']['confirmation'])
  self.assertNotIn('text',stroke['landing_report'])
  self.assertNotIn('position',stroke['landing_report'])
  self.assertEqual(1,len(view(state)['round_records']['clubs']))
  self.assertEqual(state,self.e.replay('j'))
 def test_risk_enters_rules(self):
  self.start();self.select_and_sound()
  self.assertIn('暂定球',self.send('可能OB了')['text'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))
 def test_possible_lost_then_found_in_bounds_closes_search(self):
  self.start();self.select_and_sound()
  self.assertIn('暂定球',self.send('可能找不到')['text'])
  reply=self.send('找到了，在界内')['text']
  self.assertNotIn('普通聊天',reply)
  from ball_rules import current
  self.assertIsNone(current(self.e.state('j'))['pending'])
  self.assertEqual(self.e.state('j'),self.e.replay('j'))

class LandingTaxonomyTests(unittest.TestCase):
 def test_surface_and_area(self):
  for text,kind,area in [('果岭边长草','rough','greenside'),('果岭附近沙坑','bunker','greenside'),('果岭环','fringe','greenside'),('球道左侧沙坑','bunker','fairway_left'),('球道中间','fairway','fairway_center')]:
   with self.subTest(text=text):
    row=parse(text);self.assertEqual(kind,row['lie_type']);self.assertEqual(area,row['area']);self.assertEqual('confirmed',row['confirmation'])
 def test_uncertain_is_not_confirmed(self):
  for text in ('好像在果岭上','大概在沙坑附近','果岭边'):
   with self.subTest(text=text):self.assertEqual('pending',parse(text)['confirmation'])
 def test_legacy_edge_is_not_fringe(self):
  from landing_types import normalize
  self.assertEqual('unknown',normalize({'lie':'果岭附近'})['lie_type'])
  self.assertEqual('fringe',normalize({'lie':'果岭附近','text':'果岭环'})['lie_type'])
