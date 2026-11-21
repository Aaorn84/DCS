"""Concrete, conditional alternatives from a recorded shot origin and current map."""
from round_state import fact_value
from shot_evidence import haversine
from tee_geometry import planning_geometry_cache

@planning_geometry_cache
def explain(state,hole,shots,conflicts,unit):
 number=hole['number'];par=hole.get('par');scale=1 if unit=='米' else .9144
 green=next((o for o in hole.get('objects',[]) if o.get('kind')=='green_center'),None)
 valid=[r for r in shots if r['id'] not in conflicts and r.get('origin') and r.get('landing') and r.get('club')!='推杆']
 if not green or not valid:return '现有记录缺少这洞可核对的击球起点、落点或果岭位置，暂时不能指出哪一杆适合换路线。'
 # A short approach already left by the setup calls for examining the
 # approach itself, not automatically asking the prior shot to go farther.
 from tee_strategy import reported_carry_clubs
 known=reported_carry_clubs(state['journey'].get('profile',{}))
 setup=next((r for r in valid if r['stroke_number']==2),None) if par==5 else None
 seven=known.get('seven',{}).get('carry_yards')
 long_leave=bool(setup and seven and haversine(setup['landing'],green)/.9144>seven)
 selected=setup if long_leave else next((r for r in valid if r['stroke_number']==max(1,(par or 3)-2)),None)
 if selected is None:
  return '还缺少关键进攻杆的完整记录，暂时不能确定应该调整哪一杆；需要该杆的起点、用杆和落点。'
 n=selected['stroke_number'];club=selected.get('club') or '未报球杆';origin=selected['origin'];landing=selected['landing']
 before=haversine(origin,green)/scale;after=haversine(landing,green)/scale
 distance=selected.get('distance_m');actual=f'先看第{n}杆：当时用{club}'
 if distance is not None:actual+=f'打了约{round(distance/scale)}{unit}（含滚动）'
 actual+=f'，打完后到果岭参考点还剩约{round(after)}{unit}。'
 from shot_landing_evidence import classify,wording
 surface=classify(state,hole,selected)
 if surface:actual+=wording(surface)+'。'
 from tee_strategy import reported_carry_clubs,par_five_routes,aiming_text,layup_club_text,fairway_green_clubs
 profile=state['journey'].get('profile',{});known=reported_carry_clubs(profile)
 eid=fact_value(state,'context.course_snapshot');analysis=dict(course_evidence=eid,hole=number,clubs={k:v for k,v in known.items() if k!='driver'})
 temporary=dict(state,facts=dict(state.get('facts',{})))
 temporary['facts']['context.device_position']=dict(valid=True,value=origin,version=1)
 if par==5 and n==2 and analysis['clubs']:
  routes=par_five_routes(temporary,analysis,[dict(aim_point=origin,crossing_m=None)],broad=True,risk_first=True)
  farther=[r for r in routes if not r.get('layup_long_club') and r['leave_yards']*.9144/scale<after-10*.9144/scale]
  if farther:
   route=min(farther,key=lambda r:r['risk_rank']);target=route['layup'];left=round(route['leave_yards']*.9144/scale)
   alternative=(f'按目前地图和已知杆距重算，可比较瞄{aiming_text(target,unit)}的路线。'
                +layup_club_text(profile,target['carry_yards'],unit)
                +f'这样预计下一杆到果岭参考点约{left}{unit}，比本次留下的距离近约{round(after-left)}{unit}。')
   return actual+alternative+'这个对比按Carry落点估算、未计滚动；记录未完整保存当时的触球条件和风，不能认定当时一定适合这条路线。'
  return actual+'目前地图未核对到中铁杆能到、落区又可用且能明显缩短下一杆距离的另一条路线，所以不能认定这杆应该打得更远。'
 # Compare a mapped green target, never claim the original aiming point was wrong.
 from tee_geometry import tee_targets
 candidates=fairway_green_clubs(profile,list(analysis['clubs'].items()),before*scale/.9144)
 targets=tee_targets(temporary,analysis,candidates,origin=origin,allow_crossing=True,surface='green') if candidates else []
 if targets:
  by_key=dict(candidates)
  target=min(targets,key=lambda r:(r['crossing_m'] is not None,by_key[r['club_key']].get('requires_control',False),by_key[r['club_key']].get('source','user_report')!='user_report',abs(r['carry_yards']-before*scale/.9144),-r['width_m']))
  offset=target['offset'];direction=f'果岭参考方向向{"右" if offset>0 else "左"}偏约{abs(offset)}度' if offset else '果岭参考点方向'
  basis=dict(candidates)[target['club_key']];estimate='（按7号铁杆距暂估）' if basis.get('source','user_report')!='user_report' else ''
  control=(f'这支杆常规Carry约{round(basis["nominal_carry_yards"]*.9144/scale)}{unit}，需要熟悉控制到上述距离的挥幅。' if basis.get('requires_control') else '')
  return (actual+('为避开这次落点所在的沙坑，' if surface and surface['kind']=='bunker' else '')+f'按目前地图和杆距，可比较{target["club"]}{estimate}打向{direction}的果岭落点，目标Carry约{round(target["carry_yards"]*.9144/scale)}{unit}。'
          +control+'这能比较具体的果岭落点；当时瞄准点、风和触球情况未完整记录，尚不能说原来的选杆或方向错了。')
 return actual+'目前地图和杆距未匹配到另一处可核对的果岭落点；还需当时球位、原瞄准点和触球情况，才能判断该换杆还是换方向。'
