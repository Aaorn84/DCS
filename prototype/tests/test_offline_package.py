import unittest
from services.api.server import Engine
from services.api.offline_package import build
class OfflinePackageTests(unittest.TestCase):
 def test_only_selected_course_and_profile_exported(self):
  s={'version':3,'facts':{'context.course_snapshot':{'value':'map','valid':True}},'evidence':{'map':{'data':{'course_id':'a','holes':[{'number':1}]}},'other':{'data':{'secret':'unrelated'}}},'journey':{'round':{'id':'r'},'profile':{'seven':{'value':150}},'history':[{'private':'not-exported'}],'style_receipts':{'old':'not-exported'}}}
  one=build(s);two=build(s);self.assertEqual(one['sha256'],two['sha256']);self.assertNotIn('history',one['package']);self.assertFalse(one['package']['capabilities']['full_round_offline']);self.assertEqual('a',one['package']['course']['course_id'])
  s['journey']['profile']['seven']['value']=160;self.assertNotEqual(one['sha256'],build(s)['sha256'])
 def test_no_legacy_export_mode_or_distance_component(self):
  from services.api.state_components import external
  with self.assertRaises(TypeError):build({},local_rules=False)
  self.assertFalse(external(('journey','confirmed_shot_distances','endpoints')))
  self.assertTrue(external(('journey','round_ledger','scope','sequence')))
