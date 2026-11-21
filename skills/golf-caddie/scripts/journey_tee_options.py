"""Protocol 37: evidence-based conservative/aggressive tee alternatives, no default choice."""
import copy,hashlib,re
from datetime import datetime
from round_state import require,canonical,fact_value
from dialogue_routing import scope,assent
from tee_strategy import analyze,proposal,SIDES
from journey_projection import answer as projected_answer
from journey_distance_followup import followup_query


def choice(text):
 t=re.sub(r'[\s，,。！!？?]','',text)
 if re.fullmatch(r'(?:我)?(?:今天)?(?:想|要|选|选择|用|走|就选)?(?:保守(?:一点|点|方案|路线)?|稳一点|第一种)(?:吧)?',t):return 'conservative'
 if re.fullmatch(r'(?:我)?(?:今天)?(?:想|要|选|选择|用|走|就选)?(?:进取(?:一点|点|方案|路线)?|进攻(?:方案|路线)?|积极进攻|第二种)(?:吧)?',t):return 'aggressive'
 return None

def silent(s):return s.get('journey',{}).get('quiet') or any(fact_value(s,k) is True for k in ('context.quiet','context.preparing'))
def response(s,p,result,now,owner=None):
 j=s['journey'];muted=silent(s)
 result={**result,'text':'' if muted else result['text'],'speak_allowed':not muted and bool(result['text'])}
 row={'ordinal':len(j.get('dialogue_audit',[]))+1,'event_id':p['event_id'],'intent':'fact_request' if owner!='plan.confirm' else 'player_intent','domain':'tee_route_options','question_owner':owner if not muted else None,'scope':scope(s),'at':now,'spoken_text':result['text']}
 if j.get('dialogue_audit') and j['dialogue_audit'][-1].get('event_id')==p['event_id']:j['dialogue_audit'][-1]['presentation_status']='superseded_before_delivery'
 j['response_context']=row;j.setdefault('dialogue_audit',[]).append(copy.deepcopy(row))
 if owner and not muted:j['last_pending_prompt']=copy.deepcopy(row);j.setdefault('question_prompts',{})[owner]=copy.deepcopy(row)
 return result

def build_routes(s,a,now):
 if not a or a['par'] not in (4,5):return None
 candidates=[c for c in a['candidates'] if c['carry_yards']<a['distance_yards']]
 if len(candidates)<2:return None
 aggressive=max(candidates,key=lambda c:c['carry_yards'])
 # Distinct evidence for lower exposure is mandatory; shortening the club is not enough.
 safer=[c for c in candidates if c['club_key']!=aggressive['club_key'] and not c['zone']['hazards'] and (c['zone']['width_yards']>=aggressive['zone']['width_yards']+max(5,aggressive['zone']['width_yards']*.1) or (a.get('reference_simulation') and aggressive['zone']['hazards']))]
 if not safer:return None
 conservative=max(safer,key=lambda c:c['carry_yards'])
 routes=[];unit=s['journey'].get('profile',{}).get('units',{}).get('value','码');scale=.9144 if unit=='米' else 1
 for kind,c in [('conservative',conservative),('aggressive',aggressive)]:
  projection=projected_answer(s,{'club_key':c['club_key'],'label':c['label'],'unit':unit},now).get('projection')
  if not projection:return None
  width=round(c['zone']['width_yards']*scale);hazards='、'.join(SIDES[h['side']]+h['label'] for h in c['zone']['hazards'])
  if kind=='conservative':risk=(f'避开这段已知障碍，但落区约{width}{unit}宽，方向要准' if c['zone']['width_yards']<=aggressive['zone']['width_yards'] else f'落区更宽，约{width}{unit}，代价是下一杆更长')
  else:risk=(hazards+'，要留意偏向障碍的失误') if hazards else f'落区约{width}{unit}宽，开得更远也要控制方向'
  routes.append({'kind':kind,'club_key':c['club_key'],'club':c['label'],'zone_id':c['zone_id'],'target':SIDES[c['zone']['preferred_side']], 'carry_yards':c['carry_yards'],'remaining_yards':projection['remaining_yards'],'remaining_basis':projection['basis'],'risk':risk})
 return routes

