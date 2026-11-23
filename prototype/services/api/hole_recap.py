"""Evidence-based hole narrative, separating score, incidents and data conflicts."""
from round_state import canonical,fact_value
from shot_evidence import haversine
from shot_review_evidence import counted,replay_origin_conflicts

def review(state,number):
 from round_view import summary,round_records
 rows=summary(state)['scores'];score=next((r for r in rows if r['hole']==number),None)
 clubs=[r for r in round_records(state)['clubs'] if r.get('hole')==number and r.get('source')!='score_placeholder' and r.get('club')!='推杆']
 if not score and not clubs:return f'第{number}洞暂无已确认的成绩或实际用杆记录。可以换一洞。'
 j=state['journey'];eid=fact_value(state,'context.course_snapshot');key=canonical([(j.get('round') or {}).get('id'),eid,number]);flow=j.get('round_ledger',{}).get(key,{})
 shots=counted(flow);conflicts=replay_origin_conflicts(flow);shot_numbers={r['id']:r['stroke_number'] for r in shots}
 course=state.get('evidence',{}).get(eid,{}).get('data',{});hole=next((h for h in course.get('holes',[]) if h['number']==number),{});par=hole.get('par')
 unit=j.get('profile',{}).get('units',{}).get('value','码');scale=1 if unit=='米' else .9144
 from shot_landing_evidence import classify as landing_evidence,wording as landing_wording
 surfaces={r['id']:landing_evidence(state,hole,r) for r in shots}
 lines=[]
 if score:
  lines.append(f'第{number}洞{score["total"]}杆，'+(f'{score["putts"]}推' if score['putts'] is not None else '推杆数未报')+'，'+(f'{score["penalties"]}罚杆。' if score['penalties'] is not None else '罚杆数未报。'))
  if par:
   delta=score['total']-par;result='打平标准杆' if delta==0 else f'高于标准杆{delta}杆' if delta>0 else f'低于标准杆{-delta}杆'
   lines.append(f'这是一个{par}杆洞，本洞{result}。')
 incidents=[]
 for incident in flow.get('incidents',[]):
  if incident.get('status')=='cancelled' or incident.get('phase')!='closed' or incident.get('shot_id') not in shot_numbers:continue
  penalties=[p for p in flow.get('sequence',[]) if p.get('kind')=='penalty' and p.get('active',True) and p.get('incident_id')==incident['id']]
  amount=sum(p['amount'] for p in penalties)
  ball=flow.get('balls',{}).get(incident.get('ball_id'),{})
  if not amount and not ball.get('inside_penalty_area') and ball.get('status') not in ('ob','water','lost'):continue
  cause={'ob':'出界（OB）','water':'下水','lost':'遗失'}.get(incident.get('cause'))
  if not cause:continue
  incidents.append(incident)
  n=shot_numbers[incident['shot_id']];shot=next(r for r in shots if r['id']==incident['shot_id'])
  line=f'关键转折是第{n}杆'+(f'使用{shot["club"]}' if shot.get('club') else '')+f'确认{cause}'
  line+=f'，明确计入{amount}杆罚杆。' if amount else '，按记录继续打原球。'
  option=incident.get('option')
  if option=='stroke_distance':line+='登记的处理方式是回上一杆位置重打。'
  elif option=='back_on_line':line+='登记的处理方式是向后延线救济。'
  elif option=='lateral':line+='登记的处理方式是侧向救济。'
  if incident.get('promoted'):line+='暂定球随后成为使用中球。'
  lines.append(line)
 if score and score['penalties'] and not incidents:
  lines.append(f'成绩中登记了{score["penalties"]}罚杆，但现有事故记录未能对应到具体击球，暂不能确定事故发生在哪一杆。')
 for shot in shots:
  surface=surfaces.get(shot['id'])
  if not surface or surface['kind']!='bunker' or (surface['source']=='user_report' and surface.get('confirmation','confirmed')!='confirmed'):continue
  next_shot=next((r for r in shots if r['stroke_number']>shot['stroke_number']),None)
  line=f'这洞的关键落点是第{shot["stroke_number"]}杆'+(f'{shot["club"]}' if shot.get('club') else '')+'，'+landing_wording(surface)+'。'
  if next_shot and next_shot.get('origin') and shot.get('landing') and haversine(next_shot['origin'],shot['landing'])<=10:
   next_surface=surfaces.get(next_shot['id'])
   if next_surface and next_surface['kind']=='green' and (next_surface['source']=='map_geometry' or next_surface.get('confirmation','confirmed')=='confirmed'):
    line+=f'随后第{next_shot["stroke_number"]}杆'+(f'用{next_shot["club"]}' if next_shot.get('club') else '')+'从该沙坑位置打到果岭。'
  lines.append(line)
 for shot in shots:
  conflict=conflicts.get(shot['id'])
  if conflict:
   raw=shot.get('distance_m');value=f'约{round(raw/scale)}{unit}' if raw is not None else '未记录'
   lines.append(f'但第{shot["stroke_number"]}杆的数据需要先核对：{conflict["reason"]}，原记录距离{value}暂不用于评价这次击球。')
 green=next((o for o in hole.get('objects',[]) if o.get('kind')=='green_center'),None)
 good=[r for r in shots if r['id'] not in conflicts and r.get('club')!='推杆']
 if not shots:
  good=[dict(r,id=None) for r in clubs]
 if good:
  progress=[]
  # The key incident is already described; explain the subsequent progression.
  incident_numbers=[shot_numbers[r['shot_id']] for r in incidents]
  after=max(incident_numbers) if incident_numbers else 0
  for shot in good:
   n=shot.get('stroke_number')
   if after and (not n or n<=after):continue
   line=(f'第{n}杆' if n else '一条已记击球')+'使用'+(shot.get('club') or '未报球杆')
   distance=shot.get('distance_m',shot.get('total_horizontal_m'))
   if distance is not None:line+=f'，水平总距离约{round(distance/scale)}{unit}'
   surface=surfaces.get(shot.get('id'))
   if surface:line+='，'+landing_wording(surface)
   if green and shot.get('landing'):
    left=haversine(shot['landing'],green)/scale
    if left>15*.9144/scale:line+=f'，落定后距果岭参考点直线约{round(left)}{unit}'
   progress.append(line)
  if progress:
   excerpt=progress if len(progress)<=4 else [progress[0]]+progress[-3:]
   lines.append(('后续过程：' if incidents else '击球过程：')+'；'.join(excerpt)+'。以上击球距离含滚动，不是Carry。')
 if score:
  from round_technical_stats import calculate
  stat=calculate(state,[score],{number:par} if par else {})['holes'][0]
  if stat['green_stroke'] is not None:
   on=stat['green_stroke'];lines.append(f'按地图落点核对，第{on}杆首次上果岭'+('，达到标准杆上果岭。' if stat['gir'] else f'；本洞标准杆上果岭要求不晚于第{par-2}杆，这次未达到。'))
  if score['putts'] is not None:lines.append(f'最后以{score["putts"]}推收尾。')
 if incidents:
  first=incidents[0];n=shot_numbers[first['shot_id']]
  scene='本洞开球' if n==1 else f'本洞第{n}杆对应位置的进攻'
  emphasis='水域的飞越距离与左右偏差空间' if first['cause']=='water' else '落区与界外边界的横向余量' if first['cause']=='ob' else '落点可视性和可找球区域'
  lines.append(f'下次{scene}，优先核对{emphasis}，再按现场球位和风选杆。单次事故先作路线提醒。')
 elif any(v and v['kind']=='bunker' and (v['source']!='user_report' or v.get('confirmation','confirmed')=='confirmed') for v in surfaces.values()):
  trouble=next(r for r in shots if surfaces.get(r['id']) and surfaces[r['id']]['kind']=='bunker' and (surfaces[r['id']]['source']!='user_report' or surfaces[r['id']].get('confirmation','confirmed')=='confirmed'))
  lines.append(f'下次重点比较第{trouble["stroke_number"]}杆的目标落点与该沙坑的前后、左右间隔；当时的原瞄准点和实际Carry未完整记录，目前不能认定是距离不够还是方向偏差。')
  from hole_recap_options import explain
  lines.append(explain(state,hole,shots,conflicts,unit))
 elif score and score['putts'] is not None and score['putts']>=3:
  lines.append('下一步先比较第一推距离和停球位置；缺少推杆距离记录，目前不能判定是读线还是速度问题。')
 elif score and stat['gir'] is False:
  from hole_recap_options import explain
  lines.append(explain(state,hole,shots,conflicts,unit))
 else:
  if good:
   last=good[-1];label=f'第{last["stroke_number"]}杆' if last.get('stroke_number') else '最后一杆已记进攻'
   lines.append(label+'使用'+(last.get('club') or '未报球杆')+'，这次落点可以留作下次选杆参考；当时的目标和触球条件未完整记录，先不判断哪种打法更好。')
  else:lines.append('这洞目前只有成绩，缺少具体击球过程，暂时不能评价哪一杆的打法。')
 if conflicts:lines.append('先核对上述起点记录，再判断具体击球效果；成绩保持原记录。')
 return '\n'.join(lines)
