"""Explicit local PostgreSQL cluster. Private config and data stay in ignored .runtime.
No legacy migration, no automatic account/data deletion on subsequent starts.
"""
import argparse,fcntl,hashlib,json,os,secrets,shutil,subprocess,sys,tempfile,time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[2];RUNTIME=ROOT/'.runtime'
SOCKET=Path('/tmp')/('caddie-pg-'+str(os.getuid())+'-'+hashlib.sha256(str(ROOT).encode()).hexdigest()[:12])
def prepare_imports():
 sys.path.insert(0,str(RUNTIME/'python'));sys.path.insert(0,str(ROOT/'prototype/services/api'))
def binaries():
 configured=os.environ.get('CADDIE_PG_BIN')
 bundled=RUNTIME/'python/pgserver/pginstall/bin'
 if configured:return Path(configured)
 if bundled.is_dir():return bundled
 found=shutil.which('pg_ctl')
 if found:return Path(found).parent
 raise RuntimeError('PostgreSQL client/server tools required; set CADDIE_PG_BIN')
def run(args,**kw):return subprocess.run([str(x) for x in args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,**kw)
@contextmanager
def cluster_lock(timeout=30):
 RUNTIME.mkdir(mode=0o700,exist_ok=True);RUNTIME.chmod(0o700)
 fd=os.open(RUNTIME/'postgres.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
 try:
  deadline=time.monotonic()+timeout
  while True:
   try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
   except BlockingIOError:
    if time.monotonic()>=deadline:raise RuntimeError('Local PostgreSQL initialization is busy; retry later')
    time.sleep(.05)
  yield
 finally:
  # Closing the descriptor releases the lock even after interruption or failure.
  os.close(fd)
def save_config(settings):
 fd,temp=tempfile.mkstemp(dir=RUNTIME,prefix='.postgres-')
 try:
  with os.fdopen(fd,'w') as output:
   json.dump(settings,output);output.flush();os.fsync(output.fileno())
  os.replace(temp,RUNTIME/'postgres.json')
  directory=os.open(RUNTIME,os.O_RDONLY|os.O_DIRECTORY)
  try:os.fsync(directory)
  finally:os.close(directory)
 finally:Path(temp).unlink(missing_ok=True)
def config():
 path=RUNTIME/'postgres.json'
 if path.is_symlink():raise RuntimeError('unsafe PostgreSQL config path')
 try:return json.loads(path.read_text())
 except (ValueError,OSError) as exc:raise RuntimeError('PostgreSQL config cannot be read; preserve data and inspect it') from exc
def start(port=55432):
 prepare_imports()
 with cluster_lock():return _start_locked(port)
def _start_locked(port):
 import psycopg
 from psycopg import sql
 from database import bootstrap_schema
 data=RUNTIME/'postgres';pg=binaries();settings_file=RUNTIME/'postgres.json'
 if not settings_file.exists():
  if data.exists():raise RuntimeError('unmanaged PostgreSQL data exists; refusing to overwrite')
  settings={'port':port,'app_password':secrets.token_urlsafe(32)}
  save_config(settings)
 settings=config();port=settings['port']
 if not (data/'PG_VERSION').exists():run([pg/'initdb','-D',data,'-U','postgres','--encoding=UTF8','--locale=C','--auth-local=trust','--auth-host=scram-sha-256'])
 status=subprocess.run([str(pg/'pg_ctl'),'-D',str(data),'status'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 if status.returncode:
  socket=SOCKET
  if socket.is_symlink():raise RuntimeError('unsafe local socket directory')
  socket.mkdir(mode=0o700,exist_ok=True)
  if socket.stat().st_uid!=os.getuid():raise RuntimeError('local socket owner mismatch')
  socket.chmod(0o700)
  run([pg/'pg_ctl','-D',data,'-l',RUNTIME/'postgres.log','-o',f'-h 127.0.0.1 -p {port} -k "{socket}"','-w','start'])
 admin=f'postgresql://postgres@/postgres?host={quote(str(SOCKET),safe="")}&port={port}'
 # Provision only once. Existing accounts and rounds are never changed on restart.
 if not settings.get('initialized'):
  with psycopg.connect(admin,autocommit=True) as db:
   if not db.execute("SELECT 1 FROM pg_roles WHERE rolname='caddie_app'").fetchone():
    db.execute(sql.SQL('CREATE ROLE caddie_app LOGIN PASSWORD {}').format(sql.Literal(settings['app_password'])))
   for name in ('caddie','caddie_test'):
    if not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
  application_admin=admin.replace('/postgres?','/caddie?');bootstrap_schema(application_admin)
  with psycopg.connect(application_admin,autocommit=True) as db:
   db.execute('GRANT USAGE ON SCHEMA public TO caddie_app')
   db.execute('GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO caddie_app')
  settings['initialized']=True
  save_config(settings)
 url=f'postgresql://caddie_app:{settings["app_password"]}@127.0.0.1:{port}/caddie'
 return {'application_url':url,'test_url':admin.replace('/postgres?','/caddie_test?'),'port':port}
def stop():
 with cluster_lock():
  pg=binaries();data=RUNTIME/'postgres'
  run([pg/'pg_ctl','-D',data,'-m','fast','-w','stop'])
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('action',choices=['start','stop']);parser.add_argument('--port',type=int,default=55432);args=parser.parse_args()
 if args.action=='start':print('Local PostgreSQL ready on 127.0.0.1:'+str(start(args.port)['port']))
 else:stop();print('Local PostgreSQL stopped')
