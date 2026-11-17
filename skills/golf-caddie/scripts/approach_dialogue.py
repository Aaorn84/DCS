"""Concise approach dialogue; simulated selection is not real-world shot evidence."""
import copy,re
from lie_position import fresh_position,infer
from round_state import fact_value
from approach_strategy import advise as detailed_advise,requested as previous_requested

def requested(text):
 return previous_requested(text) or bool(re.search(r'(?:用|选|拿)(?:哪|那)(?:一)?(?:支|只|个)?杆|选杆建议',text))

def prepare(s,c,now):
 pos=fresh_position(s,now)
 eid=fact_value(s,'context.course_snapshot')
 course=s.get('evidence',{}).get(eid,{}).get('data',{})
 simulated=bool(pos and course.get('reference_simulation') is True and pos['value'].get('simulation_source')=='map_click' and pos['value'].get('simulation_hole')==fact_value(s,'context.active_hole'))
 if simulated:
  c['ball_position_report']='simulation_selected'
  c['ball_position_evidence']={'source':'map_click_simulation','position_version':pos['version'],'not_real_shot_evidence':True}
 if c.get('ball_position_report') in ('user_confirmed','simulation_selected'):
  inferred=infer(s,now)
  if inferred and (not c.get('lie_report') or c.get('lie_evidence',{}).get('source')=='gps_course_surface'):
   c['lie_report']=inferred['label'];c['lie_evidence']=inferred
 report=s['journey'].get('reported_landing',{})
 if report:
  from shot_links import scope
  from round_state import canonical
  from shot_evidence import haversine
  if (report.get('scope')==canonical(scope(s)) and 0<=now-report.get('at',0)<=600
      and pos and report.get('position') and haversine(pos['value'],report['position'])<=5):
   c['lie_report']=report['lie']
   c['lie_evidence']={'label':report['lie'],'source':'user_report','event_id':report['event_id']}
 return pos

