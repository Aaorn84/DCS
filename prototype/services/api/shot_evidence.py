#!/usr/bin/env python3
"""Evidence gate for incomplete shot records; not GPS swing detection or storage.

Inputs are structured facts supplied by the APP/user, never inferred here from
silence. Only confirmed single-stroke ball-position pairs produce a total
horizontal distance. Caller still verifies currentness, authority and consent.
"""
import math
from datetime import datetime

VERSION = '0.1.0'  # component version, independent of skill/weather versions


class InputError(ValueError):
    pass


def number(value, name, low, high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise InputError(f'{name}: finite number required')
    if not low <= value <= high:
        raise InputError(f'{name}: out of range')
    return float(value)


def stamp(value):
    if not isinstance(value,str):
        raise InputError('timezone-aware position timestamp required')
    try:
        dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError as exc:
        raise InputError('invalid position timestamp') from exc
    if dt.tzinfo is None:
        raise InputError('position timestamp requires timezone')
    return dt


def position(raw):
    if raw is None:
        return None
    if not isinstance(raw,dict):
        raise InputError('position must be an object or null')
    return {'latitude':number(raw.get('latitude'),'latitude',-90,90),
            'longitude':number(raw.get('longitude'),'longitude',-180,180),
            'accuracy_m':number(raw.get('accuracy_m'),'accuracy_m',.01,20000),
            'observed_at':stamp(raw.get('observed_at')).isoformat(),
            'hole_id':raw.get('hole_id'),'crs':raw.get('crs'),
            'ball_position_confirmed':raw.get('ball_position_confirmed') is True}


def haversine(a,b):
    lat1,lat2=map(math.radians,(a['latitude'],b['latitude']))
    delta_lat=lat2-lat1
    delta_lon=math.radians(b['longitude']-a['longitude'])
    x=math.sin(delta_lat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(delta_lon/2)**2
    return 2*6371008.8*math.asin(math.sqrt(min(1.,max(0.,x))))


def assess(event):
    if not isinstance(event,dict):
        raise InputError('structured shot evidence required')
    result={'component_version':VERSION,'status':'unresolved','total_horizontal_m':None,
            'distance_type':'horizontal_start_to_finish_not_carry','usable_for_club_total_stats':False,
            'usable_for_carry_stats':False,'next_start_candidate':None,'followup_field':None,
            'missing_fields':[]}
    if event.get('recording_consent') is not True:
        result['status']='disabled'
        return result
    budget=number(event.get('max_position_error_sum_m'),'max_position_error_sum_m',.01,200)
    start,end=position(event.get('start')),position(event.get('end'))
    missing=result['missing_fields']
    for name,p in (('start',start),('end',end)):
        if p is None:
            missing.append(name)
        elif p['crs']!='WGS84':
            missing.append(name+'_coordinate_reference')
        elif not p['ball_position_confirmed']:
            missing.append(name+'_ball_position')
        elif not isinstance(p['hole_id'],str) or not p['hole_id']:
            missing.append(name+'_hole')
        elif p['accuracy_m']>budget:
            missing.append(name+'_accuracy')
    if end and not any(x=='end' or x.startswith('end_') for x in missing):
        # This is a candidate only, never a statement that the next shot occurred.
        result['next_start_candidate']=dict(end)
    link=(event.get('single_stroke_confirmed') is True
          and type(event.get('intervening_strokes')) is int and event['intervening_strokes']==0
          and event.get('relief_or_provisional') is False and event.get('gap_open') is False)
    if not link:
        missing.append('single_stroke_link')
    if start and end:
        if start['hole_id']!=end['hole_id']:
            missing.append('same_hole_link')
        if stamp(end['observed_at'])<=stamp(start['observed_at']):
            missing.append('time_order')
            result['next_start_candidate']=None
        error=start['accuracy_m']+end['accuracy_m']
        result['position_accuracy_sum_m']=error
        if error>budget:
            missing.append('combined_position_accuracy')
    club_known=(event.get('club_confirmed') is True
                and isinstance(event.get('club_id'),str) and bool(event['club_id'].strip()))
    if not club_known:
        missing.append('club_id')
    blocking=[x for x in missing if x!='club_id']
    if not blocking:
        distance=haversine(start,end)
        if distance<=result['position_accuracy_sum_m']:
            missing.append('movement_below_position_accuracy')
        else:
            result['total_horizontal_m']=distance
            result['status']='confirmed_total' if club_known else 'unassigned_total'
            result['usable_for_club_total_stats']=club_known
    if result['status']=='unresolved':
        # One field is suggested, not multiple user questions or an instruction to speak.
        if 'single_stroke_link' in missing:
            result['followup_field']='single_stroke_link'
        elif 'end_ball_position' in missing:
            result['followup_field']='end_ball_position'
        elif 'start' in missing:
            result['followup_field']='start_position_if_recoverable'
    elif not club_known:
        result['followup_field']='club_id'
    return result
