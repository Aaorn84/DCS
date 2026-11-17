"""Bounded tee facts and conditional options; never equates carry with GPS displacement."""
from datetime import datetime
import math
from shot_evidence import haversine
from gps_transition import inside,POLICY
from round_state import fact_value
SIDES={'left':'左侧','right':'右侧','center':'中间','center-left':'中左侧','center-right':'中右侧'}
PAR_FIVE_BAG=(('three_wood','3号木'),('five_wood','5号木'),('hybrid','铁木杆'),
              ('iron3','3号铁'),('iron4','4号铁'))

def reported_carry_clubs(profile):
    clubs={}
    for key,label in [('driver','一号木'),('three_wood','3号木'),('hybrid','铁木杆'),('long_iron','长铁杆'),('seven','7号铁'),
                      ('five_wood','5号木'),('iron3','3号铁'),('iron4','4号铁')]:
        v=profile.get(key,{}).get('value',{})
        if key=='hybrid' and isinstance(v,dict) and v.get('club_name'):
            label=v['club_name']
        if key=='long_iron' and isinstance(v,dict) and v.get('club_name') in [str(n)+suffix for n in range(2,7) for suffix in ('铁','号铁')]:label=v['club_name']
        if isinstance(v,dict) and v.get('distance_type')=='carry' and v.get('units') in ('码','米') and type(v.get('distance')) in (int,float) and 0<v['distance']<=400:
            clubs[key]={'label':label,'carry_yards':v['distance']/(.9144 if v['units']=='米' else 1),'source':'user_report','not_calibrated':True}
    return clubs


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
    profile=j.get('profile',{});clubs=reported_carry_clubs(profile)
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
            if driver and not driver['zone']['hazards']:
                side=SIDES[driver['zone']['preferred_side']]
                short=f"可考虑一号木，目标取这段{side}。落区约{round(driver['zone']['width_yards']*scale):g}{unit}宽，优先控制方向，别追求额外距离。"
                if a.get('usual_miss')=='偏右':short+='尤其留意右侧失误。'
                elif a.get('usual_miss')=='偏左':short+='尤其留意左侧失误。'
                option={'id':driver['club_key']+':'+driver['zone_id'],'club':driver['label'],'hole':a['hole'],'target':side,'carry_yards':driver['carry_yards'],'position_version':a['position_version'],'course_evidence':a['course_evidence'],'strategy':'available_candidate','intent_source':'user_report' if intent else 'unset'}
                return {'text':short,'continuation_text':short,'options':[option]}
            return {'text':'目前没有可确认的保守落区，先别强攻；需要现场确认一处可过渡的目标。','options':[]}
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


