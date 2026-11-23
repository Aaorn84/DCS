"""Pinned per-round single-writer leases and atomic event/cursor commits.
Only versioned shared-core commands are accepted; no free-text replay mode.
"""
import json,re,time,uuid
from datetime import datetime
from round_state import canonical,Conflict,StateError,require
from offline_package import build
AGGREGATE='companion-journey'

def aggregate(engine):return getattr(engine,'aggregate_id',AGGREGATE)

def setup(engine):
 from database import ensure_schema
 ensure_schema(engine.db)

def device(value):
 require(isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_-]{8,100}',value),'invalid device id');return value

def row(engine,include_package=False):
 setup(engine)
 package_column='package' if include_package else 'NULL'
 r=engine.db.execute('SELECT lease_id,round_id,device_id,'+package_column+',digest,base_version,cursor,last_at,status FROM offline_leases WHERE owner=%s AND aggregate_id=%s',(engine.owner,aggregate(engine))).fetchone()
 return dict(zip(('lease_id','round_id','device_id','package','sha256','base_version','cursor','last_at','status'),r)) if r else None

def public(r):return {k:r[k] for k in ('lease_id','round_id','device_id','sha256','base_version','cursor','status')}

def require_owner(engine,body):
 r=row(engine)
 if not r or r['lease_id']!=body.get('lease_id') or r['device_id']!=device(body.get('device_id')):raise Conflict('offline lease belongs to another device or round')
 return r

def online_guard(engine,state):
 r=row(engine)
 if r and r['status']=='active':raise Conflict('本场已由离线设备接管，请在该设备同步并结束离线记录后再在线修改。')

def prepare(engine,body):
 if 'two_phase' in body:require(type(body['two_phase']) is bool,'invalid two-phase preparation flag')
 require(type(body.get('local_engine_version')) is int and body['local_engine_version']==1,'typed local rules version required')
 from shared_core import CORE_VERSION
 require(body.get('core_version')==CORE_VERSION,'shared core version mismatch')
 d=device(body.get('device_id'));setup(engine);engine.db.begin()
 try:
  old=row(engine,include_package=True)
  if old and old['status'] in ('preparing','active'):
   if old['device_id']!=d:raise Conflict('本场已由另一台设备记录')
   model=engine.state(aggregate(engine),lazy=True).get('journey',{}).get('offline_local_round')
   from state_components import materialize
   model=materialize(model) if model and model.get('round_id')==old['round_id'] else None
   engine.db.execute('COMMIT');return dict(offline=public(old),offline_package=json.loads(old['package']),offline_state=model)
  s=engine.state(aggregate(engine),lazy=True);j=s.get('journey',{});r=j.get('round') or {}
  require(j.get('stage') in ('ready','active') and r.get('id') and not r.get('finished'),'请先选择球场和发球台，再准备离线球局')
  require(type(body.get('expected_version')) is int and body['expected_version']==s['version'],'球局版本已变化，请刷新后准备离线包')
  require(j.get('stage')=='ready','本地规则模式目前需从开局前准备，不能接管已开始的球局')
  package=build(s);require(package['package'].get('course'),'当前球场没有可下载地图')
  require(r.get('tee'),'请先确认本场发球台')
  holes=package['package']['course'].get('holes',[])
  require(len(holes)==18 and {h.get('number') for h in holes}==set(range(1,19)),'离线准备需要完整18洞球场资料')
  model=j.get('offline_local_round')
  require(not model or model.get('round_id')!=r['id'],'本场已有本地规则记录，结束离线接管后请继续在线使用，或新建球局再准备离线')
  from shared_core import create_local_round
  create_local_round(package['package'])
  at=time.time();lease=uuid.uuid4().hex
  engine.db.execute('INSERT INTO offline_leases VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(owner,aggregate_id) DO UPDATE SET lease_id=excluded.lease_id,round_id=excluded.round_id,device_id=excluded.device_id,package=excluded.package,digest=excluded.digest,base_version=excluded.base_version,cursor=excluded.cursor,last_at=excluded.last_at,status=excluded.status',(engine.owner,aggregate(engine),lease,r['id'],d,canonical(package),package['sha256'],s['version'],0,at-300,'preparing' if body.get('two_phase') is True else 'active'))
  answer=row(engine);engine.db.execute('COMMIT');return dict(offline=public(answer),offline_package=package,offline_state=None)
 except Exception:
  engine.db.execute('ROLLBACK');raise

