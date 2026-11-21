import sys,unittest,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from journey_style_preferences import reduce_journey
class InactiveSpatialEventsTests(unittest.TestCase):
 def test_late_gps_does_not_reopen_or_change_finished_round(self):
  for stage in ('postgame','idle','course'):
   s=dict(version=1,journey=dict(stage=stage,round={'id':'r'},profile={'carry':260}),facts={'holes.18.total':{'value':5}})
   old=copy.deepcopy(s)
   e=dict(event_id='late-gps',protocol_version=111,type='gps',data={'latitude':22,'longitude':114})
   r=reduce_journey(s,e,2,0)
   self.assertTrue(r['ignored']);self.assertEqual(r['reason'],'round_inactive');self.assertEqual(s['facts'],old['facts']);self.assertEqual(s['journey']['stage'],stage)
   self.assertTrue(reduce_journey(s,e,3,0)['duplicate'])