def suggest(state, analysis, intent=None, unit='码', unavailable=(), selected=None, *, mapped_fallback=False, par_five_plan=False, carry_crossing=False, compare_par_five=False, ask_fairway_carry=False, allow_roll_in=False, compare_safety=False):
    offer = proposal(analysis, intent, unit, unavailable, selected)
    plan_three = par_five_plan and analysis['par'] == 5
    if not mapped_fallback or (offer['options'] and not plan_three) or analysis['par'] not in (4, 5):
        return offer
    if selected:
        from club_selection import same_label
        club = analysis['clubs'].get(selected['key'])
        if not club or not same_label(club['label'], selected['label']):
            return offer
        clubs = [(selected['key'], club)]
    else:
        clubs = list(analysis['clubs'].items())
    from tee_geometry import tee_targets
    targets = tee_targets(state, analysis, clubs, allow_crossing=plan_three or carry_crossing)
    if not targets:
        return offer
    aggressive = bool(intent and any(word in intent for word in ('进攻', '进取', '积极')))
    choice = max(targets, key=lambda row: (row['carry_yards'], row['width_m']) if aggressive
                 else (row['width_m'], row['carry_yards']))
    if plan_three:
        routes = par_five_routes(state, analysis, targets)
        if routes:
            choice = min(routes, key=lambda row: (row['leave_error'], row['crossings'],
                                                  -min(row['width_m'], row['layup']['width_m']),
                                                  -row['carry_yards']))
    target = aiming_text(choice, unit)
    scale = .9144 if unit == '米' else 1
    carry = choice['carry_yards']
    low = round(choice['low_yards']*scale)
    high = round(choice['high_yards']*scale)
    label = choice['club']
    text = f"按地图估算，可用{label}瞄{target}，候选落区约{low}–{high}{unit}。"
    text += crossing_text(choice, unit)
    if choice.get('layup'):
        layup = choice['layup']
        second = aiming_text(layup, unit)
        text += (f"从这个落点，第二杆可瞄{second}，目标Carry约{round(layup['carry_yards']*scale/5)*5}{unit}，"
                 f"第三杆到果岭参考点约{round(choice['leave_yards']*scale/5)*5}{unit}。")
        text += crossing_text(layup, unit)
        text += '开球落定后，按实际球位和滚动空间重新选第二杆。'
    elif plan_three:
        text += '第二杆等开球落定后，再核对过渡落区和第三杆留距。'
    elif choice['crossing_m'] is None:
        text += '这条瞄准线给地图已标的障碍留有余量，现场再看风和滚动空间。'
    option = dict(id=f"geometry:{choice['club_key']}:{choice['offset']}", club=label,
                  hole=analysis['hole'], target=target, carry_yards=carry,
                  aim_point=choice['aim_point'], position_version=analysis['position_version'],
                  course_evidence=analysis['course_evidence'], strategy='mapped_carry_candidate',
                  intent_source='user_report' if intent else 'unset')
    if choice.get('layup'):
        option['layup'] = dict(aim_point=layup['aim_point'], carry_yards=layup['carry_yards'],
                               leave_yards=choice['leave_yards'])
    if plan_three and compare_par_five:
        return compare_par_routes(state, analysis, targets, text, option, unit,
                                  ask_fairway_carry=ask_fairway_carry and 'par_five_fairway' not in unavailable,
                                  allow_roll_in=allow_roll_in,compare_safety=compare_safety)
    return {'text': text, 'continuation_text': text, 'options': [option]}


