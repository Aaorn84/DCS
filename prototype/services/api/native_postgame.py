"""Postgame service context contains only server-derived compact score statistics."""
def reduce_postgame(state,payload,seq,now):
 from application import reduce_event
 state['journey']['native_history_comparison']=payload['history_summary']
 return reduce_event(state,payload['event'],seq,now)