def advise(s,c,now,*, practical_rough=False, confirm_landing=False, use_landing_depth=False, verified_lines=False, carry_crossing=False, verify_playability=False, allow_roll_in=False, compare_safety=False):
 calc=copy.deepcopy(c)
 if calc.get('ball_position_report')=='simulation_selected':calc['ball_position_report']='user_confirmed'
 from short_pin_distance import estimate
 pin=estimate(s,now,short_game_only=False)
 out=detailed_advise(s,calc,now,pin=pin);out['detail_text']=out['text']
 from speech_presentation import spoken_text
 text=spoken_text(out['text'])
 text=re.sub(r'(?:OB参考点|障碍参考点)距设备约[0-9.]+(?:码|米)；','',text)
 text=text.replace('这些不是障碍近沿或远沿，不能据此判断能否跨越，也不能证明路线安全。','障碍边界未确认，别勉强飞越。')
 text=text.replace('这是设备位置距离，尚未确认就是球位。','')
 text=text.replace('还没有可用的7铁Carry，先不硬指定杆号。','先用熟悉的球杆分段推进。')
 if practical_rough and c.get('lie_report')=='长草' and pin and 0<out.get('distance_m',0)<=50*.9144:
  from hazard_route import answer as hazard_answer
  from short_pin_distance import pin_distance_wording
  unit=s['journey']['profile'].get('units',{}).get('value','码')
  previous_route=s['journey'].pop('last_hazard_route',None)
  hazard_answer(s,{'kind':'bunker'},now)
  route=s['journey'].pop('last_hazard_route',{})
  if previous_route is not None:s['journey']['last_hazard_route']=previous_route
  pos=fresh_position(s,now)
  text=pin_distance_wording(pin,unit)+'。'
  if verified_lines:
   import math
   from hazard_route import landing_line
   line=landing_line(s,now,corridor=True)
   scale=1 if unit=='米' else .9144
   if line and line['hazards']['bunker'] is not None:
    far=max(v for v in line['hazards'].values() if v is not None)
    margin=max(line['accuracy_m'],3*.9144)
    target=math.ceil((max(line['front_m'],far)+margin)/scale)
    end=(line['back_m']-margin)/scale
    bunker=math.ceil(line['hazards']['bunker']/scale)
    text+=f'朝果岭中央过沙约{bunker}{unit}。'
    if target<=end and target*scale<=line['target_m']:
     text+=(f'球浮在草上，可用熟悉的挖起杆抛切，朝中央Carry约{target}{unit}。'
            '球埋得深或现场落点偏窄，就先切回宽处。')
     if not line.get('hazard_coverage_complete'):text+='先现场核对线路上有没有地图未覆盖的障碍。'
    else:
     text+='这条线没有确认到足够的过沙后落点，先找一条能避开沙坑的路线。'
   else:
    text+='先找一块看得见的落点。球埋得深或过沙后没有把握，就先切回宽处。'
  elif (pos and route.get('kind')=='bunker' and route.get('position_version')==pos['version']
      and route.get('course_evidence')==fact_value(s,'context.course_snapshot') and route['far_m']<out['distance_m']):
   import math
   far=math.ceil(route['far_m']/(1 if unit=='米' else .9144)/5)*5
   scale=1 if unit=='米' else .9144
   depth=(out['distance_m']/scale)-far
   if use_landing_depth and pin['min_m']-far*scale>=10*.9144:
    approximate=round(depth/5)*5
    target=far+5
    text+=(f'朝果岭中央过沙约{far}{unit}，沙坑远沿到旗位约{approximate}{unit}。'
           f'球浮在草上，可以用熟悉的沙杆或挖起杆抛切，'
           f'Carry先瞄约{target}{unit}，落在沙坑后的果岭上，让球往旗位滚。'
           '球埋得深或这条线落点偏窄，就先切回宽处。')
   elif confirm_landing:
    text+=f'朝果岭中央过沙约{far}{unit}。沙坑后有没有一块够宽、能落球的果岭？'
    out['rough_landing_question']={'position_version':pos['version'],'course':route['course_evidence'],
                                 'hole':fact_value(s,'context.active_hole'),'at':now}
   else:
    text+=(f'朝果岭中央过沙约{far}{unit}。球浮在草上，就用你熟悉的沙杆或挖起杆抛切，'
          '落点选在沙坑后、果岭中间较宽的一块，留出过沙余量。'
          '如果球埋得深，先往没沙坑的一侧切出去，给下一杆留个好球位。')
  elif confirm_landing:
   text+='先看清沙坑远沿和沙坑后有没有落点。球埋得深或落点太窄，就先找一条看得见的脱困路线。'
  else:
   text+=('球浮在草上，就用熟悉的挖起杆抛切，落在果岭较宽处。'
          '球埋得深，先打到好球位。如果前面有沙坑，先看清远沿和沙坑后的落点。')
  out['practical_rough']=True
 if carry_crossing and calc.get('ball_position_report')=='user_confirmed':
  from hazard_route import green_crossing_advice
  aimed=estimate(s,now,short_game_only=False,include_aim=True) if pin else None
  crossing=green_crossing_advice(s,now,target=(aimed or {}).get('aim'),lie=c.get('lie_report'),verify_playability=verify_playability,allow_roll_in=allow_roll_in,compare_safety=compare_safety)
  par_five_layup=''
  if compare_safety and c.get('lie_report')=='球道' and out.get('distance_m',0)>50*.9144:
   from tee_strategy import actual_position_layup,actual_position_roll_in
   par_five_layup=actual_position_layup(s,now,compare_safety=True)
   if par_five_layup and not (crossing and (crossing.get('attack_candidate') or crossing.get('option'))):
    unit=s['journey'].get('profile',{}).get('units',{}).get('value','码')
    direct=actual_position_roll_in(s,now,unit,compare_safety=True,direct=True)
    if direct:
     crossing={**direct,'text':direct['text'].removeprefix('另一条线'),'attack_candidate':True}
  if crossing:
   from short_pin_distance import pin_distance_wording
   unit=s['journey'].get('profile',{}).get('units',{}).get('value','码')
   prefix=pin_distance_wording(pin,unit) if pin else text.split('。',1)[0]
   text=prefix+'。'+crossing['text']
   if par_five_layup and (crossing.get('attack_candidate') or crossing.get('option')):
    out['route_choices']={'attack':crossing['text'],'layup':par_five_layup}
    text=prefix+'。两上候选：'+crossing['text']+'\n三上候选：'+par_five_layup
    if crossing.get('tight_green') or crossing.get('near_penalty'):
     reason='果岭可用空间窄' if crossing.get('tight_green') else '攻果岭落点靠近水障碍或已确认界外区'
     text+=f'这球位优先考虑三上，{reason}，球道过渡给落点偏差留的空间更多。'
    text+='现场白桩和当天边界以球场标示为准。'
   out.update(mapped_crossing=True,crossing_option=crossing.get('option'),suggestion=None)
   out.pop('rough_landing_question',None)
 from ball_outcome import reported_penalties
 if reported_penalties(s,fact_value(s,'context.active_hole')):
  text=text.replace('两上候选：','直接攻果岭候选：').replace('三上候选：','过渡后攻果岭候选：')
  text=text.replace('第二杆目标Carry','这杆目标Carry').replace('预计第三杆','预计下一杆')
  text=text.replace('优先考虑三上','优先考虑过渡后攻果岭')
  if out.get('route_choices'):
   out['route_choices']={k:v.replace('第二杆目标Carry','这杆目标Carry').replace('预计第三杆','预计下一杆')
                         for k,v in out['route_choices'].items()}
 out['text']=text
 out['position_provenance']=c.get('ball_position_evidence',{})
 return out
