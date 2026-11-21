"""Explicit single-hole test reset, retained as a replayable admin event."""
import json
from round_state import canonical
from shot_links import scope

def clear(state):
 j=state['journey'];key=list(scope(state));hole=key[2]
 def matches(row):
  if not isinstance(row,dict):return False
  if 'scope' in row:return row['scope']==key
  if 'round_scope' in row:return row['round_scope']==key
  return row.get('hole')==hole and row.get('round_id',key[0])==key[0]
 for name in ('confirmed_shot_distances','player_decisions','provisional_strokes','execution_reports','rejected_shot_links','deferred_shot_links','ball_outcome_history'):
  if isinstance(j.get(name),list):j[name]=[row for row in j[name] if not matches(row)]
 j['shot_location_candidates']=[row for row in j.get('shot_location_candidates',[]) if [row['round_id'],row['course'],row['hole']]!=key]
 for name in ('ball_rules','pin_locations','ball_outcomes','previous_club_reports','previous_club_asked','tee_announced'):
  values=j.get(name)
  if not isinstance(values,dict):continue
  for k in list(values):
   try:parts=json.loads(k)
   except (ValueError,TypeError):continue
   if isinstance(parts,list) and parts[:3]==key:values.pop(k,None)
 for name in ('consultation','last_consultation','pending_previous_club','pending_shot_link','last_short_game_advice','short_game_question','reported_landing','landing_observation','response_context','tee_club_fallback','simulated_club_choice','approach_club_offer','pending_green_followup','last_pending_prompt','shot_audio'):
  j.pop(name,None)
 for path in list(state.get('facts',{})):
  if path.startswith(f'holes.{hole}.'):state['facts'].pop(path)
 session=state.get('session',{})
 session['gps_prompted_holes']=[n for n in session.get('gps_prompted_holes',[]) if n!=hole]
 for marker in list(session.get('gps_score_prompt_attempts',{})):
  try:parts=json.loads(marker)
  except (ValueError,TypeError):continue
  if parts[:3]==key:session['gps_score_prompt_attempts'].pop(marker,None)
 if (session.get('draft') or {}).get('hole')==hole:
  session.update(draft=None,pending_patch=None,question_id=None)
 for question in state.get('questions',{}).values():
  if str(question.get('target','')).startswith(f'holes.{hole}') and question.get('status')=='pending':question['status']='closed'
 for patch in state.get('patches',{}).values():
  if any(op.get('path','').startswith(f'holes.{hole}.') for op in patch.get('operations',[])):patch['status']='invalidated'
 chain=state.get('shot_chain',{})
 for sid,shot in list(chain.get('shots',{}).items()):
  if shot.get('hole')==hole:
   chain['shots'].pop(sid)
   for nid in shot.get('slots',{}).values():chain.get('nodes',{}).pop(nid,None)
