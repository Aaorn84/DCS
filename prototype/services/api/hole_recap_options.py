"""Optional retrospective alternatives from the same shared strategy used live."""
from shot_evidence import haversine
from report_geometry import planning_geometry_cache

@planning_geometry_cache
def explain(state,hole,shots,conflicts,unit):
 usable=[s for s in shots if s['id'] not in conflicts and s.get('origin') and s.get('landing') and s.get('club')!='推杆']
 if not usable:return '缺少当时的起点和落点，暂不能比较具体路线。'
 shot=usable[-1];green=next((o for o in hole.get('objects',[]) if o.get('kind')=='green_center'),None)
 if not green:return '缺少果岭参考点，暂不能比较进攻路线。'
 scale=1 if unit=='米' else .9144
 actual=f'先看第{shot["stroke_number"]}杆：当时用{shot.get("club") or "未报球杆"}，打完后到果岭参考点还剩约{round(haversine(shot["landing"],green)/scale)}{unit}。'
 j=state.get('journey',{});model=j.get('offline_local_round');pinned=j.get('shared_web_package')
 if not model or not pinned:return actual+'缺少可重建的当时球局，先核对该杆目标落点与障碍的前后、左右间隔。'
 from state_components import materialize
 import copy
 historical=copy.deepcopy(materialize(model))
 historical.update(hole=hole['number'],position=shot['origin'],stage='playing',finished=False,pending=None,draft=None,lie='unknown',selection=None)
 historical['holes'][str(hole['number'])].update(score=None,rows=[],incidents=[])
 from shared_core import call
 assessment=call('plan',package=materialize(pinned['items'][0]),state=historical,intent={'kind':'layup' if hole.get('par')==5 else 'default'})
 options=assessment.get('options') or []
 if options:
  choice=options[0]
  actual+=f'按当前地图和已知杆距，可重新比较{choice["club"]}，Carry约{round(choice["carry_yards"]*.9144/scale)}{unit}、下一杆剩约{round(choice["remaining_yards"]*.9144/scale)}{unit}的路线。'
 else:actual+='目前地图与杆距未核对到另一处可用落点。'
 return actual+'这是按当前资料重算；当时的风、触球条件和瞄准点未完整保存，不能认定当时应该换杆或换方向。'
