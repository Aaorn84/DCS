"""Current-position hazard identity and line/polygon far-edge intersections.
Tee-radial vertices are not a valid general crossing distance.
"""
from tee_geometry import planning_geometry_cache
import math,re
from round_state import fact_value
from lie_position import fresh_position,polygon_contains
from shot_evidence import haversine

@planning_geometry_cache
def answer(s,request,now):
 label='沙坑' if request['kind']=='bunker' else '水体'
 pos=fresh_position(s,now)
 if not pos:return '请先更新当前位置，我再计算这条线路的过'+('沙' if request['kind']=='bunker' else '水')+'距离。'
 eid=fact_value(s,'context.course_snapshot');e=s.get('evidence',{}).get(eid,{})
 course=e.get('data',{}) if e.get('active') and e.get('phase')=='final' else {}
 hole=next((h for h in course.get('holes',[]) if h['number']==fact_value(s,'context.active_hole')),None)
 if not hole:return '当前球洞地图不完整，暂时无法计算过'+label+'的距离。'
 greens=[v for v in hole.get('objects',[]) if v.get('kind')=='green_center']
 if len(greens)!=1:return '缺少明确目标方向，暂时无法计算当前线路的障碍远沿。'
 p=pos['value'];g=greens[0];cos=math.cos(math.radians(p['latitude']));dx=(g['longitude']-p['longitude'])*111000*cos;dy=(g['latitude']-p['latitude'])*111000;length=math.hypot(dx,dy)
 if length<5:return '当前位置太接近果岭参考点，无法稳定确定过障碍的方向。'
 fx,fy=dx/length,dy/length
 def xy(point):
  x=(point[0]-p['longitude'])*111000*cos;y=(point[1]-p['latitude'])*111000
  return x*fy-y*fx,x*fx+y*fy
 polygons={}
 for z in hole.get('surface_zones',[]):
  geometry=z.get('geometry',{})
  if z.get('surface')==request['kind'] and z.get('verified') is True and z.get('source') and geometry.get('type')=='Polygon':polygons[z['id']]=geometry.get('coordinates',[])
 if course.get('reference_simulation') is True:
  kind='BunkerTrace' if request['kind']=='bunker' else 'WaterTrace'
  for path in hole.get('display_paths',[]):
   if path.get('kind')!=kind or len(path.get('points',[]))<3:continue
   ring=[[v['longitude'],v['latitude']] for v in path['points']]
   if ring[0]!=ring[-1]:ring.append(ring[0])
   polygons[path['id']]=[ring]
 if not polygons:return '缺少'+label+'轮廓，暂时不能按当前线路计算过障碍的距离。'
 candidates=[]
 for identity,rings in polygons.items():
  crossings=[];xs=[]
  if not rings:continue
  for ring in rings:
   points=[xy(v) for v in ring];xs.extend(x for x,y in points)
   for (x,y),(u,v) in zip(points,points[1:]):
    if abs(u-x)<1e-8:continue
    t=-x/(u-x)
    if 0<=t<=1:crossings.append(y+t*(v-y))
  if not xs:continue
  lateral=(min(xs)+max(xs))/2
  if request.get('side')=='right' and lateral<=0:continue
  if request.get('side')=='left' and lateral>=0:continue
  distances=sorted(set(round(v,4) for v in crossings if v>=0))
  # Midpoint inclusion handles multiple lobes and interior holes on this particular ray.
  intervals=[];breaks=[0]+distances
  for a,b in zip(breaks,breaks[1:]):
   if b-a<1e-4:continue
   t=(a+b)/2;point=dict(latitude=p['latitude']+fy*t/111000,longitude=p['longitude']+fx*t/(111000*cos),accuracy_m=0)
   if polygon_contains(rings,point):intervals.append((a,b))
  if not intervals:continue
  near=min(a for a,b in intervals);far=max(b for a,b in intervals)
  if near>length+pos['value']['accuracy_m']:continue
  candidates.append(dict(id=identity,near_m=near,far_m=far))
 if not candidates:
  return '按当前位置朝果岭参考点的直线，没有找到需要飞越的'+label+'轮廓交点；刚才的风险可能来自路线旁的障碍，不能拿其他'+label+'的远沿代替。'
 # Recompute the same corridor used by short-game advice; never reuse a stale tee obstacle.
 from short_game_route import assess
 route=assess(s,now)
 discussed={v['id'] for v in route.get('obstacles',[]) if v['kind']==request['kind']}
 if discussed:
  relevant=[v for v in candidates if v['id'] in discussed]
  if not relevant:return '刚才提示的'+label+'在路线误差带旁，中心线路没有可靠的远沿交点；需要换一个明确飞越方向后再算。'
  candidates=relevant
 candidates.sort(key=lambda v:v['near_m'])
 if len(candidates)>1 and not request.get('rank'):return '这条线路上有多个'+label+'，你问近处还是远处？'
 chosen=candidates[-1] if request.get('rank')=='far' else candidates[0]
 unit=request.get('unit') or s.get('journey',{}).get('profile',{}).get('units',{}).get('value','码');scale=1 if unit=='米' else .9144
 # Use an upper 5-unit band so rounding never understates a crossing requirement.
 distance=math.ceil(chosen['far_m']/scale/5)*5
 s['journey']['last_hazard_route']={'hazard_id':chosen['id'],'kind':request['kind'],'course_evidence':eid,'hole':hole['number'],'position_version':pos['version'],'target':'green_reference','method':'current_position_ray_polygon_exit','near_m':chosen['near_m'],'far_m':chosen['far_m'],'simulation_only':course.get('reference_simulation') is True}
 text=f'沿当前位置到果岭参考点的直线，到这个{label}远沿约{distance:g}{unit}；飞越还要留余量。'
 if chosen['far_m']>length+pos['value']['accuracy_m']:text+='这个障碍沿线延伸到果岭参考点之后，不能把参考点距离当成过障碍距离。'
 return text


