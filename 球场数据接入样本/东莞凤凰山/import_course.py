"""Phoenix Hill source adapter. Python 3 stdlib only; no spatial inference."""
import argparse, collections, hashlib, json
from pathlib import Path
VERSION = '0.1.1'
def dump(value, path):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def normalize(raw, source_sha256, confirmation=None):
    if confirmation is not None:
        if (confirmation.get('source_sha256') != source_sha256
                or confirmation.get('public_id') != raw.get('publicId')
                or confirmation.get('crs') != 'WGS84'):
            raise ValueError('CRS confirmation does not match this source version')
    if raw.get('publicId') != 'B87QFJP7':
        raise ValueError('Unsupported source identity')
    roots = {h['holeId']: h for h in raw['holes']}
    if len(roots) != len(raw['holes']):
        raise ValueError('Duplicate hole ID')
    courses, ownership = [], {}
    for ci, c in enumerate(raw['courses']):
        tees, order = [], None
        for ti, t in enumerate(c['tees']):
            hs = sorted(t['holes'], key=lambda h:h['holeNumber'])
            ids = [h['holeId'] for h in hs]
            if len(set(ids)) != len(ids) or [h['holeNumber'] for h in hs] != list(range(1, len(hs)+1)):
                raise ValueError('Invalid hole order')
            if order is not None and order != ids:
                raise ValueError('Tee hole membership/order conflict')
            order = ids
            facts=[]
            for h in hs:
                hi=t['holes'].index(h)
                hid=h['holeId']
                if hid not in roots: raise ValueError('Orphan tee hole')
                prior=ownership.get(hid)
                identity=(c['courseId'], h['holeNumber'], h['par'])
                if prior is not None and prior != identity: raise ValueError('Conflicting hole identity/par')
                ownership[hid]=identity
                facts.append({'hole_id':hid,'source_hole_number':h['holeNumber'],'par':h['par'],
                    'published_yardage':h['yardage'],'allocation_raw':h['allocation'],
                    'source_path':f'/courses/{ci}/tees/{ti}/holes/{hi}',
                    'updated_on_raw':h.get('updateOn'),'data_stats_raw':h.get('holeDataStats')})
            if sum(h['par'] for h in hs)!=t['par'] or sum(h['yardage'] for h in hs)!=t['yardage']:
                raise ValueError('Tee total mismatch')
            tees.append({'tee_id':t['teeId'],'name':t['teeName'],'color':t['teeColorType'],
                'par':t['par'],'published_yardage':t['yardage'],'rating':t.get('rating'),
                'slope_rating':t.get('slope'),'updated_on_raw':t.get('updateOn'),
                'source_path':f'/courses/{ci}/tees/{ti}','holes':facts})
        courses.append({'course_id':c['courseId'],'name':c['name'],'hole_ids_in_play_order':order,'tees':tees})
    if set(ownership)!=set(roots): raise ValueError('Unassigned root hole')
    holes=[]
    for i,h in enumerate(raw['holes']):
        course_id,number,par=ownership[h['holeId']]
        holes.append({'hole_id':h['holeId'],'course_id':course_id,'source_hole_number':number,
            'name':h['holeName'],'par':par,'par_basis':'consistent nested tee hole records',
            'root_par_raw':h['par'],'source_path':f'/holes/{i}',
            'reference_coordinates':{k:h.get(k) for k in ('teeGPSCoordinate','greenGPSCoordinate','approachGPSCoordinate')},
            'reference_policy':'source references only; not flag, actual ball position or colored tee position'})
    geometry=[]
    for i,g in enumerate(raw['data']):
        if g['holeId'] not in roots: raise ValueError('Orphan geometry')
        for p in [g.get('gpsCoordinate')]+[p for part in g['shapes'] for p in part]:
            if p is not None and (not -90<=p['latitude']<=90 or not -180<=p['longitude']<=180):
                raise ValueError('Invalid coordinate range')
        geometry.append({'source_path':f'/data/{i}','hole_id':g['holeId'],'source_type':g['gpsType'],
            'reference_coordinate':g.get('gpsCoordinate'),'source_paths':g['shapes'],
            'explicitly_closed':[bool(s and s[0]==s[-1]) for s in g['shapes']]})
    return {'schema_version':VERSION,'adapter':'phoenix-hill','source':{'public_id':raw['publicId'],
        'sha256':source_sha256,'name':raw['name'],'updated_on_raw':raw.get('updatedOn'),
        'data_stats_raw':raw.get('courseGroupDataStats'),'timestamp_timezone':None},
        'coordinate_confirmation':confirmation,'facility_raw':raw['facility'],'capabilities':{'business_catalogue':True,'spatial_use_allowed':False,
        'crs':'WGS84' if confirmation else None,'coordinate_status':'user_confirmed' if confirmation else 'unverified',
        'coordinate_accuracy_status':'not_field_validated','reference_point_distance_enabled':bool(confirmation),
        'polygon_operations_enabled':False,'elevation_available':False,'green_slope_available':False},
        'semantics':{'yardage_unit':'yd','yardage_unit_basis':'source field name; not independently verified',
        'yardage_kind':'published tee length; not GPS displacement or carry',
        'allocation_scope':'raw source scope; not merged into an 18-hole handicap order',
        'geometry':'unclassified multipart source paths; no implicit polygon closure',
        'weather':'facility averages are not live weather; units/time unverified'},
        'courses':courses,'holes':holes,'geometry_records':geometry}