def validate_event(event):
 require(isinstance(event,dict),'event must be an object')
 allowed={'type','event_id','observed_at','text','data'}
 require(not set(event)-allowed,'offline event contains control fields')
 require(event.get('type')=='local_round_command','typed local command required')
 require(isinstance(event.get('event_id'),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}',event['event_id']),'invalid offline event id')
 if event['type']=='local_round_command':
  command=event.get('data');require(isinstance(command,dict) and command.get('id')==event['event_id'] and command.get('at')==event['observed_at'],'local command identity mismatch')
  require(not set(command)-{'v','semantics','id','at','expected_revision','command','data'},'local command contains control fields')
 try:
  dt=datetime.fromisoformat(event['observed_at'].replace('Z','+00:00'))
  require(dt.tzinfo is not None,'offline timestamp needs timezone');at=dt.timestamp()
 except (ValueError,TypeError,KeyError,AttributeError):raise StateError('invalid offline timestamp')
 require(at<=time.time()+300,'offline timestamp is in the future')
 return at

def synchronize(engine,body):
 lease=require_owner(engine,body)
 require(body.get('sha256')==lease['sha256'],'offline package checksum mismatch')
 events=body.get('events');require(isinstance(events,list) and len(events)<=100,'offline batches are limited to 100 events')
 pinned=json.loads(row(engine,include_package=True)['package'])
 require(pinned['package'].get('local_rules_version')==1,'typed local package required')
 prepared=[]
 for entry in events:
  require(isinstance(entry,dict) and type(entry.get('seq')) is int and entry['seq']>0,'invalid offline event sequence')
  prepared.append((entry['seq'],entry.get('event'),validate_event(entry.get('event'))))
 require(all(prepared[i][0]+1==prepared[i+1][0] for i in range(len(prepared)-1)),'offline batch must be contiguous')
 accepted=[]
 for seq,event,at in prepared:
  command='offline_'+lease['lease_id']+'_'+str(seq)
  def guard(state):
   current=require_owner(engine,body)
   if current['status']!='active' or current['cursor']+1!=seq:raise Conflict('offline event sequence gap or released lease')
   if (state.get('journey',{}).get('round') or {}).get('id')!=current['round_id']:raise Conflict('offline round has changed')
  def commit(state,result):
   require((state.get('journey',{}).get('round') or {}).get('id')==lease['round_id'],'offline batch cannot start a different round')
   engine.db.execute('UPDATE offline_leases SET cursor=%s,last_at=CASE WHEN last_at>%s THEN last_at ELSE %s END WHERE owner=%s AND aggregate_id=%s',(seq,at,at,engine.owner,aggregate(engine)))
   hook=getattr(engine,'offline_commit',None)
   if hook:hook(state,event['data'])
  payload={'command':event['data']}
  if seq==1:
   payload['seed']={k:pinned['package'][k] for k in ('schema','round','course','profile','core_version') if k in pinned['package']}
  result=engine.command(aggregate(engine),command,'offline_rules_event',payload,expected_version=lease['base_version']+seq-1,now=at,guard=guard,on_commit=commit)
  accepted.append(dict(seq=seq,event_id=event['event_id'],version=result['version']))
 return dict(accepted=accepted,offline=public(require_owner(engine,body)),local_status=local_status(engine))

def release(engine,body):
 engine.db.begin()
 try:
  r=require_owner(engine,body)
  if body.get('cursor')!=r['cursor']:raise Conflict('请先同步全部本地事件，再结束离线记录')
  s=engine.state(aggregate(engine),lazy=True)
  model=s.get('journey',{}).get('offline_local_round')
  if getattr(engine,'native_round',False):require(model and model.get('finished'),'请先确认结束本场球局；进行中请使用普通同步')
  if model and model.get('round_id')==r['round_id'] and (model.get('pending') or model.get('draft')):raise Conflict('请先完成当前球的处理或确认成绩，再结束离线记录')
  if s['version']!=r['base_version']+r['cursor']:raise Conflict('球局存在未核对的版本冲突')
  engine.db.execute("UPDATE offline_leases SET status='released' WHERE owner=%s AND aggregate_id=%s",(engine.owner,aggregate(engine)));answer=public(require_owner(engine,body));engine.db.execute('COMMIT');return dict(offline=answer)
 except Exception:
  engine.db.execute('ROLLBACK');raise

def local_status(engine):
 state=engine.state(aggregate(engine),lazy=True);j=state.get('journey',{});model=j.get('offline_local_round')
 if not model or model.get('round_id')!=(j.get('round') or {}).get('id'):
  r=row(engine,include_package=True)
  if not r or r['cursor']!=0:return None
  pack=json.loads(r['package'])['package']
  if pack.get('local_rules_version')!=1:return None
  from shared_core import create_local_round
  model=create_local_round(pack)
 from shared_core import totals
 return dict(revision=model['revision'],hole=model['hole'],stage=model['stage'],totals=totals(model),pending=(model.get('pending') or {}).get('phase'),draft=bool(model.get('draft')))

def status(engine,body):
 return dict(offline=public(require_owner(engine,body)),local_status=local_status(engine))

def activate(engine,body):
 engine.db.begin()
 try:
  r=require_owner(engine,body)
  require(body.get('sha256')==r['sha256'],'offline package checksum mismatch')
  if r['status']=='active':
   engine.db.execute('COMMIT');return dict(offline=public(r))
  if r['status']!='preparing' or r['cursor']!=0:raise Conflict('离线准备已结束，请重新准备')
  state=engine.state(aggregate(engine),lazy=True)
  if state['version']!=r['base_version'] or (state.get('journey',{}).get('round') or {}).get('id')!=r['round_id']:raise Conflict('准备期间球局已变化，请取消准备并刷新后重试')
  engine.db.execute("UPDATE offline_leases SET status='active' WHERE owner=%s AND aggregate_id=%s",(engine.owner,aggregate(engine)))
  answer=public(require_owner(engine,body));engine.db.execute('COMMIT');return dict(offline=answer)
 except Exception:
  engine.db.execute('ROLLBACK');raise

def cancel_preparation(engine,body):
 setup(engine);engine.db.begin()
 try:
  r=row(engine)
  if r and r['status']=='released' and body.get('lease_id') is None:
   engine.db.execute('COMMIT');return dict(offline=None)
  if r:
   if r['device_id']!=device(body.get('device_id')) or body.get('lease_id') not in (None,r['lease_id']):raise Conflict('不能取消其他设备的离线准备')
   if r['cursor']!=0:raise Conflict('已有已同步记录，不能作为未开始的准备取消')
   if r['status'] not in ('preparing','active','cancelled'):raise Conflict('该离线记录已经结束')
   engine.db.execute("UPDATE offline_leases SET status='cancelled' WHERE owner=%s AND aggregate_id=%s",(engine.owner,aggregate(engine)));r=row(engine)
  engine.db.execute('COMMIT');return dict(offline=public(r) if r else None)
 except Exception:
  engine.db.execute('ROLLBACK');raise
