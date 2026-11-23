"""Derive scoped FIR/GIR from counted shot endpoints, never total minus putts."""
from round_state import fact_value,canonical
from report_geometry import mapped_polygons,polygon_contains,planning_geometry_cache
from shot_evidence import haversine

@planning_geometry_cache
def calculate(state,scores,pars):
 j=state.get('journey',{});rid=(j.get('round') or {}).get('id');eid=fact_value(state,'context.course_snapshot')
 course=state.get('evidence',{}).get(eid,{}).get('data',{});holes={h['number']:h for h in course.get('holes',[])}
 details=[]
 for score in scores:
  number=score['hole'];par=pars.get(number);hole=holes.get(number,{})
  out=dict(hole=number,fir=None,gir=None,green_stroke=None)
  details.append(out)
  flow=j.get('round_ledger',{}).get(canonical([rid,eid,number]))
  if not flow or flow.get('pending'):continue
  from projected_ledger import ball_counts
  events=[v for v in flow.get('sequence',[]) if v.get('active',True) and v.get('ball_id') in flow.get('balls',{}) and ball_counts(flow,v['ball_id'])]
  strokes=[v for v in events if v['kind']=='stroke']
  if not strokes:continue
  first=strokes[0];origin=first.get('origin');tee=hole.get('simulation_positions',{}).get('tee');bbox=hole.get('tee_bbox')
  if not origin:continue
  from report_geometry import inside
  at_tee=(tee and haversine(tee,origin)<=10) or (isinstance(bbox,list) and len(bbox)==4 and inside(bbox,origin))
  if not at_tee:continue
  polygons=mapped_polygons(hole,course.get('reference_simulation') is True)
  def on_surface(point,surface):
   return any(polygon_contains(rings,dict(point,accuracy_m=0)) for rings in polygons[surface].values())
  from shot_landing_evidence import classify
  first_surface=classify(state,hole,first,scope=[rid,eid,number],polygons=polygons)
  if par in (4,5):
   if first_surface and first_surface['source']=='user_report' and first_surface.get('confirmation','confirmed')=='confirmed' and first_surface['kind']!='unknown':out['fir']=first_surface['kind']=='fairway'
   elif first_surface and first_surface['source']=='user_report':pass
   elif first.get('landing') and polygons['fairway']:out['fir']=on_surface(first['landing'],'fairway')
  if not par:continue
  number_taken=0;missing_before=False
  for item in events:
   if item['kind']=='penalty':number_taken+=item['amount'];continue
   number_taken+=1;landing=item.get('landing')
   surface=classify(state,hole,item,scope=[rid,eid,number],polygons=polygons)
   if surface and surface['source']=='user_report':
    if surface.get('confirmation','confirmed')=='confirmed' and surface['kind']!='unknown':on_green=surface['kind']=='green'
    elif surface.get('green_status')=='off':on_green=False
    else:missing_before=True;continue
   elif landing and polygons['green']:on_green=on_surface(landing,'green')
   else:missing_before=True;continue
   if on_green:
    # If earlier endpoints are missing, late arrival cannot establish a miss.
    if number_taken>score['total']:break
    if number_taken<=par-2 or not missing_before:
     out.update(gir=number_taken<=par-2,green_stroke=number_taken)
    break
 def metric(key,eligible):
  known=[v for v in eligible if v[key] is not None];hits=sum(bool(v[key]) for v in known)
  return dict(value=hits/len(known) if known else None,hits=hits,known=len(known),eligible=len(eligible),missing_holes=[v['hole'] for v in eligible if v[key] is None],basis='recorded_map_landings')
 fir=metric('fir',[v for v in details if pars.get(v['hole']) in (4,5)])
 gir=metric('gir',[v for v in details if v['hole'] in pars])
 by_hole={r['hole']:r for r in scores}
 gir_putts=[by_hole[v['hole']]['putts'] for v in details if v['gir'] is True and type(by_hole[v['hole']]['putts']) is int]
 missed=[v for v in details if v['gir'] is False]
 saved=sum(by_hole[v['hole']]['total']<=pars[v['hole']] for v in missed)
 return dict(fir=fir,gir=gir,putts_per_gir=dict(value=sum(gir_putts)/len(gir_putts) if gir_putts else None,known=len(gir_putts),eligible=sum(v['gir'] is True for v in details)),scrambling=dict(value=saved/len(missed) if missed else None,hits=saved,known=len(missed)),holes=details)

def describe(stats):
 lines=[]
 for key,label in [('fir','开球上球道率FIR'),('gir','标准杆上果岭率GIR')]:
  v=stats[key]
  if v['known']:
   lines.append(f'{label}：{v["hits"]}/{v["known"]}（{v["value"]:.1%}，可核对{v["known"]}/{v["eligible"]}洞）。')
  else:lines.append(f'{label}：暂无可核对的逐杆落点。')
  if v['missing_holes']:lines.append('该项待补第'+'、'.join(map(str,v['missing_holes']))+'洞的逐杆落点或完整击球顺序。')
 p=stats['putts_per_gir'];s=stats['scrambling']
 lines.append(f'GIR洞平均推杆：{p["value"]:.2f}推（{p["known"]}洞）。' if p['value'] is not None else 'GIR洞平均推杆：暂无可统计样本。')
 lines.append(f'救帕率：{s["hits"]}/{s["known"]}（{s["value"]:.1%}，未达GIR但打出Par或更好）。' if s['value'] is not None else '救帕率：暂无已核对未达GIR的球洞。')
 lines.append('以上技术统计按已记录落点及用户确认核对；FIR仅统计四、五杆洞，GIR按首次上果岭前的击球及罚杆累计判断。')
 return '\n'.join(lines)
