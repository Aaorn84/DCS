"""Resolve the selected map before the online 'start' command installs evidence."""
from round_state import fact_value

def selected_course(state):
 eid=fact_value(state,'context.course_snapshot');data=state.get('evidence',{}).get(eid,{}).get('data')
 selected=(state.get('journey',{}).get('round') or {}).get('course')
 if selected=='dongguan-phoenix-ab-blue-demo':
  if data and data.get('course_id')==selected:return data
  from phoenix_demo import course
  return course()
 return data
