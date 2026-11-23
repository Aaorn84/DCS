"""Register independently created offline rounds without replacing another device's round."""
import hashlib,json,re,time,uuid
from datetime import datetime
from round_state import require,canonical,Conflict,initial
from shared_core import call,SUPPORTED_CORES
from state_components import materialize

def identity(body):
 rid=body.get('round_id')
 require(isinstance(rid,str) and re.fullmatch(r'[A-Za-z0-9_-]{8,90}',rid),'invalid offline round id')
 return rid

def register(engine,body):
 from offline_sync import device,public,row
 rid=identity(body);d=device(body.get('device_id'));require(body.get('core_version') in SUPPORTED_CORES,'shared core version mismatch')
 require(not set(body)-{'action','round_id','device_id','core_version','asset_sha256','context_sha256','setup','round','package_sha256'},'unknown registration field')
 require(body.get('round',{}).get('id')==rid,'offline round identity mismatch')
 raw=engine.db.execute('SELECT payload FROM course_packages WHERE digest=%s AND core_version=%s',(body.get('asset_sha256'),body.get('core_version'))).fetchone();require(raw,'downloaded course is not known to this server')
 asset=json.loads(raw[0])
 raw=engine.db.execute('SELECT payload FROM download_contexts WHERE owner=%s AND digest=%s AND asset_digest=%s',(engine.owner,body.get('context_sha256'),body.get('asset_sha256'))).fetchone();require(raw,'download context does not belong to this account or map')
 context=json.loads(raw[0]);wire=call('offline_package_wire',asset=asset,context=context,setup=body.get('setup'),round=body.get('round'));pack=wire['package']
 try:require(datetime.fromisoformat(pack['round']['started_at'].replace('Z','+00:00')).timestamp()<=time.time()+300,'offline start time is in the future')
 except (ValueError,TypeError):require(False,'invalid offline start time')
 payload=wire['payload_json'];digest=hashlib.sha256(payload.encode()).hexdigest();require(digest==body.get('package_sha256'),'offline round package mismatch')
 registration=hashlib.sha256(canonical({k:v for k,v in body.items() if k!='action'}).encode()).hexdigest()
 engine.aggregate_id='native-'+rid;engine.db.begin()
 try:
  old=engine.db.execute('SELECT device_id,registration_digest FROM native_rounds WHERE owner=%s AND round_id=%s',(engine.owner,rid)).fetchone()
  if old:
   if old!=(d,registration):raise Conflict('offline round identity is already registered with different data')
   reply=public(row(engine));engine.db.execute('COMMIT');return dict(offline=reply)
  engine.create(engine.aggregate_id);state=initial()
  state['journey']=dict(stage='ready',profile=pack['profile'],round=pack['round'],quiet=False,memory_allowed=body['setup']['memory_allowed'],history=[],number=1,coach={'enabled':False,'plan':None})
  from course_install import install
  install(state,pack['course'],'native-register',pack['round']['started_at'],0)
  engine.components.aggregate=engine.aggregate_id
  engine.db.execute('UPDATE rounds SET state=%s WHERE owner=%s AND id=%s',(canonical(engine.components.encode(state)),engine.owner,engine.aggregate_id))
  envelope=canonical(dict(package=pack,payload_json=payload,sha256=digest,source_version=0))
  # Server assigns identity only on synchronization; local play never waits for this.
  lease=uuid.uuid4().hex
  engine.db.execute('INSERT INTO offline_leases VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(engine.owner,engine.aggregate_id,lease,rid,d,envelope,digest,0,0,time.time(),'active'))
  engine.db.execute('INSERT INTO native_rounds(owner,round_id,device_id,asset_digest,package_digest,registration_digest,course_id,tee,memory_allowed,finished,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(engine.owner,rid,d,body['asset_sha256'],digest,registration,pack['round']['course'],pack['round']['tee'],body['setup']['memory_allowed'],False,time.time()))
  from native_profile import score_basis,timestamp
  engine.db.execute('UPDATE native_rounds SET started_at=%s,score_basis=%s WHERE owner=%s AND round_id=%s',(timestamp(pack['round']['started_at']),score_basis(pack['course']),engine.owner,rid))
  reply=public(row(engine));engine.db.execute('COMMIT');return dict(offline=reply)
 except Exception:
  if engine.db.in_transaction:engine.db.execute('ROLLBACK')
  raise

def handle(engine,body):
 from offline_sync import require_owner,synchronize,release,local_status,public
 rid=identity(body);engine.aggregate_id='native-'+rid;engine.native_round=True
 def update(state,command):
  model=state.get('journey',{}).get('offline_local_round') or {};scores=[h['score'] for h in model.get('holes',{}).values() if h.get('score')]
  from native_profile import remember_finished,timestamp
  finished_at=timestamp(command['at']) if model.get('finished') else None
  engine.db.execute('UPDATE native_rounds SET finished=%s,total=%s,confirmed_holes=%s,updated_at=%s,finished_at=%s WHERE owner=%s AND round_id=%s',(bool(model.get('finished')),sum(s['total'] for s in scores),len(scores),time.time(),finished_at,engine.owner,rid))
  if model.get('finished') or command['command']=='undo':
   from offline_sync import row
   seed=json.loads(row(engine,include_package=True)['package'])['package'];remember_finished(engine,state,seed,command)
 engine.offline_commit=update
 action=body.get('action')
 if action=='register':return register(engine,body)
 require(engine.db.execute('SELECT 1 FROM native_rounds WHERE owner=%s AND round_id=%s',(engine.owner,rid)).fetchone(),'offline round not registered for this account')
 if action=='status':return dict(offline=public(require_owner(engine,body)),local_status=local_status(engine))
 if action=='sync':return synchronize(engine,body)
 if action=='release':
  lease=require_owner(engine,body)
  if lease['status']=='released':
   require(engine.state(engine.aggregate_id,lazy=True).get('journey',{}).get('offline_local_round',{}).get('finished'),'本场尚未结束，请恢复记录权后继续打球')
   require(body.get('cursor')==lease['cursor'],'release cursor mismatch');return {'offline':public(lease)}
  return release(engine,body)
 if action=='resume_recording':
  engine.db.begin()
  try:
   lease=require_owner(engine,body);state=engine.state(engine.aggregate_id,lazy=True);model=state.get('journey',{}).get('offline_local_round')
   require(lease['status'] in ('released','active') and model and not model.get('finished') and not model.get('pending') and not model.get('draft'),'本场无需恢复记录权')
   require(body.get('cursor')==lease['cursor'] and state['version']==lease['base_version']+lease['cursor'],'恢复进度不一致，请保留记录')
   engine.db.execute("UPDATE offline_leases SET status='active' WHERE owner=%s AND aggregate_id=%s",(engine.owner,engine.aggregate_id));answer=public(require_owner(engine,body));engine.db.execute('COMMIT');return dict(offline=answer)
  except Exception:
   if engine.db.in_transaction:engine.db.execute('ROLLBACK')
   raise
 if action=='event':
  lease=require_owner(engine,body);state=engine.state(engine.aggregate_id,lazy=True)
  require(lease['status']=='released' and state.get('journey',{}).get('offline_local_round',{}).get('finished'),'finish and synchronize this round before postgame conversation')
  expected=body.get('expected_version');require(expected is None or type(expected) is int and 0<=expected<=2**31-1,'invalid postgame version')
  event=body.get('event');require(isinstance(event,dict) and event.get('type') in ('message','resume'),'only postgame messages are supported')
  previous=engine.db.execute('SELECT kind,payload FROM commands WHERE owner=%s AND round_id=%s AND command_id=%s',(engine.owner,engine.aggregate_id,body.get('operation_id'))).fetchone()
  payload=json.loads(previous[1]) if previous else {'event':event,'history_summary':history_summary(engine,rid)}
  require(not previous or previous[0]=='native_postgame_event' and payload['event']==event,'postgame idempotency key reused')
  def remember_consent(current,result):
   allowed=current.get('journey',{}).get('memory_allowed') is True
   engine.db.execute('UPDATE native_rounds SET memory_allowed=%s WHERE owner=%s AND round_id=%s',(allowed,engine.owner,rid))
   if not allowed:engine.db.execute('DELETE FROM native_profile_fields WHERE owner=%s AND round_id=%s',(engine.owner,rid))
  result=engine.command(engine.aggregate_id,body.get('operation_id'),'native_postgame_event',payload,expected_version=body.get('expected_version'),on_commit=remember_consent)
  from round_view import view
  current=engine.response_state(engine.aggregate_id)
  if current['version']!=result['version']:result=dict(result,text='',speak_allowed=False,stale_receipt=True)
  return {'result':result,'journey':materialize(view(current))}
 if action=='snapshot':
  require_owner(engine,body)
  from round_view import view
  return dict(journey=materialize(view(engine.state(engine.aggregate_id,lazy=True))))
 require(False,'unknown offline round action')


def history_summary(engine,rid):
 row=engine.db.execute('SELECT course_id,tee,score_basis FROM native_rounds WHERE owner=%s AND round_id=%s',(engine.owner,rid)).fetchone()
 course,tee,basis_key=row
 counts=engine.db.execute('SELECT count(*),count(*) FILTER (WHERE tee=%s AND score_basis=%s AND confirmed_holes=18),min(total) FILTER (WHERE tee=%s AND score_basis=%s AND confirmed_holes=18),sum(total) FILTER (WHERE tee=%s AND score_basis=%s AND confirmed_holes=18) FROM native_rounds WHERE owner=%s AND course_id=%s AND round_id<>%s AND finished=TRUE AND memory_allowed=TRUE',(tee,basis_key,tee,basis_key,tee,basis_key,engine.owner,course,rid)).fetchone()
 result=dict(prior=counts[0],count=counts[1],best=counts[2],sum=counts[3] or 0)
 existing=engine.db.execute('SELECT 1 FROM rounds WHERE owner=%s AND id=%s',(engine.owner,'companion-journey')).fetchone()
 if existing:
  from course_history_comparison import complete_total,basis,tee as normalize_tee,comparable_basis
  current_basis=basis(engine.state(engine.aggregate_id,lazy=True));web=engine.state('companion-journey',lazy=True).get('journey',{})
  if web.get('memory_allowed') is True:
   for entry in web.get('history',[]):
    old=entry.get('round',{})
    if old.get('course')!=course or old.get('finished') is not True or old.get('id')==rid:continue
    result['prior']+=1;total=complete_total(entry.get('scores',[]));stored=entry.get('course_basis')
    if total is None or normalize_tee(old.get('tee'))!=normalize_tee(tee) or not isinstance(stored,list) or len(stored)!=1 or not comparable_basis(current_basis) or stored[0]!=current_basis:continue
    result['count']+=1;result['sum']+=total;result['best']=total if result['best'] is None else min(result['best'],total)
 return result