def offer(s,p,a,routes,now,*,brief=None):
 j=s['journey'];c=j['consultation'];c.pop('suggestion',None);c.pop('selected_club',None);c['phase']='tee_options'
 j.pop('distance_comparison_focus',None)
 j['tee_route_options']={'status':'awaiting_choice','routes':copy.deepcopy(routes),'scope':scope(s),'at':now}
 unit=j.get('profile',{}).get('units',{}).get('value','码');scale=.9144 if unit=='米' else 1
 lines=[brief] if brief else []
 for r in routes:
  name='保守' if r['kind']=='conservative' else '进取';remaining=round(r['remaining_yards']*scale/5)*5;carry=round(r['carry_yards']*scale)
  lines.append(f"{name}：{r['club']}约{carry}{unit}，瞄落区{r['target']}，预计下一杆约{remaining}{unit}；{r['risk']}。")
 lines.append('预计距离以实际落点为准。今天想走哪条？')
 return response(s,p,{'text':'\n'.join(lines),'choices':['保守方案','进取方案','自己打'],'tee_routes':copy.deepcopy(routes)},now,'tee.choice')

def reduce_journey(s,p,seq,now):
 require(p.get('protocol_version')==37,'unsupported tee-options protocol')
 require(isinstance(p.get('event_id'),str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',p['event_id'])),'invalid event id')
 require(isinstance(p.get('observed_at'),str),'observation time required');stamp=datetime.fromisoformat(p['observed_at'].replace('Z','+00:00'));require(stamp.tzinfo is not None,'timezone required')
 sha=hashlib.sha256(canonical(p).encode()).hexdigest();j=s.get('journey',{});old=j.get('tee_options_receipts',{}).get(p['event_id'])
 if old:
  require(old==sha,'event id reused with different payload');return {'text':'','speak_allowed':False,'duplicate':True}
 require(p['event_id'] not in j.get('distance_comparison_receipts',{}),'event id already used by another journey protocol')
 before=copy.deepcopy(j.get('consultation') or {});active=j.get('tee_route_options') or {};text=p.get('text','');a=analyze(s,now) if j.get('stage')=='active' else None
 result=None
 same_offer=active.get('status')=='awaiting_choice' and before.get('phase')=='tee_options' and active.get('scope')==scope(s)
 awaiting=same_offer and 0<=now-active.get('at',0)<=300
 if p.get('type')=='message' and same_offer and not awaiting and choice(text):
  fresh=build_routes(s,a,now) if a else None
  result=offer(s,p,a,fresh,now) if fresh else response(s,p,{'text':'路线资料还在，先更新发球台定位，再确认你的选择。'},now)
 elif p.get('type')=='message' and active.get('status')=='selected' and text in ('再想想','重新比较','再比较一下'):
  fresh=build_routes(s,a,now) if a else None
  if fresh:
   j['consultation'].pop('player_intent',None)
   result=offer(s,p,a,fresh,now)
  else:result=response(s,p,{'text':'先更新发球台定位，再重新比较两条路线。'},now)
 elif p.get('type')=='message' and awaiting:
  selected=choice(text)
  if s.get('session',{}).get('draft') and selected:
   result=response(s,p,{'text':'先确认或跳过当前记分，再选择开球路线。'},now)
  elif selected:
   if not a:result=response(s,p,{'text':'记下你倾向'+('保守' if selected=='conservative' else '进取')+'；先更新发球台定位，再确认这条路线。'},now)
   else:
    fresh=build_routes(s,a,now);saved=next(r for r in active['routes'] if r['kind']==selected);route=next((r for r in (fresh or []) if r['kind']==selected),None)
    if not route or any(route[k]!=saved[k] for k in ('club_key','zone_id','target')):
     result=offer(s,p,a,fresh,now) if fresh else response(s,p,{'text':'当前落区条件已变化，需要重新比较路线。'},now)
    else:
     picked={'key':route['club_key'],'label':route['club']};selected_offer=proposal(a,selected=picked)
     if p.get('_tee_geometry_v94'):
      from tee_strategy import suggest
      selected_offer=suggest(s,a,'保守' if selected=='conservative' else '进取',j.get('profile',{}).get('units',{}).get('value','码'),selected=picked,
                             mapped_fallback=True,par_five_plan=p.get('_par_five_v95',False),carry_crossing=p.get('_carry_crossing_v96',False),
                             compare_par_five=p.get('_par_five_compare_v97',False),ask_fairway_carry=p.get('_ask_fairway_carry_v98',False),
                             allow_roll_in=p.get('_par_five_roll_v102',False),compare_safety=p.get('_approach_risk_v104',False),compare_next_shot=p.get('_stroke_consistency_v111',False))
      if not selected_offer.get('options') or len(selected_offer['options'])>1:
       # Present the actual computed choice before asking for a commitment.
       # The main reducer owns missing Carry and two/three-on questions.
       from journey import _apply_journey as main
       adapted=copy.deepcopy(p);adapted['protocol_version']=39;adapted['text']=picked['label']
       j['consultation'].update(phase='tee_intent',player_intent='保守' if selected=='conservative' else '进取')
       active['status']='selected';active['selected']=selected
       result=main(s,adapted,seq,now)
       j.setdefault('tee_options_receipts',{})[p['event_id']]=sha
       return result
     require(bool(selected_offer['options']),'selected route unavailable')
     c=j['consultation'];c.update(phase='tee_commit',selected_club=picked,suggestion=selected_offer['options'][0],player_intent='保守' if selected=='conservative' else '进取',selection_report={'club':route['club'],'source':'user_report','event_id':p['event_id']})
     c['last_offer']=copy.deepcopy(selected_offer)
     active['status']='selected';active['selected']=selected;j.pop('distance_comparison_focus',None)
     wording=(selected_offer['text']+'就按这个打吗？') if p.get('_tee_geometry_v94') else f"好，按{'保守' if selected=='conservative' else '进取'}路线，用{route['club']}打向落区{route['target']}。就按这个打吗？"
     result=response(s,p,{'text':wording,'choices':['按这个打','再想想','自己打']},now,'plan.confirm')
  elif (assent(text) is not None or text in ('确认','按这个打','就按这个')) and j.get('response_context',{}).get('question_owner')=='tee.choice':
   result=response(s,p,{'text':'你想选保守方案还是进取方案？','choices':['保守方案','进取方案','自己打']},now,'tee.choice')
  elif text in ('继续刚才的问题','刚才问什么'):
   fresh=build_routes(s,a,now) if a else None
   result=offer(s,p,a,fresh,now) if fresh else response(s,p,{'text':'路线资料保留了，先更新发球台定位再继续比较。'},now)
  elif followup_query(text) is not None and not j.get('distance_comparison_focus'):
   if a:
    routes=build_routes(s,a,now)
    if routes:
     unit=j.get('profile',{}).get('units',{}).get('value','码');scale=.9144 if unit=='米' else 1
     msg='，'.join(('保守' if r['kind']=='conservative' else '进取')+'方案预计还剩约'+str(round(r['remaining_yards']*scale/5)*5)+unit for r in routes)+'；以实际落点为准。'
     result=response(s,p,{'text':msg},now)
 if result is None:
  from journey import reduce_journey as previous
  adapted=copy.deepcopy(p);adapted['protocol_version']=36;result=previous(s,adapted,seq,now)
  j=s['journey'];c=j.get('consultation') or {}
  from approach_dialogue import requested
  advice=isinstance(text,str) and (requested(text) or bool(re.search(r'有何建议|有什么建议|有啥建议|给点建议|推荐一下',text)))
  carry_reply=before.get('phase')=='tee_club' and not before.get('selected_club')
  if p.get('type')=='message' and (advice or carry_reply) and c.get('phase')=='tee_commit' and not c.get('selected_club') and not any(option.get('strategy')=='mapped_carry_candidate' for option in (c.get('last_offer') or {}).get('options',[])) and c.get('suggestion',{}).get('strategy')!='mapped_carry_candidate':
   a=analyze(s,now);routes=build_routes(s,a,now)
   if routes:
    brief=result.get('tee_brief_prefix')
    if brief:
     result=offer(s,p,a,routes,now,brief=brief)
    else:
     result=offer(s,p,a,routes,now)
  if not (j.get('consultation') or {}).get('phase','').startswith('tee_') or (j.get('consultation') or {}).get('selected_club'):
   if j.get('tee_route_options',{}).get('status')=='awaiting_choice':j['tee_route_options']['status']='superseded'
 s['journey'].setdefault('tee_options_receipts',{})[p['event_id']]=sha
 return result
