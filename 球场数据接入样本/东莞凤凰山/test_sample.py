import copy, hashlib, json, unittest
from pathlib import Path
from import_course import normalize, report, demo_route
BASE=Path(__file__).resolve().parent
class SampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.d=json.loads((BASE/'data/course.normalized.json').read_text())
    def test_counts(self):
        self.assertEqual(report(self.d)['counts'],dict(courses=3,physical_holes=27,tee_configurations=13,tee_hole_records=117,geometry_records=171,parts=394,vertices=23640,explicitly_closed_parts=0))
    def test_nested_par_survives_root_null(self):
        self.assertTrue(all(h['root_par_raw'] is None and h['par'] in (3,4,5) for h in self.d['holes']))
    def test_order_is_not_hole_id_sort(self):
        self.assertEqual(self.d['courses'][1]['hole_ids_in_play_order'][7],475531)
    def test_blue_variants_preserved(self):
        c=self.d['courses'][2]
        self.assertEqual({t['tee_id'] for t in c['tees'] if t['color']=='Blue'},{650696,650697})
    def test_route(self):
        r=demo_route(self.d)
        self.assertEqual((len(r['holes']),r['par'],r['published_yardage']),(18,72,6388))
        self.assertEqual(r['holes'][16]['hole_id'],475531)
    def test_spatial_block(self):
        self.assertEqual(self.d['capabilities']['crs'],'WGS84')
        self.assertEqual(self.d['capabilities']['coordinate_status'],'user_confirmed')
        self.assertTrue(self.d['capabilities']['reference_point_distance_enabled'])
        self.assertFalse(self.d['capabilities']['polygon_operations_enabled'])
        self.assertFalse(self.d['capabilities']['spatial_use_allowed'])
        self.assertEqual(self.d['semantics']['yardage_kind'],'published tee length; not GPS displacement or carry')
    def fixture(self):
        h={'holeId':1,'holeNumber':1,'holeName':'A #1','par':4,'yardage':300,'allocation':1}
        return {'publicId':'B87QFJP7','name':'Fixture','facility':{},'holes':[{**h,'par':None}],
            'courses':[{'courseId':2,'name':'A','tees':[{'teeId':3,'teeName':'Blue','teeColorType':'Blue','par':4,'yardage':300,'holes':[h]}]}],
            'data':[{'holeId':1,'gpsType':'GreenTrace','gpsCoordinate':None,'shapes':[[{'latitude':22,'longitude':114},{'latitude':23,'longitude':114}]]}]}
    def test_adapter_determinism_and_no_invention(self):
        raw=self.fixture();before=copy.deepcopy(raw)
        d=normalize(raw,'fixture');self.assertEqual(d,normalize(raw,'fixture'));self.assertEqual(raw,before)
        self.assertEqual(d['geometry_records'][0]['source_paths'],raw['data'][0]['shapes'])
        self.assertIsNone(d['holes'][0]['reference_coordinates']['teeGPSCoordinate'])
    def test_reject_orphans_and_totals(self):
        for kind in ('geometry','tee','total','identity'):
            r=self.fixture()
            if kind=='geometry':r['data'][0]['holeId']=99
            if kind=='tee':r['courses'][0]['tees'][0]['holes'][0]['holeId']=99
            if kind=='total':r['courses'][0]['tees'][0]['yardage']=301
            if kind=='identity':r['publicId']='other'
            with self.subTest(kind=kind), self.assertRaises(ValueError):normalize(r,'fixture')
    def test_confirmation_is_version_bound(self):
        r=self.fixture()
        c={'source_sha256':'fixture','public_id':'B87QFJP7','crs':'WGS84'}
        self.assertEqual(normalize(r,'fixture',c)['capabilities']['crs'],'WGS84')
        with self.assertRaises(ValueError):normalize(r,'different-version',c)
        self.assertIsNone(normalize(r,'fixture')['capabilities']['crs'])
    def test_manifest(self):
        manifest=json.loads((BASE/'manifest.json').read_text())
        for name,expected in manifest['files'].items():
            self.assertEqual(hashlib.sha256((BASE/name).read_bytes()).hexdigest(),expected,name)
if __name__=='__main__':unittest.main()
