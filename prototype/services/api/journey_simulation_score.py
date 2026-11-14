"""Protocol 42: optional previous-hole score prompt after explicit next-hole simulation."""
import copy,hashlib,re
from round_state import require,canonical,fact_value,reduce

def simulated_green_point(hole, point):
 from lie_position import polygon_contains
 from shot_evidence import haversine
 green=hole.get('simulation_positions',{}).get('green')
 if green and haversine(green,point)<=2:return True
 for path in hole.get('display_paths',[]):
  if path.get('kind')!='GreenTrace' or len(path.get('points',[]))<3:continue
  ring=[[v['longitude'],v['latitude']] for v in path['points']]
  if ring[0]!=ring[-1]:ring.append(ring[0])
  if polygon_contains([ring],point):return True
 return False


def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==42,'unsupported simulated score prompt protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();prior=s.get('journey',{}).get('simulation_score_receipts',{}).get(p['event_id'])
 if prior:
  require(prior==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 previous_hole=fact_value(s,'context.active_hole')
 previous_on_green=False
 one_to_green=False
 strokes_to_green=None
 if p.get('_score_v72') and p.get('type')=='simulation_hole':
  from lie_position import infer,fresh_position
  from shot_evidence import haversine
  previous_on_green=(infer(s,now) or {}).get('label')=='果岭'
  if not previous_on_green:
   course=s.get('evidence',{}).get(fact_value(s,'context.course_snapshot'),{}).get('data',{})
   hole=next((h for h in course.get('holes',[]) if h['number']==previous_hole),{})
   green=hole.get('simulation_positions',{}).get('green')
   pos=fresh_position(s,now)
   if course.get('reference_simulation') is True and green and pos and pos['value'].get('simulation_source')=='map_click':
    previous_on_green=haversine(green,pos['value'])<=2
    if not previous_on_green and p.get('_sim_putts_v82'):
     from lie_position import polygon_contains
     for path in hole.get('display_paths',[]):
      if path.get('kind')!='GreenTrace' or len(path.get('points',[]))<3:continue
      ring=[[point['longitude'],point['latitude']] for point in path['points']]
      if ring[0]!=ring[-1]:ring.append(ring[0])
      if polygon_contains([ring],pos['value']):
       previous_on_green=True
       break
  if previous_on_green and p.get('_infer_putts_v74'):
   from shot_links import scope,pair,valid_record
   points=pair(s)
   shot_scope=scope(s)
   candidates=[row for row in s['journey'].get('shot_location_candidates',[])
               if (row['round_id'],row['course'],row['hole'])==shot_scope]
   if len(candidates)==2 and points:
    # The two points must start at the tee, not at an intermediate ball position.
    course=s.get('evidence',{}).get(shot_scope[1],{}).get('data',{})
    hole=next((h for h in course.get('holes',[]) if h['number']==previous_hole),{})
    tee=hole.get('simulation_positions',{}).get('tee')
    ids=[row['id'] for row in points]
    pos=fresh_position(s,now)
    one_to_green=bool(tee and pos and haversine(tee,points[0]['point'])<=10
                     and haversine(pos['value'],points[-1]['point'])<=5
                     and any(valid_record(s,row) and row['pair_ids']==ids and not row.get('inferred_from_score')
                             for row in s['journey'].get('confirmed_shot_distances',[])))
   if p.get('_infer_multi_putts_v79') and len(candidates)>=2:
    course=s.get('evidence',{}).get(shot_scope[1],{}).get('data',{})
    hole=next((h for h in course.get('holes',[]) if h['number']==previous_hole),{})
    tee=hole.get('simulation_positions',{}).get('tee')
    pos=fresh_position(s,now)
    confirmed={tuple(row['pair_ids']) for row in s['journey'].get('confirmed_shot_distances',[])
               if valid_record(s,row) and not row.get('inferred_from_score')}
    if p.get('_sim_putts_v82') and course.get('reference_simulation') is True:
     from shot_links import live
     rejected={tuple(row['pair_ids']) for row in s['journey'].get('rejected_shot_links',[])
               if row['scope']==list(shot_scope)}
     confirmed.update((a['id'],b['id']) for a,b in zip(candidates,candidates[1:])
                      if b['point'].get('simulation_source')=='map_click' and live(s,a) and live(s,b)
                      and (a['id'],b['id']) not in rejected)
    trail=candidates
    if p.get('_followups_v84') and course.get('reference_simulation') is True:
     first_green=next((i for i,row in enumerate(candidates) if simulated_green_point(hole,row['point'])),None)
     if first_green is not None:
      stayed_on_green=all(simulated_green_point(hole,row['point']) for row in candidates[first_green:])
      trail=candidates[:first_green+1] if stayed_on_green else []
    if (len(trail)>=2 and tee and pos and haversine(tee,trail[0]['point'])<=10
        and haversine(pos['value'],candidates[-1]['point'])<=5
        and all((a['id'],b['id']) in confirmed for a,b in zip(trail,trail[1:]))):
     strokes_to_green=len(trail)-1
 adapted=copy.deepcopy(p);adapted['protocol_version']=41
 from journey import reduce_journey as previous
 result=previous(s,adapted,seq,now);j=s['journey'];session=s.get('session',{})
 if result.get('simulation_hole_switched') and previous_hole is not None:
  course=s.get('evidence',{}).get(fact_value(s,'context.course_snapshot'),{}).get('data',{})
  order=[h['number'] for h in course.get('holes',[])];target=p['hole']
  next_hole=previous_hole in order and order.index(previous_hole)+1<len(order) and order[order.index(previous_hole)+1]==target
  prompted=session.setdefault('gps_prompted_holes',[])
  if (next_hole and fact_value(s,'preferences.proactive') is True and not j.get('quiet')
      and not fact_value(s,'context.quiet',False) and not fact_value(s,'context.preparing',False)
      and fact_value(s,f'holes.{previous_hole}.total') is None and not session.get('draft')
      and not any(q.get('status')=='pending' for q in s.get('questions',{}).values()) and previous_hole not in prompted):
   qid=p['event_id']+'-previous-score'
   reduce(s,'question',{'id':qid,'target':f'holes.{previous_hole}','field':'total','deps':{},'proactive':True,**({'allow_unknown_putts':True} if previous_on_green else {}),**({'one_to_green':True} if one_to_green else {}),**({'strokes_to_green':strokes_to_green} if strokes_to_green else {})},seq,now)
   session['question_id']=qid;session['score_target']=previous_hole;prompted.append(previous_hole)
   message=f'第{previous_hole}洞还没记分，刚才一共几杆？'
   row={'event_id':p['event_id'],'intent':'fact_request','domain':'score','question_owner':'score.total','scope':[(j.get('round') or {}).get('id'),fact_value(s,'context.course_snapshot'),target],'at':now,'spoken_text':message}
   j['response_context']=row;j.setdefault('dialogue_audit',[]).append(copy.deepcopy(row))
   result={**result,'text':message,'speak_allowed':True,'question_id':qid}
 j.setdefault('simulation_score_receipts',{})[p['event_id']]=sha
 return result