def report(d):
    gs=d['geometry_records']; paths=[p for g in gs for p in g['source_paths']]
    return {'schema_version':VERSION,'source_sha256':d['source']['sha256'],
        'counts':{'courses':len(d['courses']),'physical_holes':len(d['holes']),
        'tee_configurations':sum(len(c['tees']) for c in d['courses']),
        'tee_hole_records':sum(len(t['holes']) for c in d['courses'] for t in c['tees']),
        'geometry_records':len(gs),'parts':len(paths),'vertices':sum(map(len,paths)),
        'explicitly_closed_parts':sum(sum(g['explicitly_closed']) for g in gs)},
        'geometry_types':dict(collections.Counter(g['source_type'] for g in gs)),
        'warnings':[('WGS84 confirmed by user; field accuracy not validated' if d['coordinate_confirmation'] else 'CRS unknown: spatial runtime integration blocked'),
        'Open source paths: polygon topology not verified','HoleBoundry is not confirmed OB',
        'WaterTrace is not a designated penalty-area boundary',
        'Reference coordinates do not identify actual ball positions or individual colored tees',
        'Missing bunker record does not prove absence of bunker','Source timestamps have no timezone',
        'No elevation or green slope data; slope_rating is a separate tee rating field']}
def demo_route(d):
    result=[]
    for cid,tid in [(30914,650688),(30915,650692)]:
        c=next(c for c in d['courses'] if c['course_id']==cid)
        t=next(t for t in c['tees'] if t['tee_id']==tid)
        for h in t['holes']:
            result.append({'round_hole_number':len(result)+1,'course_id':cid,'tee_id':tid,**h})
    return {'schema_version':VERSION,'status':'example_selection_only_not_official_route',
        'spatial_use_allowed':False,'holes':result,'par':sum(h['par'] for h in result),
        'published_yardage':sum(h['published_yardage'] for h in result)}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('source');ap.add_argument('--output',default='data');ap.add_argument('--confirmation',default=str(Path(__file__).with_name('coordinate-confirmation.json')));a=ap.parse_args()
    b=Path(a.source).read_bytes();d=normalize(json.loads(b),hashlib.sha256(b).hexdigest(),json.loads(Path(a.confirmation).read_text(encoding='utf-8')))
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    for filename,value in [('course.normalized.json',d),('quality-report.json',report(d)),('route-ab-blue.example.json',demo_route(d))]:
        dump(value,out/filename)
if __name__=='__main__':main()
