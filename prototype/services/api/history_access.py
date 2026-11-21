"""Compact history metadata and explicit owner-local per-hole detail reads."""
import copy

def page(state,offset=0,limit=20):
 history=state.get('journey',{}).get('history',[]);entries=list(reversed(history))
 rows=[]
 for entry in entries[offset:offset+limit]:
  rows.append({key:copy.deepcopy(entry[key]) for key in ('round','confirmed_holes','confirmed_subtotal','putt_opportunities','three_putts') if key in entry})
 return dict(rounds=rows,total=len(entries),offset=offset,has_more=offset+len(rows)<len(entries))

def hole(state,round_id,number):
 from round_state import require
 from state_components import materialize
 entry=next((v for v in reversed(state.get('journey',{}).get('history',[])) if v.get('round',{}).get('id')==round_id),None)
 require(entry is not None,'本账号没有这场历史球局')
 score=next((r for r in entry.get('scores',[]) if r.get('hole')==number),None)
 archived=entry.get('hole_history',{}).get(str(number))
 if archived is None and entry.get('round',{}).get('id')==(state.get('journey',{}).get('round') or {}).get('id'):
  from round_state import fact_value
  from hole_history import _archive
  eid=fact_value(state,'context.course_snapshot');course=state.get('evidence',{}).get(eid,{}).get('data',{})
  archived=_archive(state,round_id,eid,course,only_hole=number).get(str(number))
 return materialize(dict(round=entry['round'],hole=number,score=score,shots=archived.get('shots',[]) if archived else [],has_shot_archive=bool(archived)))
