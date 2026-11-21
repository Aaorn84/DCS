"""Join explicit shot confirmations to ledger strokes by evidence identity."""
import copy
from datetime import datetime
from round_state import canonical
from shot_evidence import haversine

def sync_flow(state,flow):
    from ball_rules import add_stroke,last_stroke
    j=state.get('journey',{})
    if flow.get('revision',0)<111:return
    since=j.get('simulation_attempts',{}).get(canonical(flow['scope']))
    for record in j.get('confirmed_shot_distances',[]):
        if record.get('scope')!=flow['scope'] or not record.get('valid') or record.get('inferred_from_score'):continue
        endpoints=record.get('endpoints',[])
        if len(endpoints)!=2:continue
        if not all(all(state.get('evidence',{}).get(eid,{}).get('active') and state['evidence'][eid].get('phase')=='final' for eid in p.get('evidence_ids',[])) for p in endpoints):continue
        if since:
            stamps=[state['evidence'][eid].get('observed_at','') for eid in endpoints[-1].get('evidence_ids',[])]
            if not any(stamp and datetime.fromisoformat(stamp.replace('Z','+00:00'))>=datetime.fromisoformat(since.replace('Z','+00:00')) for stamp in stamps):continue
        start,end=endpoints
        candidates=[item for item in flow['sequence'] if item['kind']=='stroke' and item.get('active',True)
                    and (item.get('pair_ids')==record.get('pair_ids') or item['id']==record['id'] or item.get('confirmation_record_id')==record['id'])]
        if not candidates:
            candidates=[item for item in flow['sequence'] if item['kind']=='stroke' and item.get('active',True)
                        and item.get('origin') and haversine(item['origin'],start['point'])<=5
                        and (not item.get('landing') or haversine(item['landing'],end['point'])<=5)]
        if len(candidates)>1:continue
        report=j.get('previous_club_reports',{}).get(canonical([*flow['scope'],*record['pair_ids']]),{})
        club=report.get('club') or record.get('club')
        if candidates:
            stroke=candidates[0]
        elif ((record.get('confirmation_event_id') or record.get('simulated_landing'))
              and not flow.get('pending') and not flow.get('incidents')):
            add_stroke(flow,record['id'],flow['active_ball'],club,start['point'],end['point'],record['pair_ids'])
            stroke=last_stroke(flow)
        else:continue
        stroke.update(origin=copy.deepcopy(start['point']),landing=copy.deepcopy(end['point']),
                      pair_ids=list(record['pair_ids']),distance_m=record['total_horizontal_m'],confirmation_record_id=record['id'])
        if club:stroke['club']=club
        opening=flow.get('open_shot') or {}
        if not opening.get('stroke_id') and opening.get('origin') and haversine(opening['origin'],start['point'])<=5:
            stamp=opening.get('observed_at')
            observed=[state['evidence'][eid].get('observed_at') for eid in end.get('evidence_ids',[])]
            if stamp and any(value and datetime.fromisoformat(value.replace('Z','+00:00'))>=datetime.fromisoformat(stamp.replace('Z','+00:00')) for value in observed):
                opening['stroke_id']=stroke['id']
        if opening.get('stroke_id')==stroke['id']:
            opening['landed']=True
    # A later explicit club correction can exist without another distance event.
    for stroke in flow['sequence']:
        if stroke['kind']!='stroke' or not stroke.get('pair_ids'):continue
        report=j.get('previous_club_reports',{}).get(canonical([*flow['scope'],*stroke['pair_ids']]),{})
        if report.get('club'):stroke['club']=report['club']

def sync(state):
    journey=state.get('journey',{});round_id=(journey.get('round') or {}).get('id')
    for flow in journey.get('ball_rules',{}).values():
        if flow.get('scope',[None])[0]==round_id:sync_flow(state,flow)
