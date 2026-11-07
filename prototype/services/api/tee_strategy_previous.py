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
    if len(matches)!=1:return None
    green=[o for o in hole['objects'] if o['kind']=='green_center']
    if len(green)!=1:return None
    yards=haversine(gps,green[0])/.9144
    profile=j.get('profile',{});clubs={}
    for key,label in [('driver','一号木'),('seven','7号铁')]:
        v=profile.get(key,{}).get('value',{})
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
                           'remaining_is_conditional':True,'risk':'high' if any(h['kind'] in ('water','ob') for h in z['hazards']) else 'unquantified'})
    return {'hole':hole['number'],'par':hole['par'],'distance_yards':yards,'distance_origin':'device_gps_in_tee_area','target':'green_center',
      'distance_kind':'horizontal_straight_line_not_card_length','position_version':pos['version'],'course_evidence':eid,
      'clubs':clubs,'candidates':candidates,'zones_verified':bool(zones),'roll':'unknown','weather_adjustment':'not_applied','map_source':data.get('source'),
      'usual_miss':profile.get('usual_miss',{}).get('value')}
def facts_text(a,unit='码'):
    distance=a['distance_yards']*(.9144 if unit=='米' else 1)
    text=f"第{a['hole']}洞，{a['par']}杆洞。从当前发球区位置到果岭中心直线约{round(distance/5)*5:g}{unit}，不是旗杆距离。"
    c=a['clubs'].get('driver')
    if c and a['par'] in (4,5):text+=f"你自报一号木Carry约{round(c['carry_yards']*(.9144 if unit=='米' else 1)):g}{unit}。"
    return text

def proposal(a,intent,unit='码'):
    if a['par'] not in (4,5):return {'text':'三杆洞另按攻果岭距离和球位讨论，不套用四、五杆洞开球模板。','options':[]}
    options=a['candidates']
    if not options:
        return {'text':'还没有可匹配的一号木Carry或经核实的落区资料，暂不硬选杆。','options':[]}
    driver=next((x for x in options if x['club_key']=='driver'),None)
    safer=next((x for x in options if x['club_key']!='driver' and x['risk']!='high'),None)
    choice=safer if driver and driver['risk']=='high' and safer and ('稳' in intent or a.get('usual_miss') in ('偏右','偏左')) else driver or safer or options[0]
    z=choice['zone'];side=SIDES.get(z['preferred_side'],'已核实的目标区域')
    scale=.9144 if unit=='米' else 1
    factors=f"这支{choice['label']}的自报Carry约{round(choice['carry_yards']*scale):g}{unit}，对应落区宽约{round(z['width_yards']*scale):g}{unit}"
    if z['hazards']:factors+='，'+ '、'.join(SIDES.get(h['side'],'附近')+h['label'] for h in z['hazards'])
    text=factors+'。'
    if a.get('usual_miss')=='偏右' and any(h['side']=='right' for h in z['hazards']):text+='你常见偏右，这里的右侧风险要留意；不能只靠瞄左抵消失误。'
    text+=f"结合你想“{intent[:40]}”，可以讨论用{choice['label']}打向这段{side}落区。"
    if a['par']==4:text+='下一杆按实际落点再选杆，不把Carry后的剩余量当成已经打出的结果。'
    else:text+='这洞先分段推进，不默认两杆上果岭；第二杆再结合实际球位安排。'
    text+='滚动、风况和个人散布尚未计入，落区宽度不代表命中保证，这只是候选方案。'
    return {'text':text,'options':[{'id':choice['club_key']+':'+choice['zone_id'],'club':choice['label'],'target':side,'carry_yards':choice['carry_yards'],'position_version':a['position_version'],'course_evidence':a['course_evidence']}]}

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
