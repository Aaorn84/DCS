"""Field-level personal memory and score basis, independent of upload/core/map-envelope time."""
import hashlib,json,math,time
from datetime import datetime,timezone
from round_state import canonical

def timestamp(value,fallback=0):
 try:
  result=datetime.fromisoformat(value.replace('Z','+00:00')).timestamp() if isinstance(value,str) else float(value)
  return result if math.isfinite(result) and result<=time.time()+300 else fallback
 except (ValueError,TypeError,OverflowError):return fallback

def score_basis(course):
 from course_history_comparison import comparable_basis
 basis={str(h['number']):dict(par=h.get('par'),published_yardage=h.get('published_yardage')) for h in course.get('holes',[])}
 if not comparable_basis(basis):return None
 # 130 and 130.0 represent the same published length.
 normalized={k:{**v,'published_yardage':float(v['published_yardage'])} for k,v in basis.items()}
 return hashlib.sha256(canonical(normalized).encode()).hexdigest()

def provision_round_metadata(db):
 """Explicit schema upgrade only. Read immutable seeds; never alter user golf records."""
 cursor=('', '')
 while True:
  rows=db.execute("SELECT n.owner,n.round_id,l.package FROM native_rounds n JOIN offline_leases l ON l.owner=n.owner AND l.aggregate_id='native-'||n.round_id WHERE (n.started_at=0 OR n.score_basis IS NULL) AND (n.owner,n.round_id)>(%s,%s) ORDER BY n.owner,n.round_id LIMIT 100",cursor).fetchall()
  if not rows:break
  for owner,rid,raw in rows:
   pack=json.loads(raw)['package'];started=timestamp(pack['round'].get('started_at'))
   db.execute('UPDATE native_rounds SET started_at=%s,score_basis=%s WHERE owner=%s AND round_id=%s',(started,score_basis(pack['course']),owner,rid))
  cursor=rows[-1][:2]
 # Backfill only old completed contributions, bounded batches of lazy components.
 from state_components import Components
 from types import SimpleNamespace
 cursor=('', '')
 while True:
  rows=db.execute("SELECT n.owner,n.round_id,l.package,r.state FROM native_rounds n JOIN offline_leases l ON l.owner=n.owner AND l.aggregate_id='native-'||n.round_id JOIN rounds r ON r.owner=n.owner AND r.id=l.aggregate_id WHERE n.finished=TRUE AND n.memory_allowed=TRUE AND NOT EXISTS(SELECT 1 FROM native_profile_fields f WHERE f.owner=n.owner AND f.round_id=n.round_id) AND (n.owner,n.round_id)>(%s,%s) ORDER BY n.owner,n.round_id LIMIT 100",cursor).fetchall()
  if not rows:break
  for owner,rid,raw,saved in rows:
   components=Components(db,owner,('schema-upgrade',hashlib.sha256(db.info.dsn.encode()).hexdigest()));components.aggregate='native-'+rid
   state=components.decode(json.loads(saved));seed=json.loads(raw)['package']
   remember_finished(SimpleNamespace(owner=owner,db=db),state,seed,{'at':seed['round']['started_at']})
  cursor=rows[-1][:2]

def remember_finished(engine,state,seed,command):
 """Rebuild one round's small contribution on finish/undo, transactionally with the cursor."""
 j=state['journey'];model=j.get('offline_local_round') or {};rid=j['round']['id']
 engine.db.execute('DELETE FROM native_profile_fields WHERE owner=%s AND round_id=%s',(engine.owner,rid))
 if not model.get('finished') or j.get('memory_allowed') is not True:return
 from shared_core import call
 memory=call('profile_memory',profile=model['profile']);baseline=call('profile_memory',profile=seed.get('profile',{}))
 started=timestamp(seed['round'].get('started_at'));fallback=started
 events=None;records=[]
 for key,value in memory['fields'].items():
  clock=memory['clocks'].get(key) or {};at=timestamp(clock.get('at'),-1);order=clock.get('order',0)
  if at<0:
   at=timestamp((baseline['clocks'].get(key) or {}).get('at'),fallback)
   # Old releases have no clocks. Use original command time, never arrival time.
   if value!=baseline['fields'].get(key):
    kinds={'strategy_preference':'set_strategy_preference','fairway_finder':'set_fairway_finder','fairway_carry_status':'set_fairway_carry_status','strategy_usage':'record_stroke'}
    kind='set_club_carry' if key.startswith('bag:') or key in ('driver','three_wood','five_wood','hybrid','seven','iron3','iron4','pitching_wedge') else 'set_club_purpose' if key.startswith('purpose:') else kinds.get(key)
    if events is None:events=[e for _,e in model.get('receipts',{}).items()]
    relevant=[e for e in events if e.get('command')==kind]
    if relevant:
     last=max(relevant,key=lambda e:e['expected_revision']);at=timestamp(last.get('at'),fallback);order=last['expected_revision']+1
  order=order if type(order) is int and 0<=order<=2**31-1 else 0
  records.append((engine.owner,rid,key,canonical(value),at,order))
 if records:
  if hasattr(engine.db,'executemany'):engine.db.executemany('INSERT INTO native_profile_fields VALUES(%s,%s,%s,%s,%s,%s)',records)
  else:
   with engine.db.cursor() as cursor:cursor.executemany('INSERT INTO native_profile_fields VALUES(%s,%s,%s,%s,%s,%s)',records)

def merged_profile(engine,base=None):
 from shared_core import call
 memory=call('profile_memory',profile=base or {});fields=memory['fields'];clocks=memory['clocks']
 rows=engine.db.execute('SELECT DISTINCT ON(field) field,value,occurred_at,event_order,round_id FROM native_profile_fields WHERE owner=%s ORDER BY field,occurred_at DESC,event_order DESC,round_id DESC',(engine.owner,)).fetchall()
 for key,raw,at,order,rid in rows:
  previous=clocks.get(key);old=timestamp(previous.get('at'),-1) if previous else -1
  if old>at or old==at and previous.get('order',0)>order:continue
  fields[key]=json.loads(raw);clocks[key]={'at':datetime.fromtimestamp(at,timezone.utc).isoformat(),'round_id':rid,'order':order}
 return call('profile_from_facts',fields=fields,clocks=clocks)
