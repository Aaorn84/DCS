"""Account-authenticated advance downloads; public map bytes are immutable and shared."""
import hashlib,time
from datetime import datetime
from functools import lru_cache
from round_state import require,canonical
from shared_core import CORE_VERSION,CORE_DATASET
from state_components import materialize

@lru_cache(maxsize=4)
def asset(course_id):
 from phoenix_demo import ID,course
 require(course_id==ID,'course is not available for download')
 from offline_package import prepare_course
 payload=dict(schema=1,core_version=CORE_VERSION,dataset=CORE_DATASET,course=prepare_course(course()),tees=['蓝Tee'])
 raw=canonical(payload);return dict(package=payload,payload_json=raw,sha256=hashlib.sha256(raw.encode()).hexdigest())

def catalog():
 from phoenix_demo import ID
 return [dict(course_id=ID,name='东莞凤凰山 A+B（来源坐标演示）',tees=['蓝Tee'],holes=18,reference_simulation=True)]

def private_context(engine,course_id,tee,course):
 profile={};dispersion={};history=[];profile_time=0
 existing=engine.db.execute('SELECT 1 FROM rounds WHERE owner=%s AND id=%s',(engine.owner,'companion-journey')).fetchone()
 if existing:
  state=engine.state('companion-journey',lazy=True);j=state.get('journey',{})
  if j.get('memory_allowed') is True:
   profile=materialize(j.get('profile',{}));dispersion=materialize(j.get('tee_dispersion_summary',{}))
   recent_command=engine.db.execute('SELECT at FROM commands WHERE owner=%s AND round_id=%s ORDER BY seq DESC LIMIT 1',(engine.owner,'companion-journey')).fetchone()
   profile_time=recent_command[0] if recent_command else 0
   for v in reversed(j.get('history',[])):
    old=v.get('round',{})
    if old.get('finished') and old.get('course')==course_id and old.get('tee') in (tee,tee.replace('Tee','台')):history.append(v)
    if len(history)>=5:break
 rows=engine.db.execute('SELECT round_id FROM native_rounds WHERE owner=%s AND course_id=%s AND tee=%s AND memory_allowed=TRUE AND finished=TRUE ORDER BY started_at DESC,round_id DESC LIMIT 5',(engine.owner,course_id,tee)).fetchall()
 # Personal strategy is account-wide; course-local history is a separate bounded input.
 latest=engine.db.execute('SELECT round_id,started_at FROM native_rounds WHERE owner=%s AND memory_allowed=TRUE AND finished=TRUE ORDER BY started_at DESC,round_id DESC LIMIT 1',(engine.owner,)).fetchone()
 if latest and latest[1]>=profile_time:
  personal=engine.state('native-'+latest[0],lazy=True).get('journey',{})
  profile=materialize(personal.get('profile',{}));dispersion=materialize(personal.get('tee_dispersion_summary',{}))
 from native_profile import merged_profile
 profile=merged_profile(engine,profile)
 for (rid,) in rows:
  state=engine.state('native-'+rid,lazy=True);j=state['journey']
  history.extend([v for v in j.get('history',[]) if v.get('round',{}).get('id')==rid and v.get('round',{}).get('finished')])
 # Exactly five rounds are considered across sources; maps/signatures still filter each hole.
 def finished_at(entry):
  value=entry.get('round',{}).get('finished_at') or entry.get('round',{}).get('started_at')
  try:return datetime.fromisoformat(value.replace('Z','+00:00')).timestamp() if isinstance(value,str) else 0
  except (ValueError,TypeError):return 0
 history.sort(key=finished_at,reverse=True)
 seen=set();bounded=[]
 for row in history:
  rid=row.get('round',{}).get('id')
  if rid and rid not in seen:bounded.append(row);seen.add(rid)
  if len(bounded)==5:break
 state=dict(facts={'context.course_snapshot':{'value':'download-map'}},evidence={'download-map':{'data':course}},journey={'round':{'id':'future-round','course':course_id,'tee':tee},'profile':profile,'history':list(reversed(bounded)),'memory_allowed':True})
 from hole_history import records
 result=dict(profile=profile,dispersion=dispersion,history_by_hole={str(h['number']):records(state,h['number'])[:500] for h in course['holes']})
 return result

def download(engine,course_id,tee,include_personal=False):
 published=asset(course_id);require(tee in published['package']['tees'],'Tee unavailable')
 require(type(include_personal) is bool,'invalid personal context preference')
 context=private_context(engine,course_id,tee,published['package']['course']) if include_personal else dict(profile={},dispersion={},history_by_hole={})
 context['asset_sha256']=published['sha256'];raw=canonical(context);digest=hashlib.sha256(raw.encode()).hexdigest();now=time.time()
 engine.db.execute('INSERT INTO course_packages VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(published['sha256'],course_id,CORE_VERSION,published['payload_json'],now))
 engine.db.execute('INSERT INTO download_contexts VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',(engine.owner,digest,published['sha256'],raw,now))
 return dict(asset=published,context=dict(payload_json=raw,sha256=digest))
