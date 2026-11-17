"""Map-derived tee targets for a known carry, using the current tee as the origin."""
import math

from lie_position import polygon_contains
from round_state import fact_value


def valid_ring(ring):
    return (isinstance(ring, list) and len(ring) >= 4 and ring[0] == ring[-1]
            and all(isinstance(vertex, list) and len(vertex) == 2
                    and all(type(value) in (int, float) and math.isfinite(value) for value in vertex)
                    for vertex in ring))


def mapped_polygons(hole, simulation):
    polygons = {kind: {} for kind in ('fairway', 'green', 'bunker', 'water', 'ob')}
    if simulation:
        kinds = {'FairwayTrace': 'fairway', 'GreenTrace': 'green', 'BunkerTrace': 'bunker', 'WaterTrace': 'water'}
        for path in hole.get('display_paths', []):
            kind = kinds.get(path['kind'])
            if kind and len(path['points']) >= 3:
                ring = [[point['longitude'], point['latitude']] for point in path['points']]
                closed = ring if ring[0] == ring[-1] else ring+[ring[0]]
                if valid_ring(closed):
                    polygons[kind][path['id']] = [closed]
    for zone in hole.get('surface_zones', []):
        kind = zone.get('surface')
        geometry = zone.get('geometry', {})
        rings = geometry.get('coordinates')
        if (kind in polygons and zone.get('verified') is True and zone.get('source')
                and geometry.get('type') == 'Polygon' and isinstance(rings, list)
                and rings and all(valid_ring(ring) for ring in rings)):
            polygons[kind][zone['id']] = rings
    return polygons


def edges(ring):
    return zip(ring, ring[1:])


def corridor_edges(rings, width, end):
    """Check a projected corridor, with x to the right and y down the aim line."""
    for ring in rings:
        for (x, y), (u, v) in edges(ring):
            if max(y, v) < 0 or min(y, v) > end or max(x, u) < -width or min(x, u) > width:
                continue
            # Clip the edge to the lateral band and test the resulting depth range.
            if x != u:
                enter, leave = sorted(((-width-x)/(u-x), (width-x)/(u-x)))
                y, v = y + max(0, enter)*(v-y), y + min(1, leave)*(v-y)
            if max(y, v) >= 0 and min(y, v) <= end:
                yield min(end, max(y, v))


def corridor_hits(rings, width, end):
    return next(corridor_edges(rings, width, end), None) is not None


ROLL_IN_CLUBS=('three_wood','five_wood','hybrid','long_iron','iron3','iron4')
MAX_ROLL_IN_YARDS=10