def compare_par_routes(state, analysis, targets, layup_text, layup_option, unit, *, ask_fairway_carry=False, allow_roll_in=False, compare_safety=False):
    from tee_geometry import MAX_ROLL_IN_YARDS,ROLL_IN_CLUBS,tee_targets
    course=state['evidence'][analysis['course_evidence']]['data']
    hole=next(h for h in course['holes'] if h['number']==analysis['hole'])
    card=hole.get('published_yardage')
    scale=.9144 if unit=='米' else 1

    def distance(yards):
        return f'{round(yards*scale)}{unit}'

    # Driver carry is reported from the tee. Do not reuse it as a fairway carry.
    clubs=[(key,club) for key,club in analysis['clubs'].items() if key!='driver']
    budget=(max(tee['carry_yards'] for tee in targets)+max(c['carry_yards'] for _,c in clubs)) if clubs else None
    roll_budget=None
    if allow_roll_in:
        roll_budget=max((tee['carry_yards']+club['carry_yards']+MAX_ROLL_IN_YARDS
                         for tee in targets for key,club in clubs if key in ROLL_IN_CLUBS),default=None)
    attack=None
    if budget is None:
        reason='还缺可用于第二杆的球道杆距。'
    elif card and max(budget,roll_budget or 0)<card:
        reason=f'候选开球杆与球道最长杆的已知Carry合计最多{distance(budget)}，低于球洞公布长度{distance(card)}。按现有杆距先走三上。'
    else:
        for tee in targets:
            green_targets=tee_targets(state,analysis,clubs,origin=tee['aim_point'],
                                      allow_crossing=True,surface='green')
            if allow_roll_in:
                eligible=[(key,club) for key,club in clubs
                          if not card or tee['carry_yards']+club['carry_yards']+MAX_ROLL_IN_YARDS>=card]
                green_targets+=tee_targets(state,analysis,eligible,origin=tee['aim_point'],
                                           allow_crossing=True,surface='green',roll_in=True)
            for green in green_targets:
                allowance=MAX_ROLL_IN_YARDS if green['club_key'] in ROLL_IN_CLUBS else 0
                if allow_roll_in and card and tee['carry_yards']+green['carry_yards']+allowance<card:
                    continue
                rank=(() if not allow_roll_in else (not green.get('roll_yards'),))+(sum(shot['crossing_m'] is None for shot in (tee,green)),
                      min(tee['width_m'],green['width_m']),green['width_m'])
                if attack is None or rank>attack[0]:
                    attack=(rank,tee,green)
        reason='从候选开球落点出发，已知球道杆距还没有匹配到兼顾过障碍和停球空间的果岭落区。'
    if attack is None:
        if ask_fairway_carry and not any(key in ('three_wood','five_wood','hybrid','iron3','iron4','long_iron') for key,_ in clubs):
            question='你在球道上能稳定用的最长一支杆是什么，Carry大概多少？例如「3号木235码」或「4号铁木杆200码」。不知道可以跳过。'
            if budget is not None:
                tee=max(targets,key=lambda shot:shot['carry_yards'])
                _,fairway=max(clubs,key=lambda entry:entry[1]['carry_yards'])
                question=(f"目前只有{tee['club']}和{fairway['label']}可用于这组估算，Carry合计{distance(budget)}。"
                          +question)
            return {'text':layup_text,'continuation_text':layup_text,'options':[layup_option],
                    'missing_club':'par_five_fairway','question':question}
        text=layup_text+'两上评估：'+reason
        return {'text':text,'continuation_text':text,'options':[layup_option]}

    _,tee,green=attack
    target=aiming_text(tee,unit)
    offset=green['offset']
    aim=f"从预计落点朝果岭参考方向{'右' if offset>0 else '左'}偏约{abs(offset)}度" if offset else '从预计落点瞄果岭参考点'
    text=(f"两上方案：{tee['club']}开球，瞄{target}，预计Carry约{distance(tee['carry_yards'])}。"
          +crossing_text(tee,unit)
          +f"第二杆可考虑{green['club']}，{aim}，目标Carry约{distance(green['carry_yards'])}。"
          +roll_in_text(green,unit)
          +crossing_text(green,unit)
          +'开球落定后，再按球位和滚动空间确认是否攻果岭。')
    if compare_safety:
        space=green_landing_space(state,analysis,tee['aim_point'],green)
        text+=space_text(space,'果岭入口' if green.get('roll_yards') else '果岭落区',unit)
        if layup_option.get('layup') and (space['width_m']<12*.9144 or space['depth_m']<12*.9144
                or any(h['kind'] in ('water','ob') and h['distance_m']<=15*.9144 for h in space['hazards'])):
            text+='如果更重视落点容错，优先看三上。'
    attack_option=dict(layup_option,id=f"geometry:{tee['club_key']}:{tee['offset']}:two",
                       club=tee['club'],target=target,carry_yards=tee['carry_yards'],
                       aim_point=tee['aim_point'],par_plan='two',
                       approach=dict(club=green['club'],carry_yards=green['carry_yards'],aim_point=green['aim_point'],
                                     **({'roll_yards':green['roll_yards']} if green.get('roll_yards') else {})))
    attack_option.pop('layup',None)
    if not layup_option.get('layup'):
        return {'text':text,'continuation_text':text,'options':[attack_option]}
    layup_option=dict(layup_option,par_plan='three')
    text+='\n三上方案：'+layup_text
    return {'text':text,'continuation_text':text,'options':[attack_option,layup_option]}


