#!/usr/bin/env python3
"""Offline, provenance-preserving built-in course registry. No CRS guessing."""
import argparse
import copy
import hashlib
import json
from pathlib import Path

VERSION='0.1.0'
COURSE_ID='shenzhen-noble-merchant-cn'
KINDS={'WaterPath':'water_path','WaterTrace':'water_outline','BunkerTrace':'bunker_outline',
       'FairwayTrace':'fairway_outline','TeeboxTrace':'tee_outline','GreenTrace':'green_outline','CartpathTrace':'cart_path'}


def encode(d):
    return json.dumps(d,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')


def check(ok,msg):
    if not ok:raise ValueError(msg)


def coord(p):
    check(isinstance(p,dict),'coordinate object required')
    import math
    lat,lon=p.get('latitude'),p.get('longitude')
    check(type(lat) in (int,float) and type(lon) in (int,float) and math.isfinite(lat) and math.isfinite(lon)
          and -90<=lat<=90 and -180<=lon<=180,'invalid source coordinate')
    return [lon,lat]


def normalize(raw, source_sha256, source_name='名商.json'):
    check(isinstance(raw,dict) and isinstance(raw.get('data'),list),'source data array required')
    check(isinstance(source_sha256,str) and len(source_sha256)==64 and all(c in '0123456789abcdef' for c in source_sha256),'source SHA256 required')
    check(isinstance(raw.get('name'),str) and isinstance(raw.get('courses'),list),'source course metadata required')
    check(raw.get('publicId')=='CDJXPFHP' and raw.get('facility',{}).get('facilityId')==26004,'this importer profile is for Noble Merchant only')
    full_records=set();features={};holes={};unknown_types=set();point_count=0
    for i,item in enumerate(raw['data']):
        check(isinstance(item,dict) and set(item)=={'holeId','gpsType','gpsCoordinate','shapes'},'unrecognized source record schema')
        hid,typ=item['holeId'],item['gpsType']
        check(type(hid) is int and hid>0 and isinstance(typ,str),'source hole id/type required')
        check(isinstance(item['shapes'],list) and item['shapes'],'source shapes required')
        parts=[]
        for path in item['shapes']:
            check(isinstance(path,list) and len(path)>=2,'source path needs at least two vertices')
            parts.append([coord(p) for p in path]);point_count+=len(path)
        anchor=None if item['gpsCoordinate'] is None else coord(item['gpsCoordinate'])
        canonical_source={k:v for k,v in item.items() if k!='holeId'}
        full_records.add(encode(item))
        digest=hashlib.sha256(encode(canonical_source)).hexdigest()
        fid='feature-'+digest
        if typ not in KINDS:unknown_types.add(typ)
        if fid not in features:
            points=[p for part in parts for p in part]
            features[fid]=dict(id=fid,source_type=typ,kind=KINDS.get(typ,'unknown'),source_anchor=anchor,
                anchor_meaning='unspecified_provider_reference',geometry=dict(type='source_paths',coordinate_order='longitude_latitude',parts=parts,
                    closed=[len(path)>=4 and path[0]==path[-1] for path in parts]),
                bbox=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)],
                source_hole_ids=[],source_record_indices=[])
        feature=features[fid]
        feature['source_record_indices'].append(i)
        if hid not in feature['source_hole_ids']:feature['source_hole_ids'].append(hid)
        hole=holes.setdefault(hid,dict(source_hole_id=hid,course_id=None,number=None,par=None,feature_ids=[]))
        if fid not in hole['feature_ids']:hole['feature_ids'].append(fid)
    check(bool(features),'empty course geometry')
    for f in features.values():f['source_hole_ids'].sort()
    for h in holes.values():h['feature_ids'].sort()
    courses=[]
    for c in raw['courses']:
        check(isinstance(c,dict) and type(c.get('courseId')) is int and isinstance(c.get('name'),str),'invalid source course metadata')
        courses.append(dict(source_course_id=c['courseId'],name=c['name'],declared_hole_type=c.get('courseHoleType'),source_status=c.get('courseStatusType')))
    check(len({c['source_course_id'] for c in courses})==len(courses),'duplicate source course id')
    facility=raw.get('facility') or {}
    root=dict(schema_version=VERSION,course_id=COURSE_ID,map_version='source-'+source_sha256[:16],
        display_name='名商',display_name_source='user_filename',name=raw['name'],synthetic=False,
        crs=None,coordinate_status='unverified',spatial_use_allowed=False,
        source=dict(filename=source_name,sha256=source_sha256,format='provider_gps_shapes',surveyed_at=None,
                    public_id=raw.get('publicId'),course_group_id=raw.get('courseGroupId')),
        facility=dict(source_facility_id=facility.get('facilityId'),name=facility.get('facilityName'),address=facility.get('address'),
                      source_reference=coord(facility['gpsCoordinate']) if facility.get('gpsCoordinate') else None),
        source_courses=courses,source_holes=[holes[k] for k in sorted(holes)],
        # No round-numbered holes until source grouping, order and par are confirmed.
        holes=[],features=[features[k] for k in sorted(features)],
        capabilities=dict(offline_catalogue=True,source_geometry=True,round_hole_mapping=False,par=False,
                          gps_distance=False,ob_rulings=False,penalty_area_classification=False,elevation=False,green_slope=False),
        readiness=dict(status='reference_only',missing=['coordinate_reference_system','source_hole_to_course_and_number','standard_par','survey_time_and_accuracy'],
                       notes=['Source hole IDs are not confirmed physical holes.','Open source paths are preserved; no auto-closure.',
                              'Water outlines are not red/yellow penalty boundaries.','Source anchors are not flag positions.',
                              'Facility averages are not live weather and are excluded from operational weather.']),
        statistics=dict(source_records=len(raw['data']),source_vertices=point_count,unique_source_records=len(full_records),
                        exact_duplicate_records=len(raw['data'])-len(full_records),source_hole_groups=len(holes),
                        unique_features=len(features),shared_feature_associations=len(full_records)-len(features),
                        feature_types={k:sum(f['source_type']==k for f in features.values()) for k in sorted({f['source_type'] for f in features.values()})},
                        unknown_source_types=sorted(unknown_types)))
    report=dict(course_id=root['course_id'],source=root['source'],statistics=root['statistics'],readiness=root['readiness'],
                source_courses=courses,unsupported=['Automatic course/hole ordering','GPS/flag distances before CRS confirmation','OB/penalty rulings','Slope/elevation compensation'])
    return root,report


