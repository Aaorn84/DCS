import copy,unittest
from services.api.view_delivery import compact
class ViewDeliveryTests(unittest.TestCase):
 def test_revisions_omit_only_unchanged_sections_without_mutating_input(self):
  view=dict(version=1,simulation=dict(hole=1,paths=[{'points':[1,2]}],positions={'tee':1},device_position={'latitude':1}),round_records={'clubs':[]},profile={})
  original=copy.deepcopy(view);first=compact(view,{})
  again=compact(view,first['journey_revisions'])
  self.assertEqual(original,view);self.assertNotIn('paths',again['journey']['simulation']);self.assertNotIn('round_records',again['journey'])
  view['simulation']['device_position']={'latitude':2};view['simulation']['paths']=[{'points':[3,4]}]
  changed=compact(view,first['journey_revisions']);self.assertIn('paths',changed['journey']['simulation']);self.assertEqual({'latitude':2},changed['journey']['simulation']['device_position'])
 def test_missing_or_wrong_revision_sends_full_value_and_no_stale_null(self):
  self.assertEqual(None,compact({'round_review':None},{'round_review':'old'})['journey']['round_review'])
  self.assertEqual(None,compact({'simulation':None},{'simulation.paths':'old'})['journey']['simulation'])