def actual_position_roll_in(state, now, unit, *, compare_safety=False, direct=False):
    from lie_position import fresh_position
    from tee_geometry import tee_targets
    origin=fresh_position(state,now)
    if not origin:
        return None
    analysis=dict(course_evidence=fact_value(state,'context.course_snapshot'),
                  hole=fact_value(state,'context.active_hole'))
    profile=state['journey'].get('profile',{})
    clubs=reported_carry_clubs(profile)
    from iron_estimates import iron_table
    from club_selection import same_label
    for number,estimate in iron_table(profile).items():
        label=f'{number}号铁'
        if not any(same_label(label,club['label']) for club in clubs.values()):
            clubs[f'estimated_iron_{number}']={
                'label':label,'carry_yards':estimate['carry_yards'],
                'source':estimate['source']}
    candidates=tee_targets(state,analysis,list(clubs.items()),origin=origin['value'],
                           allow_crossing=True,surface='green',roll_in=not direct)
    if direct:
        candidates=[candidate for candidate in candidates if candidate['club_key']!='driver']
    if not candidates:
        return None
    target=min(candidates,key=lambda row:(row['crossing_m'] is not None,row.get('roll_yards',0),-row['width_m']))
    scale=.9144 if unit=='米' else 1
    offset=target['offset']
    aim=f"朝果岭参考方向{'右' if offset>0 else '左'}偏约{abs(offset)}度" if offset else '朝果岭参考点'
    text=(f"另一条线可考虑{target['club']}，{aim}，Carry约{round(target['carry_yards']*scale)}{unit}。"
          +roll_in_text(target,unit)+crossing_text(target,unit))
    if str(target['club_key']).startswith('estimated_iron_'):
        text+='这支铁杆的Carry按7号铁杆距暂估，现场按你的实际杆距确认。'
    if not compare_safety:
        return {'text':text}
    space=green_landing_space(state,analysis,origin['value'],target)
    text+=space_text(space,'果岭入口' if target.get('roll_yards') else '果岭落区',unit)
    return {'text':text,'tight_green':space['width_m']<12*.9144 or space['depth_m']<12*.9144,
            'near_penalty':any(h['kind'] in ('water','ob') and h['distance_m']<=15*.9144
                               for h in space['hazards'])}


def roll_in_text(target,unit):
    if not target.get('roll_yards'):
        return ''
    roll=math.ceil(target['roll_yards']*(.9144 if unit=='米' else 1))
    return f'这条路线要靠球落地后再滚约{roll}{unit}上果岭，现场确认前沿通畅、地面能滚再用。'


def aiming_text(choice, unit):
    reference = choice['reference']
    scale = .9144 if unit == '米' else 1
    if reference:
        distance = round(reference['distance_m']/.9144*scale/5)*5
        target = (f"{reference['rank']}{reference['bunker_side']}侧约{distance}{unit}的沙坑"
                  f"{reference['aim_side']}边的球道")
    else:
        offset = choice['offset']
        direction = f"向{'右' if offset > 0 else '左'}约{abs(offset)}度"
        target = f"果岭参考方向{direction}的球道" if offset else '朝果岭参考点方向的球道'
    return target


def crossing_text(choice, unit):
    if choice['crossing_m'] is None:
        return ''
    scale = 1 if unit == '米' else .9144
    far = math.ceil(choice['crossing_m']/scale/5)*5
    return f"沿这条线要飞越地图上的障碍，远沿约{far}{unit}，现场确认有飞越余量再打。"


def par_five_routes(state, analysis, targets):
    from tee_geometry import tee_targets
    journey = state['journey']
    course = state['evidence'][analysis['course_evidence']]['data']
    hole = next(h for h in course['holes'] if h['number'] == analysis['hole'])
    green = next(o for o in hole['objects'] if o['kind'] == 'green_center')
    preference = journey['profile'].get('shot_style_preferences', {}).get('leave_distance')
    if not preference:
        from wedge_leave import suggested_leave
        preference = suggested_leave(journey)
    preferred = preference['value']/(.9144 if preference['unit'] == '米' else 1) if preference else 90
    max_layup = max((club['carry_yards'] for key, club in analysis['clubs'].items()
                     if key != 'driver'), default=220)
    routes = []
    for tee in targets:
        landing = tee['aim_point']
        remaining = haversine(landing, green)/.9144
        nominal_layup = remaining-preferred
        distances = [d for d in range(35, 221, 10) if d<=max_layup and abs(d-nominal_layup)<=35 and d<remaining-25]
        if not distances:
            continue
        layups = tee_targets(state, analysis, [(str(d), {'label':'', 'carry_yards':d}) for d in distances],
                             origin=landing, allow_crossing=True)
        for layup in layups:
            leave = haversine(layup['aim_point'], green)/.9144
            if 25 <= leave < remaining-15:
                routes.append(dict(tee, layup=layup, leave_yards=leave,
                                   leave_error=max(0,abs(leave-preferred)-5),
                                   crossings=sum(shot['crossing_m'] is not None for shot in (tee,layup))))
    return routes