def landing_line(state, now, target=None, *, corridor=False, include_ob=False, stop_at_target=False, stop_distance_m=None):
 """Intersect green and mapped hazards along one explicit aiming ray."""
 pos=fresh_position(state,now)
 eid=fact_value(state,'context.course_snapshot')
 evidence=state.get('evidence',{}).get(eid,{})
 if not pos or not evidence.get('active') or evidence.get('phase')!='final':return None
 course=evidence['data']
 hole=next((h for h in course.get('holes',[]) if h['number']==fact_value(state,'context.active_hole')),None)
 if not hole:return None
 centers=[v for v in hole.get('objects',[]) if v['kind']=='green_center']
 if len(centers)!=1:return None
 target=target or centers[0]
 start=pos['value']
 scale=111000*math.cos(math.radians(start['latitude']))
 def xy(lon,lat):
  return (lon-start['longitude'])*scale,(lat-start['latitude'])*111000
 dx,dy=xy(target['longitude'],target['latitude'])
 length=math.hypot(dx,dy)
 if length<5:return None
 fx,fy=dx/length,dy/length
 polygons={kind:[] for kind in ('green','bunker','water')}
 if include_ob:polygons['ob']=[]
 for zone in hole.get('surface_zones',[]):
  shape=zone.get('geometry',{})
  if zone.get('surface') in polygons and zone.get('verified') is True and zone.get('source') and shape.get('type')=='Polygon':
   polygons[zone['surface']].append(shape['coordinates'])
 if course.get('reference_simulation') is True:
  kinds={'GreenTrace':'green','BunkerTrace':'bunker','WaterTrace':'water'}
  for path in hole.get('display_paths',[]):
   kind=kinds.get(path['kind'])
   if not kind or len(path['points'])<3:continue
   ring=[[point['longitude'],point['latitude']] for point in path['points']]
   polygons[kind].append([ring if ring[0]==ring[-1] else ring+[ring[0]]])
 def intervals(rings):
  crossings={0.0}
  for ring in rings:
   pts=[xy(*v) for v in ring]
   projected=[(x*fy-y*fx,x*fx+y*fy) for x,y in pts]
   for (x,a),(u,b) in zip(projected,projected[1:]):
    if abs(u-x)<1e-8:continue
    fraction=-x/(u-x)
    distance=a+fraction*(b-a)
    if 0<=fraction<=1 and distance>0:crossings.add(distance)
  cuts=sorted(crossings)
  for a,b in zip(cuts,cuts[1:]):
   mid=(a+b)/2
   point={'longitude':start['longitude']+fx*mid/scale,
          'latitude':start['latitude']+fy*mid/111000,'accuracy_m':0}
   if polygon_contains(rings,point):yield a,b
 green=next(((a,b) for rings in polygons['green'] for a,b in intervals(rings) if a<=length<=b),None)
 if not green:return None
 limit=length if stop_at_target else green[1]
 if stop_distance_m is not None:
  limit=min(green[1],stop_distance_m)
 hazards={kind:max((b for rings in polygons[kind] for a,b in intervals(rings)
                    if a<limit),default=None) for kind in polygons if kind!='green'}
 if corridor:
  miss=state.get('journey',{}).get('profile',{}).get('usual_miss',{}).get('value')
  accuracy=start['accuracy_m']
  left=accuracy+(3 if miss=='偏左' else 0)
  right=accuracy+(3 if miss=='偏右' else 0)
  for kind in hazards:
   for rings in polygons[kind]:
    for ring in rings:
     pts=[xy(*point) for point in ring]
     projected=[(x*fy-y*fx,x*fx+y*fy) for x,y in pts]
     for (x,a),(u,b) in zip(projected,projected[1:]):
      if max(x,u)<-left or min(x,u)>right or max(a,b)<=0 or min(a,b)>=limit:continue
      if abs(u-x)>1e-8:
       limits=sorted(((-left-x)/(u-x),(right-x)/(u-x)))
       far=max(a+max(0,limits[0])*(b-a),a+min(1,limits[1])*(b-a))
      else:
       far=max(a,b)
      hazards[kind]=max(hazards[kind] or 0,far)
 return {'front_m':green[0],'back_m':green[1],'target_m':length,'hazards':hazards,
         'accuracy_m':start['accuracy_m'],
         'hazard_coverage_complete':hole.get('hazard_coverage_complete') is True}