def import_source(path, output):
    path=Path(path);blob=path.read_bytes();check(len(blob)<=30_000_000,'source exceeds importer size limit')
    data,report=normalize(json.loads(blob),hashlib.sha256(blob).hexdigest(),path.name)
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    payload=encode(data)+b'\n';asset=COURSE_ID+'.json'
    # Dedicated output: do not silently discard other registered courses.
    index_file=output/'index.json'
    index=json.loads(index_file.read_text()) if index_file.exists() else dict(schema_version=VERSION,courses=[])
    check(index.get('schema_version')==VERSION and isinstance(index.get('courses'),list),'invalid existing registry index')
    entry=dict(course_id=COURSE_ID,display_name=data['display_name'],name=data['name'],map_version=data['map_version'],
               asset=asset,sha256=hashlib.sha256(payload).hexdigest(),status='reference_only')
    index['courses']=[c for c in index['courses'] if c['course_id']!=COURSE_ID]+[entry]
    index['courses'].sort(key=lambda c:c['course_id'])
    (output/asset).write_bytes(payload)
    (output/(COURSE_ID+'-report.json')).write_bytes(encode(report)+b'\n')
    index_file.write_bytes(encode(index)+b'\n')
    return report


def registry_root(root=None):
    return Path(root) if root else Path(__file__).resolve().parents[1]/'assets'/'courses'


def list_courses(root=None):
    data=json.loads((registry_root(root)/'index.json').read_text(encoding='utf-8'))
    check(data.get('schema_version')==VERSION and isinstance(data.get('courses'),list),'invalid registry index')
    return copy.deepcopy(data['courses'])


def load(course_id=COURSE_ID,root=None):
    entries=[c for c in list_courses(root) if c['course_id']==course_id]
    check(len(entries)==1,'built-in course not found or ambiguous')
    base=registry_root(root).resolve();path=(base/entries[0]['asset']).resolve()
    check(path.is_relative_to(base),'unsafe registry asset path')
    payload=path.read_bytes();check(hashlib.sha256(payload).hexdigest()==entries[0]['sha256'],'built-in asset checksum mismatch')
    data=json.loads(payload)
    check(data.get('course_id')==course_id and data.get('map_version')==entries[0]['map_version'],'registry identity mismatch')
    return data


def source_hole(hole_id,course_id=COURSE_ID,root=None):
    data=load(course_id,root);holes=[h for h in data['source_holes'] if h['source_hole_id']==hole_id]
    check(len(holes)==1,'source hole id not found')
    h=holes[0];ids=set(h['feature_ids'])
    return dict(course_id=course_id,coordinate_status=data['coordinate_status'],hole=h,
                features=[f for f in data['features'] if f['id'] in ids])


def round_snapshot(course_id=COURSE_ID,root=None):
    data=load(course_id,root)
    return dict(status='blocked',missing=data['readiness']['missing'],course_id=course_id,
                reason='Unverified CRS and unassigned source hole IDs cannot become an operational round map.')


def register(engine,round_id,operation_id,observed_at,course_id=COURSE_ID,root=None):
    data=load(course_id,root)
    eid='builtin-'+course_id+'-'+data['source']['sha256'][:16]
    return engine.command(round_id,operation_id,'evidence',dict(id=eid,revision=1,phase='final',source='course',
                           observed_at=observed_at,data=data))


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    ip=sub.add_parser('import');ip.add_argument('--source',required=True);ip.add_argument('--output',required=True)
    for action in ('list','show','source-hole','round-snapshot'):
        sp=sub.add_parser(action);sp.add_argument('--root');
        if action!='list':sp.add_argument('--course-id',default=COURSE_ID)
        if action=='source-hole':sp.add_argument('--hole-id',type=int,required=True)
    args=p.parse_args()
    if args.action=='import':out=import_source(args.source,args.output)
    elif args.action=='list':out=list_courses(args.root)
    elif args.action=='show':out=load(args.course_id,args.root)
    elif args.action=='source-hole':out=source_hole(args.hole_id,args.course_id,args.root)
    else:out=round_snapshot(args.course_id,args.root)
    print(json.dumps(out,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