def actual_position_layup(state, now, *, compare_safety=False):
    from lie_position import fresh_position
    from round_state import fact_value
    origin=fresh_position(state,now)
    eid=fact_value(state,'context.course_snapshot')
    number=fact_value(state,'context.active_hole')
    course=state.get('evidence',{}).get(eid,{}).get('data',{})
    hole=next((h for h in course.get('holes',[]) if h['number']==number),None)
    if not origin or not hole or hole['par']!=5:
        return ''
    profile=state['journey'].get('profile',{})
    clubs={key:club for key,club in reported_carry_clubs(profile).items() if key!='driver'}
    if not clubs:
        return ''
    analysis=dict(course_evidence=eid,hole=number,clubs=clubs)
    routes=par_five_routes(state,analysis,[dict(aim_point=origin['value'],crossing_m=None)])
    if not routes:
        return ''
    if compare_safety:
        from tee_geometry import landing_space
        for row in routes:
            row['space']=landing_space(hole,course.get('reference_simulation') is True,origin['value'],
                                       row['layup']['aim_point'],'fairway')
        route=min(routes,key=lambda row:(row['crossings'],
                   sum(h['kind'] in ('water','ob') for h in row['space']['hazards']),
                   -row['space']['width_m'],row['leave_error']))
    else:
        route=min(routes,key=lambda row:(row['leave_error'],row['crossings'],-row['layup']['width_m']))
    unit=profile.get('units',{}).get('value','码')
    scale=.9144 if unit=='米' else 1
    layup=route['layup']
    return (f"从现在的球位，可瞄{aiming_text(layup,unit)}，第二杆目标Carry约"
            f"{round(layup['carry_yards']*scale/5)*5}{unit}，预计第三杆到果岭参考点约"
            f"{round(route['leave_yards']*scale/5)*5}{unit}。"+crossing_text(layup,unit)
            +(space_text(route['space'],'球道落区',unit) if compare_safety else '')
            +"按现场球位和滚动空间选杆。")


def green_landing_space(state,analysis,origin,target):
    from tee_geometry import landing_space
    course=state['evidence'][analysis['course_evidence']]['data']
    hole=next(h for h in course['holes'] if h['number']==analysis['hole'])
    return landing_space(hole,course.get('reference_simulation') is True,origin,
                         target['aim_point'],'green',target.get('roll_yards',0))


def space_text(space, label, unit):
    scale=1 if unit=='米' else .9144
    width=round(space['width_m']/scale)
    depth=round(space['depth_m']/scale)
    text=f'{label}沿这条线横向约{width}{unit}' if width else ''
    if text and label.startswith('果岭') and depth:
        text+=f'、纵深约{depth}{unit}'
    if text:
        text+='。'
    labels={'water':'水障碍','bunker':'沙坑','ob':'已确认界外区'}
    hazards=list(dict.fromkeys(h['side']+labels[h['kind']] for h in space['hazards']))
    if hazards:
        text+='落点附近有'+'、'.join(hazards)+'。'
    return text


def same_target(previous, updated):
    if not updated or any(previous.get(key) != updated.get(key)
                          for key in ('id', 'club', 'target', 'course_evidence', 'hole')):
        return False
    for field in ('layup','approach'):
        before,after=previous.get(field),updated.get(field)
        if (before or after) and (not before or not after or before.get('club')!=after.get('club')
                or before['carry_yards']!=after['carry_yards'] or before.get('roll_yards')!=after.get('roll_yards')
                or haversine(before['aim_point'],after['aim_point'])>3):
            return False
    if 'aim_point' in previous or 'aim_point' in updated:
        return ('aim_point' in previous and 'aim_point' in updated
                and previous['carry_yards'] == updated['carry_yards']
                and haversine(previous['aim_point'], updated['aim_point']) <= 3)
    return True
