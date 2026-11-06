import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from builtin_courses import load, list_courses, source_hole, normalize, encode, import_source, round_snapshot, register, COURSE_ID
from round_state import Engine,StateError
from round_session import course_schema


class BuiltinTests(unittest.TestCase):
    def sample(self):
        p1=dict(latitude=22.5,longitude=113.9);p2=dict(latitude=22.501,longitude=113.901)
        item=dict(holeId=100,gpsType='GreenTrace',gpsCoordinate=p1,shapes=[[p1,p2]])
        return dict(name='Noble Merchant',publicId='CDJXPFHP',facility=dict(facilityId=26004),
                    courses=[dict(courseId=35612,name='A',courseHoleType='EighteenHole')],data=[item])
    def norm(self,raw):return normalize(raw,hashlib.sha256(encode(raw)).hexdigest())
    def test_real_asset_inventory_and_hash(self):
        d=load();self.assertEqual(d['course_id'],COURSE_ID)
        self.assertEqual(d['statistics']['source_records'],1236)
        self.assertEqual(d['statistics']['unique_source_records'],616)
        self.assertEqual(d['statistics']['exact_duplicate_records'],620)
        self.assertEqual(len(d['features']),263)
        self.assertEqual(len(d['source_holes']),36)
        self.assertEqual(d['source']['sha256'],'f867eb5757a3b9aaabaac36605016211a378128535644fcc574ae05f51190012')
    def test_real_groups_keep_missing_mapping_and_par(self):
        d=load();self.assertEqual([c['name'] for c in d['source_courses']],['A','B'])
        for h in d['source_holes']:
            self.assertIsNone(h['course_id']);self.assertIsNone(h['number']);self.assertIsNone(h['par'])
        self.assertEqual(d['holes'],[]);self.assertIsNone(d['crs'])
    def test_every_original_record_has_one_provenance_reference(self):
        d=load();indexes=[i for f in d['features'] for i in f['source_record_indices']]
        self.assertEqual(sorted(indexes),list(range(1236)))
        features={f['id']:f for f in d['features']}
        for h in d['source_holes']:
            self.assertTrue(all(h['source_hole_id'] in features[fid]['source_hole_ids'] for fid in h['feature_ids']))
    def test_duplicate_and_cross_hole_shared_geometry_not_lost(self):
        raw=self.sample();raw['data']+=[copy.deepcopy(raw['data'][0]),dict(copy.deepcopy(raw['data'][0]),holeId=101)]
        d,r=self.norm(raw)
        self.assertEqual(len(d['features']),1)
        self.assertEqual(d['features'][0]['source_record_indices'],[0,1,2])
        self.assertEqual(d['features'][0]['source_hole_ids'],[100,101])
        self.assertEqual(r['statistics']['exact_duplicate_records'],1)
    def test_open_paths_are_not_auto_closed(self):
        d,_=self.norm(self.sample());f=d['features'][0]
        self.assertEqual(f['geometry']['closed'],[False]);self.assertEqual(len(f['geometry']['parts'][0]),2)
        self.assertEqual(f['geometry']['parts'][0][0],[113.9,22.5])
    def test_invalid_coordinate_rejects_entire_import(self):
        raw=self.sample();raw['data'][0]['shapes'][0][0]['latitude']=100
        with self.assertRaises(ValueError):self.norm(raw)
    def test_source_identity_not_silently_assigned_to_other_club(self):
        raw=self.sample();raw['publicId']='OTHER'
        with self.assertRaises(ValueError):self.norm(raw)
    def test_source_anchor_is_not_flag_or_verified_green_center(self):
        d=load();greens=[f for f in d['features'] if f['kind']=='green_outline']
        self.assertEqual(len(greens),36)
        self.assertTrue(all(f['anchor_meaning']=='unspecified_provider_reference' for f in greens))
        self.assertFalse(d['capabilities']['gps_distance'])
    def test_unknown_type_is_preserved_not_classified_as_penalty(self):
        raw=self.sample();raw['data'][0]['gpsType']='UnknownProviderThing'
        d,_=self.norm(raw);self.assertEqual(d['features'][0]['kind'],'unknown')
        self.assertEqual(d['statistics']['unknown_source_types'],['UnknownProviderThing'])
    def test_bounds_and_closed_flags_reflect_only_source(self):
        raw=self.sample();path=raw['data'][0]['shapes'][0]
        path.extend([dict(latitude=22.502,longitude=113.9),copy.deepcopy(path[0])])
        d,_=self.norm(raw);self.assertEqual(d['features'][0]['geometry']['closed'],[True])
        self.assertEqual(d['features'][0]['bbox'],[113.9,22.5,113.901,22.502])
    def test_weather_averages_never_become_live_weather(self):
        raw=self.sample();raw['facility'].update(averageTemp=79,averageWindSpeed=7.91)
        d,_=self.norm(raw);self.assertNotIn('averageTemp',d['facility']);self.assertNotIn('weather',d)
    def test_import_and_registry_are_deterministic(self):
        with tempfile.TemporaryDirectory() as t:
            source=Path(t)/'source.json';source.write_bytes(encode(self.sample()))
            out=Path(t)/'registry';import_source(source,out)
            before={p.name:p.read_bytes() for p in out.iterdir()}
            import_source(source,out)
            self.assertEqual(before,{p.name:p.read_bytes() for p in out.iterdir()})
            self.assertEqual(load(root=out)['statistics']['source_records'],1)
    def test_corrupt_asset_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);entry=list_courses()[0]
            (root/'index.json').write_bytes(encode(dict(schema_version='0.1.0',courses=[entry])))
            (root/entry['asset']).write_text('{}')
            with self.assertRaises(ValueError):load(root=root)
    def test_registry_cannot_escape_asset_root(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);entry=list_courses()[0];entry['asset']='../escape.json'
            (root/'index.json').write_bytes(encode(dict(schema_version='0.1.0',courses=[entry])))
            with self.assertRaises(ValueError):load(root=root)
    def test_source_hole_lookup_has_only_associated_features(self):
        data=source_hole(538214)
        self.assertEqual(len(data['features']),27)
        self.assertTrue(all(538214 in f['source_hole_ids'] for f in data['features']))
        with self.assertRaises(ValueError):source_hole(1)
    def test_operational_round_map_is_blocked_without_metadata(self):
        self.assertEqual(round_snapshot()['status'],'blocked')
        with self.assertRaises(StateError):course_schema(load())
    def test_register_reference_evidence_and_replay_without_guessing(self):
        e=Engine(':memory:','alice');e.create('r')
        try:
            result=register(e,'r','builtin-load','2026-11-06T00:00:00Z')
            ev=e.state('r')['evidence'][result['evidence_id']]
            self.assertEqual(ev['source'],'course');self.assertFalse(ev['data']['spatial_use_allowed'])
            self.assertEqual(e.state('r')['facts'],{})
            self.assertEqual(e.state('r'),e.replay('r'))
            self.assertEqual(result,register(e,'r','builtin-load','2026-11-06T00:00:00Z'))
        finally:e.close()
    def test_unverified_course_cannot_sneak_operational_holes(self):
        e=Engine(':memory:','alice');e.create('r')
        try:
            data=load();data['holes']=[dict(number=1,par=4)]
            with self.assertRaises(StateError):e.command('r','unsafe','evidence',dict(id='unsafe',revision=1,phase='final',source='course',observed_at='2026-11-06T00:00:00Z',data=data))
        finally:e.close()
    def test_cli_registry_lists_real_builtin(self):
        p=Path(__file__).resolve().parents[1]/'scripts/builtin_courses.py'
        r=subprocess.run([sys.executable,'-B',str(p),'list'],capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(r.stdout)[0]['course_id'],COURSE_ID)
