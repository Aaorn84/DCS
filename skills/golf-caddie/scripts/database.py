"""PostgreSQL-only DB boundary: bounded pools and authenticated-owner transactions."""
import atexit,hashlib,os,threading
from pathlib import Path
import psycopg
from psycopg.rows import dict_row,tuple_row
from psycopg_pool import ConnectionPool,PoolTimeout,TooManyRequests

from runtime_control import CapacityError,integer
_POOLS={};_LOCK=threading.RLock();_SCHEMAS=set();SCHEMA_VERSION=3
TABLES=('users','sessions','records','operations','rounds','receipt_buckets','state_receipts','state_components','commands','offline_leases','course_packages','download_contexts','native_rounds','native_profile_fields')

def postgres(url):return isinstance(url,str) and url.startswith(('postgresql://','postgres://'))
def require_url(url=None):
 value=url or os.environ.get('CADDIE_DATABASE_URL','')
 if not postgres(value):raise ValueError('PostgreSQL URL required; configure CADDIE_DATABASE_URL')
 return value

def integrity_errors():return (psycopg.IntegrityError,)
def pool(url):
 url=require_url(url);key=(os.getpid(),url)
 with _LOCK:
  if key not in _POOLS:
   _POOLS[key]=ConnectionPool(url,min_size=0,max_size=integer('CADDIE_DB_POOL_SIZE',8,1,64),timeout=2,
    max_waiting=integer('CADDIE_DB_WAITERS',16,0,256),open=True,
    kwargs={'autocommit':True,'options':connection_options(url)})
  return _POOLS[key]

def connection_options(url):
 # Preserve explicit options (including isolated test search_path) before timeout bounds.
 from psycopg.conninfo import conninfo_to_dict
 return conninfo_to_dict(url).get('options','')+' -c statement_timeout=10000 -c lock_timeout=2000 -c idle_in_transaction_session_timeout=15000'

def close_pools(url=None):
 with _LOCK:
  for key,p in list(_POOLS.items()):
   if key[0]==os.getpid() and (url is None or key[1]==url):p.close();del _POOLS[key]
  for key in list(_SCHEMAS):
   if url is None or key[1]==url:_SCHEMAS.remove(key)
atexit.register(close_pools)

class Connection:
 def __init__(self,url=None,owner=None,implicit=False,mapping=False):
  self.path=require_url(url);self.owner=owner;self.implicit=implicit;self.mapping=mapping;self.closed=False;self.pool=pool(self.path)
  try:self.raw=self.pool.getconn(timeout=2)
  except (PoolTimeout,TooManyRequests) as exc:raise CapacityError('database capacity exceeded') from exc
 @property
 def in_transaction(self):return self.raw.info.transaction_status!=0
 def begin(self):
  self.raw.execute('BEGIN')
  if self.owner:self.raw.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',(self.owner,))
 def execute(self,sql,params=()):
  verb=sql.lstrip().split(None,1)[0].upper()
  if self.implicit and verb in ('INSERT','UPDATE','DELETE') and not self.in_transaction:self.begin()
  cur=self.raw.cursor(row_factory=dict_row if self.mapping else tuple_row);cur.execute(sql,params);return cur
 def executemany(self,sql,params):
  cur=self.raw.cursor();cur.executemany(sql,params);return cur
 def __enter__(self):return self
 def __exit__(self,typ,value,tb):
  if typ:self.raw.rollback()
  else:self.raw.commit()
 def close(self):
  if self.closed:return
  self.closed=True
  try:self.raw.rollback()
  finally:self.pool.putconn(self.raw)

def connect(url=None,**kw):return Connection(url,**kw)
def namespace(db,url):return ('postgres',hashlib.sha256(require_url(url).encode()).hexdigest())

def bootstrap_schema(url):
 """Explicit provisioning with a schema-owner connection, never automatic on requests."""
 with psycopg.connect(require_url(url),autocommit=True) as db:
  with db.transaction():
   db.execute("SELECT pg_advisory_xact_lock(hashtextextended('caddie-schema-v1',0))")
   existing=db.execute("SELECT to_regclass('schema_meta')").fetchone()[0]
   if existing:
    versions=db.execute('SELECT version FROM schema_meta').fetchall()
    if versions not in ([(1,)],[(2,)],[(SCHEMA_VERSION,)]):raise RuntimeError('database schema version mismatch')
   db.execute(Path(__file__).with_name('schema.sql').read_text(),prepare=False)
   from native_profile import provision_round_metadata
   provision_round_metadata(db)

def ensure_schema(db):
 key=(os.getpid(),db.path)
 with _LOCK:
  if key in _SCHEMAS:return
  versions=db.raw.execute('SELECT version FROM schema_meta').fetchall()
  if versions!=[(SCHEMA_VERSION,)]:raise RuntimeError('database schema version mismatch; provision explicitly')
  for table in TABLES:db.raw.execute('SELECT 1 FROM '+table+' LIMIT 0')
  _SCHEMAS.add(key)
