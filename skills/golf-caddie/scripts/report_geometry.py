"""Read-only surface classification for reports; never produces a golf strategy."""
import math

def inside(box,p):
    dy=p.get('accuracy_m',0)/111000;dx=dy/max(.05,math.cos(math.radians(p['latitude'])))
    w,s,e,n=box
    return w<=p['longitude']-dx and p['longitude']+dx<=e and s<=p['latitude']-dy and p['latitude']+dy<=n

from surface_uncertainty import polygon_contains as _uncertainty_contains
from contextvars import ContextVar
from functools import wraps
_geometry_cache=ContextVar('planning_geometry_cache',default=None)

def planning_geometry_cache(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        if _geometry_cache.get() is not None:return function(*args,**kwargs)
        token=_geometry_cache.set({})
        try:return function(*args,**kwargs)
        finally:_geometry_cache.reset(token)
    return wrapped



def polygon_contains(rings,point):
    # Geometry here comes from mapped_polygons, which already validates rings.
    # Generated exact sample points need ray casting, not a GPS disk distance
    # calculation against every edge. Real uncertainty still uses the full check.
    if point['accuracy_m']!=0:return _uncertainty_contains(rings,point)
    px,py=point['longitude'],point['latitude']
    cache=_geometry_cache.get()
    key=('prepared_rings',id(rings))
    prepared=cache.get(key) if cache is not None else None
    if prepared is None:
        bounds=[]
        for ring in rings:
            xs=[v[0] for v in ring];ys=[v[1] for v in ring]
            bounds.append((min(xs),min(ys),max(xs),max(ys),tuple(zip(ring,ring[1:]))))
        prepared=(rings,bounds)  # Retain input identity for the lifetime of this plan.
        if cache is not None:cache[key]=prepared
    outer=False
    for index,(left,bottom,right,top,edges) in enumerate(prepared[1]):
        if px<left or px>right or py<bottom or py>top:
            if index==0:return False
            continue
        hit=False
        for (x,y),(u,v) in edges:
            cross=(px-x)*(v-y)-(py-y)*(u-x)
            if cross==0 and min(x,u)<=px<=max(x,u) and min(y,v)<=py<=max(y,v):return False
            if (y>py)!=(v>py) and px<x+(u-x)*(py-y)/(v-y):hit=not hit
        if index==0:
            if not hit:return False
            outer=hit
        elif hit:return False
    return outer


def valid_ring(ring):
    return (isinstance(ring, list) and len(ring) >= 4 and ring[0] == ring[-1]
            and all(isinstance(vertex, list) and len(vertex) == 2
                    and all(type(value) in (int, float) and math.isfinite(value) for value in vertex)
                    for vertex in ring))


def mapped_polygons(hole, simulation):
    cache=_geometry_cache.get()
    key=('polygons',id(hole),simulation)
    if cache is not None and key in cache:return cache[key]
    result=_mapped_polygons(hole,simulation)
    if cache is not None:cache[key]=result
    return result

def _mapped_polygons(hole, simulation):
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
