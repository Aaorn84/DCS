import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from journey_style_preferences import reduce_journey
from phoenix_demo import course,preview
class CourseMetadataCorrectionTests(unittest.TestCase):
 def test_hole17_asset(self):
  h=preview(17)
  self.assertEqual((h['par'],h['published_yardage']),(3,130))
 def test_correction_preserves_records_and_geometry_and_replays(self):
  snapshot=course();snapshot['holes'][16].update(par=5,published_yardage=580)
  s=dict(version=5,facts={'context.course_snapshot':dict(valid=True,value='map')},evidence={'map':{'data':snapshot}},journey=dict(profile={'carry':260},ball_rules={'strokes':[{'club':'seven'}]},round={'id':'round'},consultation={'stale':True}))
  old=copy.deepcopy(s)
  e=dict(event_id='correction17',protocol_version=111,type='course_metadata_correction',data=dict(hole=17,published_yardage=130,provenance={'source':'user_report'}))
  reduce_journey(s,e,6,0)
  self.assertEqual(s['evidence']['map']['data']['holes'][16]['par'],3)
  for key in ('profile','round','ball_rules'):self.assertEqual(s['journey'][key],old['journey'][key])
  for i,h in enumerate(snapshot['holes']):
   if i!=16:self.assertEqual(h,old['evidence']['map']['data']['holes'][i])
  self.assertEqual(snapshot['holes'][16]['display_paths'],old['evidence']['map']['data']['holes'][16]['display_paths'])
  self.assertNotIn('consultation',s['journey'])
  self.assertTrue(reduce_journey(s,e,7,0)['duplicate'])