@planning_geometry_cache
def green_crossing_advice(state,now,**kwargs):
 out=_green_crossing_advice(state,now,**kwargs)
 if out and out.get('option') and state.get('facts') and state.get('journey',{}).get('memory_allowed') is True:
  from hole_history import note
  number=fact_value(state,'context.active_hole');course=state.get('evidence',{}).get(fact_value(state,'context.course_snapshot'),{}).get('data',{})
  target=kwargs.get('target') or next((o for h in course.get('holes',[]) if h['number']==number for o in h.get('objects',[]) if o['kind']=='green_center'),None)
  extra=note(state,number,fact_value(state,'context.device_position'),target,out['option'].get('club'))
  if extra and '历史参考：' not in out['text']:out['text']+=extra
 return out

@planning_geometry_cache
def _green_crossing_advice(state, now, *, target=None, short_game=False, lie=None, verify_playability=False, allow_roll_in=False, compare_safety=False, pin_depth=None, assess_lie=False, lie_playability=None):
 """Keep an airborne option when a mapped hazard leaves a usable carry window."""
 line=landing_line(state,now,target,corridor=True,include_ob=True,stop_at_target=True)
 if not line or not any(v is not None for v in line['hazards'].values()):
  return None
 short_distance=line['target_m']<=50*.9144
 if verify_playability and short_game and not short_distance:
  return None
 far,kind=max((value,kind) for kind,value in line['hazards'].items() if value is not None)
 profile=state.get('journey',{}).get('profile',{})
 unit=profile.get('units',{}).get('value','码')
 scale=1 if unit=='米' else .9144
 margin=max(line['accuracy_m'], (2 if short_game else 3)*.9144)
 low=math.ceil((max(far,line['front_m'])+margin)/scale)
 # Reserve enough depth beyond the landing point for roll and range error.
 high=math.floor((line['back_m']-2*margin)/scale)
 before_target=math.floor((line['target_m']-margin)/scale)
 middle_pin=pin_depth=='中' and not short_distance and not short_game
 if middle_pin:
  high=min(high,math.floor((line['target_m']+10*.9144)/scale))
 elif low<=before_target:
  high=min(high,before_target)
 elif low<=high:
  deeper=landing_line(state,now,target,corridor=True,include_ob=True)
  far,kind=max((value,kind) for kind,value in deeper['hazards'].items() if value is not None)
  low=math.ceil((max(far,line['front_m'])+margin)/scale)
 label={'bunker':'沙坑','water':'水障碍','ob':'界外区域'}[kind]
 text=f'沿这条线，{label}远沿约{math.ceil(far/scale)}{unit}。'
 if low>high:
  return {'text':text+'按远沿和可用落点算，这条线的飞越与停球空间不足。可以改瞄果岭较宽处，再核对另一条线的Carry。'}
 distance=f'{low}–{high}{unit}' if low<high else f'{low}{unit}'
 if verify_playability and not short_distance and lie in ('长草','沙坑','不清楚') and not (assess_lie and lie_playability=='clear'):
  if assess_lie and lie=='不清楚':
   required=text+f'这条攻果岭线需要Carry约{distance}。'
   if lie_playability is None:
    return {'text':required+'先确认现场是球道、长草还是沙坑？',
            'lie_question':{'lie':lie,'choices':['球道','长草','沙坑','暂不确定']}}
   return {'text':required+'球位能干净触球并稳定打够时可评估攻果岭；深草或沙坑沿限制出球时可先脱困。现场确认球位后再定这杆。'}
  if assess_lie and lie in ('长草','沙坑'):
   from approach_lie import CHOICES
   required=text+f'这条攻果岭线需要Carry约{distance}。'
   if lie_playability is None:
    question='长草里球是浮着、能干净触球，还是埋得较深？' if lie=='长草' else '这处沙坑球位能稳定打够这个Carry，且坑沿不挡出球吗？'
    return {'text':required+question,'lie_question':{'lie':lie,'choices':CHOICES[lie]}}
   if lie_playability=='unknown':
    return {'text':required+'若能干净触球并稳定打够，可继续比较攻果岭用杆；触球或出球高度没把握时，先选看得见的宽处过渡。'
            +'你可以补充浅草、深草或坑沿情况，我再细化方案。'}
   from shot_club_advice import recommendation
   return {'text':required+('球埋得深，先打到看得见的宽处，出草后再攻果岭。' if lie=='长草' else '球埋得深或坑沿挡出球，先打出沙坑，落在看得见的宽处，再按实际球位进攻。')+recommendation(profile,lie=lie,unit=unit)}
  return {'text':text+f'这条攻果岭线需要Carry约{distance}。按当前球位，先把球送回看得见、较宽的球道，再从实际落点规划下一杆。'}
 if not verify_playability or short_distance:
  text+=f'落点放在障碍后，目标Carry约{distance}。'
 else:
  text+=f'这条攻果岭线需要Carry约{distance}。'
 if short_game or (lie in ('长草','沙坑') and (not verify_playability or short_distance)):
  if lie=='沙坑':
   uses=profile.get('lofted_wedge_uses',{}).get('value',{})
   sand=[str(loft) for loft,use in uses.items() if use=='沙坑']
   loft='58' if '58' in sand or not sand else min(sand,key=lambda value:abs(int(value)-58))
   club=loft+'度杆'
   basis='按你注明的沙坑用途，' if loft in sand else ''
   return {'text':text+basis+'这杆可考虑'+club+'打出沙坑，控制落点在障碍后。先确认坑沿、球是否埋沙和沙质，按你熟悉的沙坑挥幅打这个目标Carry。现场核对落地后的滚动空间。',
           'option':{'club':club,'status':'candidate','source':'user_reported_bunker_use' if loft in sand else 'bunker_club_candidate','not_for_learning':True}}
  from shot_club_advice import recommendation
  club_text=recommendation(profile,target_yards=(low+high)/2*scale/.9144,lie=lie,unit=unit)
  return {'text':text+'这条线可评估熟悉的抛切。'+club_text+'现场核对触球、障碍边缘和滚动空间后再打。'}
 from iron_estimates import iron_table,pitching_wedge
 from club_selection import same_label
 table=iron_table(profile)
 clubs=[(f'{n}号铁',v['carry_yards']) for n,v in table.items() if n>=5 or v['source']=='user_report']
 wedge=pitching_wedge(profile,table)
 if wedge:
  clubs.append(('P杆',wedge['carry_yards']))
 reported_labels=[]
 if verify_playability:
  from tee_strategy import reported_carry_clubs
  for key,club in reported_carry_clubs(profile).items():
   if key=='driver' and lie!='发球台':
    continue
   clubs=[entry for entry in clubs if not same_label(entry[0],club['label'])]
   clubs.append((club['label'],club['carry_yards']))
   reported_labels.append(club['label'])
 else:
  for key,label in (('driver','一号木'),('three_wood','3号木'),('hybrid','铁木杆'),('long_iron','长铁杆')):
   club=profile.get(key,{}).get('value') or {}
   if isinstance(club,dict) and club.get('distance_type')=='carry' and club.get('units') in ('米','码'):
    distance=club.get('distance')
    if type(distance) in (int,float) and 0<distance<=400:
     clubs.append((club.get('club_name') or label,distance/(.9144 if club['units']=='米' else 1)))
 def estimated_club(name):
  if any(same_label(name,label) for label in reported_labels):return False
  if name=='P杆':return bool(wedge and wedge['source']!='user_report')
  return bool(re.fullmatch(r'[2-9]号铁',name) and table.get(int(name[0]),{}).get('source')=='estimated_10_yard_gap')
 range_clubs=set()
 if assess_lie:
  goal=(low+high)/2*scale/.9144
  for loft,value in profile.get('lofted_wedge_ranges',{}).get('value',{}).items():
   if not isinstance(value,dict) or value.get('units') not in ('码','米'):continue
   left,right=value.get('low'),value.get('high')
   if type(left) not in (int,float) or type(right) not in (int,float) or not 0<=left<=right<=250:continue
   divisor=.9144 if value['units']=='米' else 1
   start,end=left/divisor,right/divisor
   candidate=max(start,min(end,goal))
   if low<=candidate*.9144/scale<=high:
    label=str(loft)+'度杆'
    clubs.append((label,candidate))
    range_clubs.add(label)
 fits=[(abs(carry*.9144/scale-(low+high)/2),club) for club,carry in clubs
       if low<=carry*.9144/scale<=high]
 if middle_pin:
  checked=[]
  for error,club in fits:
   carry=next(value for label,value in clubs if label==club)*.9144
   checked_line=landing_line(state,now,target,corridor=True,include_ob=True,
                             stop_distance_m=carry+2*margin)
   if checked_line:
    hazard=max((value for value in checked_line['hazards'].values() if value is not None),default=0)
    if max(checked_line['front_m'],hazard)+margin<=carry<=checked_line['back_m']-2*margin:
     checked.append((error,club))
  fits=checked
 # The preferred landing window does not cap a club's usable Carry.
 # Consider the shortest adequate club, then verify its normal landing deeper
 # on the green; otherwise offer a controlled swing subject to confirmation.
 if not fits and verify_playability and not short_distance and (lie in ('球道','发球台') or (assess_lie and lie_playability=='clear')):
  adequate=sorted((carry,estimated_club(club),club) for club,carry in clubs if carry*.9144/scale>=low)
  if adequate:
   carry,_,club=adequate[0]
   carry_m=carry*.9144
   deeper=landing_line(state,now,target,corridor=True,include_ob=True,stop_distance_m=carry_m+2*margin)
   safe=False
   if deeper:
    farthest=max((value for value in deeper['hazards'].values() if value is not None),default=0)
    safe=max(deeper['front_m'],farthest)+margin<=carry_m<=deeper['back_m']-2*margin
   estimated=club=='P杆' and wedge and wedge['source']!='user_report'
   estimated=estimated or (re.fullmatch(r'[2-9]号铁',club) and table.get(int(club[0]),{}).get('source')=='estimated_10_yard_gap' and not any(same_label(club,name) for name in reported_labels))
   basis='按7号铁杆距暂估' if estimated else '按已报杆距'
   amount=round(carry_m/scale)
   if safe:
    return {'text':text+f'从最低所需Carry向上选杆，可考虑{club}，{basis}Carry约{amount}{unit}。这支杆的常规落点在已核对的果岭较深处；现场确认草阻、风和落地后的停球空间。',
            'option':{'club':club,'status':'candidate','source':'deeper_pin_line','not_for_learning':True},'attack_candidate':True}
   return {'text':text+f'从最低所需Carry向上选杆，可考虑{club}，{basis}常规Carry约{amount}{unit}。若你熟悉这支杆的控制挥幅，可把目标Carry控制在约{distance}；能否稳定打出这个距离，需要你确认。常规Carry的更深落点尚未核对可用，不能直接按全距离打。',
           'nearby_club':{'club':club,'carry_yards':carry,'status':'needs_carry_confirmation'}}
 option=None
 if fits:
  if middle_pin:
   flag_yards=line['target_m']/.9144
   from hole_history import weight as history_weight
   history_origin=fact_value({'facts':state.get('facts',{})},'context.device_position')
   history_hole=fact_value({'facts':state.get('facts',{})},'context.active_hole')
   history_course=state.get('evidence',{}).get(fact_value({'facts':state.get('facts',{})},'context.course_snapshot'),{}).get('data',{})
   history_target=target or next((o for h in history_course.get('holes',[]) if h['number']==history_hole for o in h.get('objects',[]) if o['kind']=='green_center'),None)
   club=min((club for _,club in fits),
            key=lambda name:abs(next(value for label,value in clubs if label==name)-flag_yards)+10*history_weight(state,history_hole,history_origin,history_target,name))
   text+='中旗可把平旗和稍长的Carry纳入候选。'
  else:
   from hole_history import weight as history_weight
   history_origin=fact_value({'facts':state.get('facts',{})},'context.device_position');history_hole=fact_value({'facts':state.get('facts',{})},'context.active_hole')
   course=state.get('evidence',{}).get(fact_value({'facts':state.get('facts',{})},'context.course_snapshot'),{}).get('data',{})
   history_target=target or next((o for h in course.get('holes',[]) if h['number']==history_hole for o in h.get('objects',[]) if o['kind']=='green_center'),None)
   _,club=min(fits,key=lambda row:(row[0]+10*history_weight(state,history_hole,history_origin,history_target,row[1]),estimated_club(row[1]),row[1]))
  text+='按现有杆距，可考虑'+club+'。'
  if middle_pin:
   def carry_label(name):
    carry=next(value for label,value in clubs if label==name)*.9144/scale
    estimated=(re.fullmatch(r'[2-9]号铁',name) and table.get(int(name[0]),{}).get('source')=='estimated_10_yard_gap'
               and not any(same_label(name,label) for label in reported_labels))
    return name+f'Carry约{round(carry)}{unit}'+('（按7号铁杆距暂估）' if estimated else '')
   text+=carry_label(club)+'。'
   longer=[name for _,name in fits if name!=club
           and next(value for label,value in clubs if label==name)>=line['target_m']/.9144]
   if longer:
    alternative=min(longer,key=lambda name:next(value for label,value in clubs if label==name))
    text+='稍长的备选可比较'+carry_label(alternative)+'，现场确认落地后能停住。'
  if club in range_clubs:
   text+='角度杆的目标Carry取自你已报的距离范围。'
  if assess_lie and lie in ('长草','沙坑'):
   text+='按你确认的触球条件，现场核对草阻、出球高度和停球空间。'
  option={'club':club,'status':'candidate','source':'mapped_crossing_window','not_for_learning':True}
 elif verify_playability and not short_distance:
  if lie=='球道' or (middle_pin and lie=='发球台'):
   from tee_strategy import actual_position_layup,actual_position_roll_in
   direct=actual_position_roll_in(state,now,unit,compare_safety=compare_safety,direct=True)
   if direct:
    return {**direct,'text':text+'也可以改瞄果岭内的另一处落点。'+direct['text'],
            'attack_candidate':True}
   roll=actual_position_roll_in(state,now,unit,compare_safety=compare_safety) if allow_roll_in else ''
   if roll:
    return {**roll,'text':text+roll['text'],**({'attack_candidate':True} if compare_safety else {})}
   # A short-of-pin target is a preference, not the far edge of the green.
   # Recheck each near club against the deeper green and its full hazard corridor.
   nearby=sorted((abs(carry*.9144/scale-(low+high)/2),club,carry)
                 for club,carry in clubs
                 if min(abs(carry*.9144/scale-low),abs(carry*.9144/scale-high))<=5)
   for _,club,carry in nearby:
    carry_m=carry*.9144
    deeper=landing_line(state,now,target,corridor=True,include_ob=True,
                        stop_distance_m=carry_m+2*margin)
    if not deeper:continue
    farthest=max((value for value in deeper['hazards'].values() if value is not None),default=0)
    if max(deeper['front_m'],farthest)+margin<=carry_m<=deeper['back_m']-2*margin:
     amount=round(carry_m/scale)
     estimated=(re.fullmatch(r'[2-9]号铁',club) and table.get(int(club[0]),{}).get('source')=='estimated_10_yard_gap'
                and not any(same_label(club,label) for label in reported_labels))
     origin='按7号铁杆距暂估，' if estimated else '按已报杆距，'
     return {'text':f'沿这条线，{label}远沿约{math.ceil(far/scale)}{unit}。'
                   +f'把落点放在旗位附近较深的果岭，可考虑{club}，{origin}Carry约{amount}{unit}。'
                   +'现场确认这处落点的宽度、风和落地后的滚动空间。',
             'option':{'club':club,'status':'candidate','source':'deeper_pin_line','not_for_learning':True},
             'attack_candidate':True}
   if nearby:
    _,club,carry=nearby[0]
    amount=round(carry*.9144/scale)
    source='按7号铁杆距估算，' if re.fullmatch(r'[2-9]号铁',club) and table.get(int(club[0]),{}).get('source')=='estimated_10_yard_gap' and not any(same_label(club,label) for label in reported_labels) else '按已报杆距，'
    return {'text':text+source+f'最接近的是{club}，Carry约{amount}{unit}。'
            +f'当前只核对到约{distance}的窄落点窗；这支杆能否稳定控制到这个范围，需要你确认。'
            +'若按常规Carry打，先核对更深处的果岭落点和滚动空间。',
            'nearby_club':{'club':club,'carry_yards':carry,'status':'needs_carry_confirmation'}}
   if assess_lie and clubs and max(carry for _,carry in clubs)*.9144/scale<low:
    return {'text':'现有球道球杆的Carry不足以覆盖已核对的攻果岭落点，这杆先考虑球道过渡。',
            'attack_unreachable':True}
   layup=actual_position_layup(state,now,compare_safety=True) if compare_safety else actual_position_layup(state,now)
  else:
   layup=''
  if assess_lie and lie_playability=='clear' and lie in ('长草','沙坑'):
   return {'text':text+'按你确认的触球条件，可以继续评估直接攻果岭；现有杆距还未覆盖这个落点窗，请补充相应挖起杆或短铁的Carry。',
           'missing_attack_carry':True}
  return {'text':text+'现有杆距未匹配到已核对的攻果岭落点，先确认你能稳定打约'+distance+'的球杆和Carry。'
          +(layup or '先找一段看得见、够宽的球道过渡，再按实际落点规划下一杆。')}
 else:
  text+='按你能稳定打出的Carry选杆。'
 return {'text':text+'现场再核对球位、风和落地后的滚动空间。','option':option}
