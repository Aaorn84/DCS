"""Bounded tee facts and conditional options; never equates carry with GPS displacement."""
from datetime import datetime
from shot_evidence import haversine
from gps_transition import inside,POLICY
from round_state import fact_value
SIDES={'left':'左侧','right':'右侧','center':'中间','center-left':'中左侧','center-right':'中右侧'}
def analyze(s,now):
    j=s.get('journey',{});pos=s['facts'].get('context.device_position',{})
    if not pos.get('valid'):return None
    gps=pos['value'];stamp=datetime.fromisoformat(gps['observed_at'].replace('Z','+00:00')).timestamp()
    if not -5<=now-stamp<=60 or gps['accuracy_m']>POLICY['max_accuracy_m']:return None
    eid=fact_value(s,'context.course_snapshot');e=s['evidence'].get(eid,{})
    if not e.get('active') or e.get('phase')!='final':return None
    course=e.get('data',{});hole=next((h for h in course.get('holes',[]) if h['number']==fact_value(s,'context.active_hole')),None)
    if not hole or not hole.get('tee_bbox') or not inside(hole['tee_bbox'],gps):return None
    matches=[h for h in course['holes'] if h.get('tee_bbox') and inside(h['tee_bbox'],gps)]
    if len(matches)!=1:
        if not (course.get('reference_simulation') is True and gps.get('simulation_hole')==hole['number'] and hole in matches):return None
    green=[o for o in hole['objects'] if o['kind']=='green_center']
    if len(green)!=1:return None
    yards=haversine(gps,green[0])/.9144
    profile=j.get('profile',{});clubs={}
    for key,label in [('driver','一号木'),('three_wood','3号木'),('long_iron','长铁杆'),('seven','7号铁')]:
        v=profile.get(key,{}).get('value',{})
        if key=='long_iron' and isinstance(v,dict) and v.get('club_name') in [str(n)+suffix for n in range(2,7) for suffix in ('铁','号铁')]:label=v['club_name']
        if isinstance(v,dict) and v.get('distance_type')=='carry' and v.get('units') in ('码','米') and type(v.get('distance')) in (int,float) and 0<v['distance']<=400:
            clubs[key]={'label':label,'carry_yards':v['distance']/(.9144 if v['units']=='米' else 1),'source':'user_report','not_calibrated':True}
    data=hole.get('tee_strategy',{});zones=data.get('landing_zones',[]) if data.get('verified') is True and data.get('source') else []
    zones=[z for z in zones if isinstance(z,dict) and isinstance(z.get('id'),str)
           and all(type(z.get(k)) in (int,float) and 0<z[k]<1000 for k in ('start_yards','end_yards','width_yards'))
           and z['start_yards']<z['end_yards'] and z.get('preferred_side') in SIDES
           and isinstance(z.get('hazards'),list) and all(isinstance(h,dict) and h.get('side') in SIDES and h.get('kind') in ('water','ob','bunker') and isinstance(h.get('label'),str) for h in z['hazards'])
           and type(z.get('required_carry_yards',0)) in (int,float)]
    candidates=[]
    for key,club in clubs.items():
        fitting=[z for z in zones if z['start_yards']<=club['carry_yards']<=z['end_yards']]
        if len(fitting)!=1:continue
        z=fitting[0]
        if z.get('required_carry_yards',0)>club['carry_yards']:continue
        candidates.append({'club_key':key,**club,'zone_id':z['id'],'zone':z,'remaining_straight_line_yards':max(0,yards-club['carry_yards']),
                           'remaining_is_conditional':True,'risk':'aggressive' if any(h['kind'] in ('water','ob') for h in z['hazards']) or (z['width_yards']<=40 and any(h['kind']=='bunker' for h in z['hazards'])) else 'unquantified'})
    return {**({'reference_simulation':True} if course.get('reference_simulation') else {}),'hole':hole['number'],'par':hole['par'],'distance_yards':yards,'distance_origin':'device_gps_in_tee_area','target':'green_center',
      'distance_kind':'horizontal_straight_line_not_card_length','position_version':pos['version'],'course_evidence':eid,
      'clubs':clubs,'candidates':candidates,'zones_verified':bool(zones),'roll':'unknown','weather_adjustment':'not_applied','map_source':data.get('source'),
      'usual_miss':profile.get('usual_miss',{}).get('value')}
