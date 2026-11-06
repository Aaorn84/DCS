"""Deterministic GPS transition evidence. Thresholds are unvalidated engineering defaults."""
import math
from shot_evidence import haversine
POLICY={'max_accuracy_m':15,'min_fixes':3,'dwell_seconds':15,'max_gap_seconds':15,'max_speed_mps':20}
def inside(box,p):
    dy=p['accuracy_m']/111000;dx=dy/max(.05,math.cos(math.radians(p['latitude'])))
    w,s,e,n=box
    return w<=p['longitude']-dx and p['longitude']+dx<=e and s<=p['latitude']-dy and p['latitude']+dy<=n

def observe(tracker, course, p, timestamp, now, active_hole):
    """Mutates round-local tracker only; never emits score or stroke facts."""
    result={'confirmed_hole':None,'reason':'candidate','accepted_position':True}
    last=tracker.get('last')
    if last and timestamp<=last['timestamp']:
        return dict(result,reason='duplicate_fix' if timestamp==last['timestamp'] and p==last['position'] else 'non_monotonic_fix',accepted_position=False)
    if not -5<=now-timestamp<=60 or p['accuracy_m']>POLICY['max_accuracy_m']:
        tracker['pending']=None
        return dict(result,reason='stale_or_inaccurate',accepted_position=False)
    if last:
        elapsed=timestamp-last['timestamp']
        distance=haversine(last['position'],p)
        if max(0,distance-last['position']['accuracy_m']-p['accuracy_m'])/elapsed>POLICY['max_speed_mps']:
            tracker['pending']=None
            return dict(result,reason='implausible_jump',accepted_position=False)
        if elapsed>POLICY['max_gap_seconds']:tracker['pending']=None
    tracker['last']={'timestamp':timestamp,'position':dict(p)}
    current=next((h for h in course['holes'] if h['number']==active_hole),None)
    if current and current.get('green_bbox'):
        if inside(current['green_bbox'],p):tracker['green_seen']=active_hole
        elif tracker.get('green_seen')==active_hole:
            # Require the uncertainty envelope to be wholly outside before leaving.
            w,s,e,n=current['green_bbox'];dy=p['accuracy_m']/111000;dx=dy/max(.05,math.cos(math.radians(p['latitude'])))
            if p['longitude']+dx<w or p['longitude']-dx>e or p['latitude']+dy<s or p['latitude']-dy>n:
                tracker['green_departure']=active_hole
    matches=[h['number'] for h in course['holes'] if h.get('tee_bbox') and inside(h['tee_bbox'],p)]
    if len(matches)!=1:
        tracker['pending']=None
        return dict(result,reason='outside_or_ambiguous_tee')
    target=matches[0];order=[h['number'] for h in course['holes']]
    if target==active_hole:
        tracker['pending']=None
        return dict(result,reason='current_hole')
    if active_hole is not None and (active_hole not in order or order.index(active_hole)+1>=len(order) or order[order.index(active_hole)+1]!=target):
        tracker['pending']=None
        return dict(result,reason='non_next_hole')
    if current and current.get('green_bbox') and tracker.get('green_departure')!=active_hole:
        tracker['pending']=None
        return dict(result,reason='green_departure_not_observed')
    pending=tracker.get('pending')
    if not pending or pending['hole']!=target:
        pending={'hole':target,'since':timestamp,'fixes':0};tracker['pending']=pending
    pending['fixes']+=1
    result.update(candidate_hole=target,fixes=pending['fixes'],dwell_seconds=timestamp-pending['since'])
    if pending['fixes']>=POLICY['min_fixes'] and timestamp-pending['since']>=POLICY['dwell_seconds']:
        tracker['pending']=None;tracker['green_seen']=None;tracker['green_departure']=None
        return dict(result,confirmed_hole=target,reason='stable_next_tee')
    return result