def tee_targets(state, analysis, clubs, *, origin=None, allow_crossing=False, surface='fairway',
                roll_in=False):
    course = state['evidence'][analysis['course_evidence']]['data']
    hole = next(h for h in course['holes'] if h['number'] == analysis['hole'])
    polygons = mapped_polygons(hole, course.get('reference_simulation') is True)
    if not polygons[surface]:
        return []
    origin = origin or fact_value(state, 'context.device_position')
    green = next(o for o in hole['objects'] if o['kind'] == 'green_center')
    scale = 111195 * math.cos(math.radians(origin['latitude']))
    if scale <= 1:
        return []

    def xy(lon, lat):
        return (lon-origin['longitude'])*scale, (lat-origin['latitude'])*111195

    def point(east, north):
        return {'longitude': origin['longitude']+east/scale,
                'latitude': origin['latitude']+north/111195, 'accuracy_m': 0}

    def project(rings):
        return [[xy(*vertex) for vertex in ring] for ring in rings]

    landing_areas = [(rings, project(rings)) for rings in polygons[surface].values()]
    obstacle_rings = [rings for kind in ('bunker', 'water', 'ob') for rings in polygons[kind].values()]
    obstacles = [project(rings) for rings in obstacle_rings]
    run_in_surfaces = list(polygons['fairway'].values()) + list(polygons['green'].values())
    at_tee = point(0, 0)
    if any(polygon_contains(rings, at_tee) for rings in obstacle_rings):
        return []
    bunkers = []
    for rings in polygons['bunker'].values():
        vertices = project(rings)[0][:-1]
        east = sum(x for x, _ in vertices)/len(vertices)
        north = sum(y for _, y in vertices)/len(vertices)
        bunkers.append((math.hypot(east, north), east, north))
    bunkers.sort()
    bearing = math.atan2(*xy(green['longitude'], green['latitude']))
    margin = max(5*.9144, origin['accuracy_m'])
    # A planning band around a single reported carry, with no estimated roll.
    targets = []
    for key, club in clubs:
        if roll_in and key not in ROLL_IN_CLUBS:
            continue
        carry_yards = club['carry_yards']
        low_yards, high_yards = carry_yards-5, carry_yards+5
        carry, low, high = (yards*.9144 for yards in (carry_yards, low_yards, high_yards))
        if low <= margin:
            continue
        runs = []
        for offset in range(-75, 76):
            angle = bearing + math.radians(offset)
            east, north = math.sin(angle), math.cos(angle)

            def aim_rings(rings):
                return [[(x*north-y*east, x*east+y*north) for x, y in ring] for ring in rings]

            midpoint = point(east*carry, north*carry)
            end=high
            roll=0
            if roll_in:
                # Test the nominal first bounce and the mapped ground run to the green.
                if any(polygon_contains(rings,midpoint) for rings,_ in landing_areas):
                    continue
                for yards in range(MAX_ROLL_IN_YARDS+1):
                    depth=carry+yards*.9144
                    sample=point(east*depth,north*depth)
                    if not any(polygon_contains(rings,sample) for rings in run_in_surfaces):
                        break
                    if yards and any(polygon_contains(rings,sample) for rings,_ in landing_areas):
                        roll=yards
                        end=depth
                        break
                if not roll:
                    continue
            else:
                # A surface edge inside the band would interrupt the landing corridor.
                in_area=any(polygon_contains(rings,midpoint) and not corridor_hits(
                    [[(x,y-low) for x,y in ring] for ring in aim_rings(projected)],
                    margin,high-low) for rings,projected in landing_areas)
                if not in_area:
                    continue
            if any(polygon_contains(rings,midpoint) for rings in obstacle_rings):
                continue
            crossing=max((far for rings in obstacles
                          for far in corridor_edges(aim_rings(rings),margin,end)),default=None)
            if crossing is not None and (not allow_crossing or crossing+margin>=low):
                continue
            if not runs or runs[-1][-1][0] != offset-1:
                runs.append([])
            runs[-1].append((offset, east, north, crossing, roll))
        if not runs:
            continue
        run = max(runs, key=lambda row: (len(row), -abs(row[len(row)//2][0])))
        offset, east, north, crossing, roll = run[len(run)//2]
        width = 2*low*math.sin(math.radians((len(run)-1)/2)) + 2*margin
        nearby = []
        for index, (distance, x, y) in enumerate(bunkers):
            lateral, along = x*north-y*east, x*east+y*north
            if along > 0 and margin < abs(lateral) <= 45*.9144 and abs(along-carry) <= 65*.9144:
                nearby.append((math.hypot(lateral, along-carry), index, distance, lateral, x, y))
        reference = None
        if nearby:
            _, index, distance, lateral, x, y = min(nearby)
            side = '右' if lateral > 0 else '左'
            bunker_side = '右' if x*math.cos(bearing)-y*math.sin(bearing) > 0 else '左'
            rank = ('近处' if index == 0 else '远处') if len(bunkers) == 2 else ''
            reference = dict(rank=rank, bunker_side=bunker_side, aim_side='左' if side == '右' else '右',
                             distance_m=distance)
        targets.append(dict(club_key=key, club=club['label'], carry_yards=carry_yards,
                            low_yards=low_yards, high_yards=high_yards, width_m=width, offset=offset, reference=reference,
                            crossing_m=crossing, aim_point=point(east*carry, north*carry),
                            **({'roll_yards':roll} if roll else {})))
    return targets


def landing_space(hole, simulation, origin, target, surface, roll_yards=0):
    """Measure cross-track room and nearby mapped hazard edges at a candidate landing."""
    polygons=mapped_polygons(hole,simulation)
    scale=111195*math.cos(math.radians(origin['latitude']))
    dx=(target['longitude']-origin['longitude'])*scale
    dy=(target['latitude']-origin['latitude'])*111195
    distance=math.hypot(dx,dy)
    if not distance or not polygons[surface]:
        return {'width_m':0,'depth_m':0,'hazards':[]}
    east,north=dx/distance,dy/distance
    entry=roll_yards*.9144

    def inside(lateral,along):
        point=dict(longitude=target['longitude']+(east*along+north*lateral)/scale,
                   latitude=target['latitude']+(north*along-east*lateral)/111195,
                   accuracy_m=0)
        return any(polygon_contains(rings,point) for rings in polygons[surface].values())

    def extent(across,sign):
        for step in range(1,101):
            if not inside(sign*step if across else 0,entry if across else entry+sign*step):
                return step-1
        return 100

    width=extent(True,-1)+extent(True,1) if inside(0,entry) else 0
    depth=extent(False,-1)+extent(False,1) if width else 0
    hazards=[]
    for kind in ('bunker','water','ob'):
        for rings in polygons[kind].values():
            nearest=None
            for ring in rings:
                points=[((lon-target['longitude'])*scale,(lat-target['latitude'])*111195)
                        for lon,lat in ring]
                for (x,y),(u,v) in edges(points):
                    dx,dy=u-x,v-y
                    length=dx*dx+dy*dy
                    fraction=max(0,min(1,-(x*dx+y*dy)/length)) if length else 0
                    x,y=x+fraction*dx,y+fraction*dy
                    candidate=(math.hypot(x,y),x*north-y*east)
                    if nearest is None or candidate[0]<nearest[0]:
                        nearest=candidate
            if nearest and nearest[0]<=35*.9144:
                distance,lateral=nearest
                side='右侧' if lateral>2 else '左侧' if lateral< -2 else '沿线'
                hazards.append(dict(kind=kind,side=side,distance_m=distance))
    return dict(width_m=width,depth_m=depth,hazards=hazards)