def facts_text(a,unit='码'):
    distance=a['distance_yards']*(.9144 if unit=='米' else 1)
    text=f"第{a['hole']}洞，{a['par']}杆洞。从当前发球区位置到果岭中心直线约{round(distance/5)*5:g}{unit}，不是旗杆距离。"
    c=a['clubs'].get('driver')
    if c and a['par'] in (4,5):text+=f"你自报一号木Carry约{round(c['carry_yards']*(.9144 if unit=='米' else 1)):g}{unit}。"
    return text

def proposal(a,intent=None,unit='码',unavailable=(),selected=None):
    if a['par'] not in (4,5):return {'text':'三杆洞按攻果岭距离讨论，不套用开球模板。','options':[]}
    if selected:
        from club_selection import same_label
        club=a['clubs'].get(selected['key'])
        if not club or not same_label(club['label'],selected['label']):
            return {'text':'','options':[],'missing_club':selected['key'],'question':selected['label']+'平常的Carry大概多少'+unit+'？'}
    if not selected and 'driver' not in a['clubs'] and 'driver' not in unavailable:
        return {'text':'','options':[],'missing_club':'driver','question':'一号木平常的Carry大概多少'+unit+'？'}
    options=a['candidates'];driver=next((x for x in options if x['club_key']=='driver'),None)
    scale=.9144 if unit=='米' else 1
    def details(x):
        z=x['zone'];t=f"{x['label']}Carry约{round(x['carry_yards']*scale):g}{unit}，对应落区宽约{round(z['width_yards']*scale):g}{unit}"
        if z['hazards']:t+='，'+ '、'.join(SIDES.get(h['side'],'附近')+h['label'] for h in z['hazards'])
        return t+'。'
    if selected:
        choice=next((x for x in options if x['club_key']==selected['key']),None)
        if not choice:return {'text':'记下你想用'+selected['label']+'；地图还缺这支杆预计落点附近的资料，暂不能确认这条路线。','options':[]}
        side=SIDES[choice['zone']['preferred_side']]
        text=details(choice)
        text+=('这条路线较进取，旁边障碍的风险仍在。' if choice['risk']=='aggressive' else '仍需为落点偏差留余量。')
        text+='如果用'+choice['label']+'，目标取这段'+side+'。'
        option={'id':choice['club_key']+':'+choice['zone_id'],'club':choice['label'],'hole':a['hole'],'target':side,'carry_yards':choice['carry_yards'],'position_version':a['position_version'],'course_evidence':a['course_evidence'],'strategy':'player_selected','intent_source':'user_report' if intent else 'unset','selection_source':'user_report'}
        return {'text':text,'continuation_text':text,'options':[option]}
    text=details(driver) if driver else '地图还缺一号木预计落点附近的资料。'
    if driver and driver['risk']=='aggressive':text+='这是一条较进取的开球路线，不能称为稳妥方案；瞄向中左侧也不能消除旁边障碍的风险。'
    if intent:text+='按你明确提出的“'+intent[:40]+'”比较方案。'
    else:text+=''
    # Relative comparison, not a claim that a shorter club is intrinsically safer.
    alternatives=[x for x in options if x['club_key']!='driver' and not x['zone']['hazards'] and
                  (not driver or x['zone']['width_yards']>driver['zone']['width_yards'] or (a.get('reference_simulation') and driver['zone']['hazards']))]
    conservative=intent is None or '稳' in intent or '保守' in intent
    if conservative:
        for key,label in [('three_wood','3号木'),('long_iron','最有把握的一支长铁杆')]:
            if key=='long_iron' and any(x['club_key']=='three_wood' for x in alternatives):continue
            if key not in a['clubs'] and key not in unavailable:
                text+='要比较更稳妥的落区，还缺少'+label+'的数据；短一支杆并不自动更安全。'
                continuation=''
                if key=='long_iron':
                    three=next((x for x in options if x['club_key']=='three_wood'),None)
                    continuation=(details(three)+'仍未找到比一号木更宽且避开已知邻接障碍的落区。' if three else '目前还不能用3号木确认更稳妥的落区。')
                return {'text':text,'continuation_text':continuation,'options':[],'missing_club':key,'question':label+'平常的Carry大概多少'+unit+'？'}
        if alternatives:
            # Prefer a longer familiar club among the less exposed mapped zones; no probability claims.
            choice=max(alternatives,key=lambda x:x['carry_yards'])
            if driver and choice['zone']['width_yards']<=driver['zone']['width_yards']:
                text+=details(choice)+'可避开这一段已知邻接障碍，但落区更窄，下一杆也更长，要兼顾方向控制。'
            else:text+=details(choice)+'这段落区比一号木落区更宽，现有图层未标出邻接障碍，可作为相对保守的候选；代价是下一杆通常更长。'
        else:
            text+='现有球杆与地图还找不到更宽且避开已知邻接障碍的替代落区，不把同一条风险路线重新命名为安全方案。'
            return {'text':text+'还需核实具体球杆、落区或现场条件。','options':[]}
    else:
        if not driver:return {'text':text+'目前不能给出可靠的一号木进攻方案。','options':[]}
        choice=driver
        text+='若接受这条路线的失误代价，可以把一号木作为进攻候选。'
    if a.get('usual_miss')=='偏右' and any(h['side']=='right' for h in choice['zone']['hazards']):text+='你常见偏右，右侧障碍尤其需要留余量。'
    side=SIDES[choice['zone']['preferred_side']]
    text+=f"候选：{choice['label']}，目标取该落区{side}。"
    text+=('五杆洞先分段安排，不默认两杆上果岭。' if a['par']==5 else '下一杆按实际落点再选杆。')
    text+='风、滚动和个人散布未计入，落区宽度不能替代命中概率；未标障碍也不证明无障碍。'
    tradeoff='用更宽的落区换取容错，代价是下一杆更长。'
    if conservative and driver and choice['zone']['width_yards']<=driver['zone']['width_yards']:tradeoff='避开这一段已知邻接障碍，但落区更窄、下一杆更长，仍要控制方向。'
    brief=details(choice)+f"我建议把{choice['label']}打向这段{side}，"+('接受这条进攻路线的障碍风险。' if not conservative else tradeoff)+'风、滚动和个人散布尚未计入，仍要留余量。'
    return {'text':text,'continuation_text':brief,'options':[{'id':choice['club_key']+':'+choice['zone_id'],'club':choice['label'],'hole':a['hole'],'target':side,'carry_yards':choice['carry_yards'],'position_version':a['position_version'],'course_evidence':a['course_evidence'],'strategy':'relative_conservative' if conservative else 'aggressive','intent_source':'user_report' if intent else 'unset'}]}

def arrival(j,a,timestamp):
    """Additional dwell gate for initial tee arrivals; round_session gates hole changes."""
    tr=j.setdefault('tee_tracking',{})
    key=str(a['hole'])
    if timestamp<=tr.get('last_timestamp',float('-inf')):return False
    old_time=tr.get('last_timestamp');tr['last_timestamp']=timestamp
    if tr.get('hole')!=key or old_time is None or timestamp-old_time>POLICY['max_gap_seconds']:
        tr.update(hole=key,since=timestamp,fixes=0)
    tr['fixes']+=1
    return tr['fixes']>=POLICY['min_fixes'] and timestamp-tr['since']>=POLICY['dwell_seconds']
