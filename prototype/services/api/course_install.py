"""Install the authenticated pinned course without executing an old session event."""
import copy
from round_state import require

def install(state,course,event_id,observed_at,seq):
 require(isinstance(course,dict) and course.get('course_id') and course.get('map_version') and course.get('crs')=='WGS84','invalid pinned map')
 eid=event_id+'-course'
 state['evidence'][eid]=dict(id=eid,source='course',revision=1,phase='final',observed_at=observed_at,data=copy.deepcopy(course))
 state['facts']['context.course_snapshot']=dict(value=eid,valid=True,status='confirmed',version=seq,evidence_ids=[eid])
 return eid
