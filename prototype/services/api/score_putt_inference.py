"""Infer putts only from a complete tee-started ledger reaching the green."""
from round_state import canonical,fact_value
from shot_evidence import haversine

def known_nonputts(state,hole_number):
    from ball_rules import ball_counts
    from tee_geometry import mapped_polygons
    from lie_position import polygon_contains
    j=state.get('journey',{});rid=(j.get('round') or {}).get('id');eid=fact_value(state,'context.course_snapshot')
    key=[rid,eid,hole_number];flow=j.get('ball_rules',{}).get(canonical(key))
    if not flow or flow.get('pending'):return None
    events=[item for item in flow['sequence'] if item.get('active',True) and ball_counts(flow,item['ball_id'])]
    strokes=[item for item in events if item['kind']=='stroke']
    if not strokes:return None
    course=state.get('evidence',{}).get(eid,{}).get('data',{})
    hole=next((h for h in course.get('holes',[]) if h['number']==hole_number),None)
    if not hole:return None
    tee=hole.get('simulation_positions',{}).get('tee')
    origin=strokes[0].get('origin')
    if not origin:return None
    at_tee=bool(tee and haversine(tee,origin)<=10)
    box=hole.get('tee_bbox')
    if not at_tee and isinstance(box,list) and len(box)==4:
        from gps_transition import inside
        at_tee=inside(box,origin)
    if not at_tee:return None
    nonputts=[item for item in strokes if item.get('club')!='推杆']
    if not nonputts:return None
    last=nonputts[-1];report=j.get('reported_landing',{})
    green_report=(report.get('scope')==canonical(key) and report.get('stroke_id')==last['id'] and report.get('lie')=='果岭')
    point=last.get('landing')
    green_point=False
    if point:
        green=hole.get('simulation_positions',{}).get('green')
        green_point=bool(green and haversine(green,point)<=2)
        if not green_point:
            green_point=any(polygon_contains(rings,{**point,'accuracy_m':0}) for rings in mapped_polygons(hole,course.get('reference_simulation') is True)['green'].values())
    if not green_report and not green_point:return None
    penalties=sum(item['amount'] for item in events if item['kind']=='penalty')
    return dict(nonputts=len(nonputts),penalties=penalties)
