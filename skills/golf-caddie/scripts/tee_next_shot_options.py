"""Tee choices compared with the following green approach, not width alone."""
from shot_evidence import haversine
import math

def bunker_band(hole,simulation,origin,target):
    if not origin:return None
    from tee_geometry import mapped_polygons
    cosine=math.cos(math.radians(origin['latitude']))
    def xy(p):return ((p['longitude']-origin['longitude'])*111195*cosine,(p['latitude']-origin['latitude'])*111195)
    x,y=xy(target['aim_point']);length=math.hypot(x,y)
    if not length:return None
    bands=[]
    for rings in mapped_polygons(hole,simulation)['bunker'].values():
        coords=[xy(dict(longitude=a,latitude=b)) for a,b in rings[0]]
        along=[(a*x+b*y)/length for a,b in coords];side=[(a*y-b*x)/length for a,b in coords]
        gap=max(0,min(side),-max(side))
        near,far=min(along),max(along)
        if gap<=20*.9144 and far>0 and target.get('low_yards',target['carry_yards']-5)*.9144<=far and target.get('high_yards',target['carry_yards']+5)*.9144>=near:bands.append((max(0,near),far))
    return min(bands) if bands else None


def compare(state,a,targets,unit,*,requested_alternative=False):
    if not targets:return None
    from tee_strategy import aiming_text,crossing_text,reported_carry_clubs
    from tee_geometry import landing_space
    course=state['evidence'][a['course_evidence']]['data'];hole=next(h for h in course['holes'] if h['number']==a['hole'])
    green=next(o for o in hole['objects'] if o['kind']=='green_center')
    profile=state['journey'].get('profile',{})
    known=reported_carry_clubs(profile)
    longest=max((club['carry_yards'] for key,club in known.items() if key!='driver'),default=0)
    # Expand the sand-front search beyond the few explicitly reported clubs.
    # Estimated mid irons are candidates only, clearly labelled and never saved as facts.
    origin=state.get('facts',{}).get('context.device_position',{}).get('value')
    estimates={}
    if any(bunker_band(hole,course.get('reference_simulation') is True,origin,t) for t in targets):
        from iron_estimates import iron_table
        from tee_geometry import tee_targets
        reported_labels={v['label'] for v in known.values()}
        for n,v in iron_table(profile).items():
            if n not in (5,6) or str(n)+'号铁' in reported_labels:continue
            key='iron'+str(n);estimates[key]=dict(label=str(n)+'号铁',**v)
        if estimates:
            extra=tee_targets(state,a,list(estimates.items()),origin=origin,allow_crossing=True)
            targets=list(targets)+extra
    grouped={}
    for target in targets:
        if target['club_key'] not in grouped or target['width_m']>grouped[target['club_key']]['width_m']:
            grouped[target['club_key']]=target
    from hole_history import weight as history_weight,note as history_note
    origin=state.get('facts',{}).get('context.device_position',{}).get('value')
    candidates=[]
    for target in grouped.values():
        remaining=haversine(target['aim_point'],green)/.9144
        # Nearby hazards and limited carry clearance remain risk factors, not
        # automatic rejection merely because the aim line crosses an obstacle.
        space=landing_space(hole,course.get('reference_simulation') is True,
                            state.get('facts',{}).get('context.device_position',{}).get('value',target['aim_point']),target['aim_point'],'fairway')
        penalty=sum(h['kind'] in ('water','ob') and h['distance_m']<=15*.9144 for h in space['hazards'])
        sand=sum(h['kind']=='bunker' and h['distance_m']<=10*.9144 for h in space['hazards'])
        clearance=target.get('low_yards',target['carry_yards']-5)-(target['crossing_m']/.9144) if target.get('crossing_m') is not None else None
        crossing=2 if clearance is not None and clearance<=10 else 1 if clearance is not None and clearance<=20 else 0
        history=history_weight(state,a['hole'],origin,target['aim_point'],target['club'])
        band=bunker_band(hole,course.get('reference_simulation') is True,origin,target)
        if band:sand=max(sand,1)
        risk=(penalty,sand,crossing,history)
        approach=landing_space(hole,course.get('reference_simulation') is True,target['aim_point'],green,'green')
        narrow=bool(approach['width_m'] and approach['width_m']<20*.9144) or sum(h['kind']=='bunker' for h in approach['hazards'])>=2
        candidates.append(dict(target=target,remaining=remaining,risk=risk,space=space,narrow=narrow,history=history,bunker_band=band))
    def dominates(left,right):
        # Dominance requires no worse distance, width, or any hazard factor.
        return (left['remaining']<=right['remaining']+1 and left['target']['width_m']>=right['target']['width_m']
                and all(x<=y for x,y in zip(left['risk'],right['risk']))
                and (left['remaining']<right['remaining']-1 or left['target']['width_m']>right['target']['width_m']+1 or left['risk']!=right['risk']))
    frontier=[row for row in candidates if not any(dominates(other,row) for other in candidates if other is not row)]
    primary=min(frontier,key=lambda row:(row['risk'][0],row['remaining']+20*row['history'],row['risk'],-row['target']['width_m']))
    alternatives=[row for row in frontier if row is not primary and
                  (row['target']['width_m']-primary['target']['width_m']>=max(5*.9144,primary['target']['width_m']*.15)
                   or row['risk']<primary['risk']) and row['target']['width_m']>=20*.9144]
    reachable=[row for row in alternatives if not longest or row['remaining']<=longest+10]
    if reachable:alternatives=reachable
    chosen=[primary]
    if alternatives:
        # Among comparable risk levels, keep the greatest useful advance.
        best_risk=min(row['risk'] for row in alternatives)
        reduced=[row for row in alternatives if row['risk']==best_risk]
        if best_risk<primary['risk']:alternatives=reduced
        def tradeoff(row):
            gain=(row['target']['width_m']-primary['target']['width_m'])/.9144
            extra=max(0,row['remaining']-primary['remaining'])
            # Longer approaches into tight green geometry reduce the benefit
            # of a wider tee landing. This is a planning heuristic, not odds.
            value=gain/(1+extra/40*(2 if row['narrow'] else 1))
            return (row['risk']<primary['risk'],-extra if row['risk']<primary['risk'] else value,value)
        alternative=max(alternatives,key=tradeoff)
        if alternative['risk']<primary['risk'] or tradeoff(alternative)[1]>=3:
            chosen.append(alternative)
    # These are screening margins, not personal dispersion or predicted roll.
    roll_clearance_yards=30
    supplied=profile.get('tee_roll_clearance',{})
    value=supplied.get('value',{})
    if supplied.get('source')=='user_report' and isinstance(value,dict) and type(value.get('yards')) in (int,float) and 10<=value['yards']<=80:
        roll_clearance_yards=value['yards']
    safer=None
    if primary['bunker_band']:
        near=primary['bunker_band'][0]
        conservative=[row for row in candidates if row is not primary and not row['bunker_band']
                      and not row['risk'][0] and not row['risk'][1]
                      and row['target']['width_m']>=20*.9144
                      and (row['target'].get('high_yards',row['target']['carry_yards']+5)+roll_clearance_yards)*.9144<=near]
        if conservative:
            # Reserve 30 yards beyond the upper Carry band for roll and clearance;
            # this is a screening margin, never a prediction of actual roll.
            safer=min(conservative,key=lambda row:(row['remaining'],-row['target']['width_m']))
            chosen=[primary,safer]
    finder=(profile.get('fairway_finder',{}).get('value') or {}).get('club_key')
    trusted=next((row for row in candidates if row['target']['club_key']==finder
                  and all(x<=y for x,y in zip(row['risk'],primary['risk'])) and row['target']['width_m']>=20*.9144),None)
    if trusted is not None and trusted is not primary:chosen=[primary,trusted]
    if not requested_alternative and primary['target']['club_key']=='driver' and not primary['risk'][0] and not primary['history'] and not primary['bunker_band'] and primary['target']['width_m']>=20*.9144:
        driver=primary['target']
        far=driver.get('crossing_m')
        if far is None:
            from tee_club_query import bunker_clearance
            far=bunker_clearance(state,a,driver,driver['carry_yards'],unit,distance_only=True)
        # The lower end of the Carry band must clear the mapped far edge.
        # Missing edge evidence does not imply clear passage.
        if far is not None and driver.get('low_yards',driver['carry_yards']-5)*.9144>far:
            chosen=[primary];safer=None
    from tee_decision_framework import preference
    from round_state import canonical
    from hole_history import _signature
    context=canonical([(state['journey'].get('round') or {}).get('id'),a.get('course_evidence'),a.get('hole'),a.get('position_version'),origin,_signature(hole)])
    learned=preference(state['journey'])
    # Learned style only changes order among options with no worse mapped risks.
    # It never manufactures dispersion, changes Carry, or removes a safer option.
    if learned=='control' and len(chosen)>1:
        suitable=[row for row in chosen[1:] if all(x<=y for x,y in zip(row['risk'],chosen[0]['risk']))]
        if suitable:
            preferred=min(suitable,key=lambda row:(row['target']['club_key']!=finder,row['risk'],row['remaining']))
            chosen=[preferred]+[row for row in chosen if row is not preferred]
    pairs=[row['target'] for row in chosen]
    scale=.9144 if unit=='米' else 1
    lines=[];options=[]
    for target in pairs:
        aim=aiming_text(target,unit)
        left=haversine(target['aim_point'],green)/.9144
        tee_width=round(target['width_m']/.9144*scale)
        prefix=target['club']+('方案：' if len(pairs)>1 else '')
        text=f"{prefix}Carry约{round(target['carry_yards']*scale)}{unit}，瞄{aim}，预计落区横向约{tee_width}{unit}。"
        text+=crossing_text(target,unit)
        assessed=next(row for row in chosen if row['target'] is target)
        labels={'bunker':'沙坑','water':'水障碍','ob':'已确认界外区'}
        nearby=list(dict.fromkeys(h['side']+labels[h['kind']] for h in assessed['space']['hazards']
                    if h['distance_m']<=(15 if h['kind'] in ('water','ob') else 10)*.9144))
        if nearby:text+='落点近旁需留意'+'、'.join(nearby)+'。'
        text+=f'按Carry落点估算，下一杆到果岭参考点直线约{round(left*scale/5)*5}{unit}；尚未计入滚动，不是旗杆距离。'
        if not profile.get('shot_dispersion') and assessed['risk'][0]:
            text+='目前没有这支杆的个人左右散布数据，不能把落区宽度当作安全保证；请按平常偏差核对罚杆区余量。'
        if target['club_key']==finder:
            text+='这是你设置的保底开球杆，仍需核对当天状态与障碍余量。'
        if target['club_key'] in estimates:
            text+='这支铁杆Carry按7铁每号相差10码暂估，执行前需按你的实际杆距确认。'
        if assessed['bunker_band']:
            text+='这支杆的Carry范围与近旁沙坑的前后距离重叠，偏向沙坑一侧的失误需留意。'
        elif safer is not None and target is safer['target']:
            text+='这是沙前保守候选，采用经验余量筛选，并非你的实测滚动或散布；仍需现场确认地面滚动，不能保证停在沙前。'
        text+=history_note(state,a['hole'],origin,target['aim_point'],target['club'])
        lines.append(text)
        options.append(dict(id=f"geometry:{target['club_key']}:{target['offset']}",club=target['club'],club_key=target['club_key'],hole=a['hole'],target=aim,carry_yards=target['carry_yards'],aim_point=target['aim_point'],position_version=a['position_version'],course_evidence=a['course_evidence'],strategy='mapped_carry_candidate',next_reference_yards=left,risk_factors=list(assessed['risk'])))
    from hole_history import selection_note
    explanation=selection_note(state,a['hole'],origin,targets,pairs[0])
    if explanation and explanation not in '\n'.join(lines):lines.append(explanation)
    return dict(comparison_context=context,framework=dict(version=1,preference=learned,dimensions=['penalty_risk','landing_room','carry_and_roll_clearance','next_approach','trusted_club','recent_history'],roll_clearance_yards=roll_clearance_yards,roll_clearance_basis='user_report' if roll_clearance_yards!=30 else 'screening_heuristic',dispersion='unknown_unless_reported',community_numbers_not_personal=True),text='\n'.join(lines),continuation_text='\n'.join(lines),options=options,tee_club_comparison=True)
