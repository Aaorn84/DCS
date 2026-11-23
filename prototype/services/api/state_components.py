"""Owner-scoped immutable list components, loaded only when domain code reads them."""
import copy,hashlib,json,threading
from collections import OrderedDict

_CACHE=OrderedDict();_CACHE_BYTES=0;_LOCK=threading.Lock();_LIMIT=8*1024*1024
TAG='__caddie_list_component_v1__'

class LazyList(list):
 def __init__(self,store,digest):
  super().__init__();self.store=store;self.digest=digest;self.loaded=False;self.original=None
 def load(self):
  if not self.loaded:
   raw=self.store.read(self.digest);items=json.loads(raw)
   if not isinstance(items,list):raise ValueError('invalid stored list component')
   list.extend(self,items);self.original=raw;self.loaded=True
  return self
 def __len__(self):self.load();return list.__len__(self)
 def __iter__(self):self.load();return list.__iter__(self)
 def __getitem__(self,key):self.load();return list.__getitem__(self,key)
 def __setitem__(self,key,value):self.load();return list.__setitem__(self,key,value)
 def __delitem__(self,key):self.load();return list.__delitem__(self,key)
 def __contains__(self,value):self.load();return list.__contains__(self,value)
 def __eq__(self,other):self.load();return list.__eq__(self,other)
 def __ne__(self,other):return not self.__eq__(other)
 def __repr__(self):self.load();return list.__repr__(self)
 def __deepcopy__(self,memo):
  # Normal copy semantics: callers may safely mutate nested objects in the copy.
  self.load();result=copy.deepcopy(list(self),memo);memo[id(self)]=result;return result
 def append(self,value):self.load();return list.append(self,value)
 def extend(self,values):self.load();return list.extend(self,values)
 def insert(self,index,value):self.load();return list.insert(self,index,value)
 def pop(self,index=-1):self.load();return list.pop(self,index)
 def remove(self,value):self.load();return list.remove(self,value)
 def clear(self):self.load();return list.clear(self)
 def reverse(self):self.load();return list.reverse(self)
 def sort(self,*args,**kwargs):self.load();return list.sort(self,*args,**kwargs)
 def copy(self):self.load();return list.copy(self)
 def count(self,value):self.load();return list.count(self,value)
 def index(self,*args):self.load();return list.index(self,*args)
 def __iadd__(self,values):self.extend(values);return self
 def __imul__(self,n):self.load();list.__imul__(self,n);return self
 def __reversed__(self):self.load();return list.__reversed__(self)
 def __add__(self,other):self.load();return list(self)+list(other)
 def __radd__(self,other):self.load();return list(other)+list(self)
 def __mul__(self,n):self.load();return list(self)*n
 def __rmul__(self,n):return self.__mul__(n)

class Components:
 def __init__(self,db,owner,namespace):self.db=db;self.owner=owner;self.namespace=namespace;self.reads=0;self.aggregate=None
 def read(self,digest):
  global _CACHE_BYTES
  key=(self.namespace,self.owner,digest)
  with _LOCK:
   raw=_CACHE.get(key)
   if raw is not None:_CACHE.move_to_end(key);return raw
  row=self.db.execute('SELECT data FROM state_components WHERE owner=%s AND digest=%s',(self.owner,digest)).fetchone()
  if row is None:raise ValueError('stored component missing for authenticated owner')
  raw=row[0]
  if hashlib.sha256(raw.encode()).hexdigest()!=digest:raise ValueError('stored component checksum mismatch')
  self.reads+=1;self.cache(digest,raw);return raw
 def cache(self,digest,raw):
  global _CACHE_BYTES
  size=len(raw.encode())
  if size>_LIMIT:return
  key=(self.namespace,self.owner,digest)
  with _LOCK:
   previous=_CACHE.pop(key,None)
   if previous is not None:_CACHE_BYTES-=len(previous.encode())
   _CACHE[key]=raw;_CACHE_BYTES+=size
   while _CACHE_BYTES>_LIMIT:
    _,old=_CACHE.popitem(last=False);_CACHE_BYTES-=len(old.encode())
 def store(self,values):
  from round_state import canonical
  if isinstance(values,LazyList) and not values.loaded:return {TAG:values.digest}
  raw=canonical(values)
  if isinstance(values,LazyList) and raw==values.original:return {TAG:values.digest}
  digest=hashlib.sha256(raw.encode()).hexdigest()
  self.db.execute('INSERT INTO state_components(owner,digest,data) VALUES(%s,%s,%s) ON CONFLICT(owner,digest) DO NOTHING',(self.owner,digest,raw))
  self.cache(digest,raw);return {TAG:digest}
 def receipt_bucket(self,aggregate,name):
  return hashlib.sha256(json.dumps([self.owner,aggregate,name],separators=(',',':')).encode()).digest()
 def ensure_bucket(self,aggregate,name):
  bucket=self.receipt_bucket(aggregate,name)
  self.db.execute('INSERT INTO receipt_buckets(id,owner,aggregate_id,name) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING',(bucket,self.owner,aggregate,name))
  return bucket
 def encode(self,value,path=()):
  if isinstance(value,ReceiptMap):return value.flush()
  if isinstance(value,dict) and len(path)==2 and path[0]=='journey' and path[1].endswith('receipts') and self.aggregate:
   from round_state import canonical
   bucket=self.ensure_bucket(self.aggregate,path[1])
   self.db.execute('DELETE FROM state_receipts WHERE bucket_id=%s',(bucket,))
   self.db.executemany('INSERT INTO state_receipts(bucket_id,receipt_id,data) VALUES(%s,%s,%s)',[(bucket,k,canonical(v)) for k,v in value.items()])
   return {_RECEIPTS:dict(aggregate=self.aggregate,name=path[1])}
  if isinstance(value,LazyList):return self.store(value)
  if isinstance(value,dict):return {k:self.encode(v,path+(str(k),)) for k,v in value.items()}
  if isinstance(value,list):
   if value and external(path):return self.store(value)
   return [self.encode(v,path+(str(i),)) for i,v in enumerate(value)]
  return value
 def decode(self,value):
  if isinstance(value,dict):
   if set(value)=={_RECEIPTS}:
    spec=value[_RECEIPTS]
    if spec.get('aggregate')!=self.aggregate:raise ValueError('receipt aggregate mismatch')
    return ReceiptMap(self,spec['aggregate'],spec['name'])
   if set(value)=={TAG} and isinstance(value[TAG],str) and len(value[TAG])==64:return LazyList(self,value[TAG])
   return {k:self.decode(v) for k,v in value.items()}
  if isinstance(value,list):return [self.decode(v) for v in value]
  return value

def external(path):
 if not path:return False
 if path==('journey','shared_web_package','items'):return True
 if path[0]=='evidence' and path[-1] in ('display_paths','surface_zones','objects','simulation_boundary_rings','boundary_segments','landing_zones') and 'holes' in path:return True
 if path[:2]==('journey','history') and (path[-1]=='scores' or (path[-1]=='shots' and 'hole_history' in path)):return True
 if path[:2]==('journey','history') and path[-1]=='course_basis':return True
 if path[:2]==('journey','round_ledger') and path[-1] in ('sequence','incidents'):return True
 return False

def materialize(value):
 if isinstance(value,Mapping):return {k:materialize(v) for k,v in value.items()}
 if isinstance(value,list):return [materialize(v) for v in value]
 return value

# Mutable idempotency receipts are indexed separately from immutable geometry.
from collections.abc import MutableMapping,Mapping
_RECEIPTS='__caddie_receipt_bucket_v1__'
_MISSING=object()
class ReceiptMap(MutableMapping):
 def __init__(self,store,aggregate,name):self.store=store;self.aggregate=aggregate;self.name=name;self.values_cache={};self.original={};self.deleted=set();self.bucket=store.receipt_bucket(aggregate,name)
 def __getitem__(self,key):
  if key in self.deleted:raise KeyError(key)
  if key not in self.values_cache:
   row=self.store.db.execute('SELECT data FROM state_receipts WHERE bucket_id=%s AND receipt_id=%s',(self.bucket,key)).fetchone()
   self.original[key]=row[0] if row else _MISSING
   self.values_cache[key]=json.loads(row[0]) if row else _MISSING
  value=self.values_cache[key]
  if value is _MISSING:raise KeyError(key)
  return value
 def __setitem__(self,key,value):
  if key not in self.original:
   try:self[key]
   except KeyError:pass
  self.deleted.discard(key);self.values_cache[key]=value
 def __delitem__(self,key):self[key];self.deleted.add(key)
 def __iter__(self):
  rows=self.store.db.execute('SELECT receipt_id FROM state_receipts WHERE bucket_id=%s',(self.bucket,)).fetchall()
  keys={r[0] for r in rows}|{k for k,v in self.values_cache.items() if v is not _MISSING}
  return iter(sorted(keys-self.deleted))
 def __len__(self):
  n=self.store.db.execute('SELECT count(*) FROM state_receipts WHERE bucket_id=%s',(self.bucket,)).fetchone()[0]
  n+=sum(self.original.get(k) is _MISSING and v is not _MISSING and k not in self.deleted for k,v in self.values_cache.items())
  n-=sum(self.original.get(k) is not _MISSING for k in self.deleted)
  return n
 def items(self):
  rows=self.store.db.execute('SELECT receipt_id,data FROM state_receipts WHERE bucket_id=%s',(self.bucket,)).fetchall()
  for key,raw in rows:
   if key not in self.values_cache:self.original[key]=raw;self.values_cache[key]=json.loads(raw)
  return [(k,v) for k,v in self.values_cache.items() if k not in self.deleted and v is not _MISSING]
 def __deepcopy__(self,memo):return copy.deepcopy(dict(self.items()),memo)
 def flush(self):
  from round_state import canonical
  self.store.ensure_bucket(self.aggregate,self.name)
  for key in self.deleted:self.store.db.execute('DELETE FROM state_receipts WHERE bucket_id=%s AND receipt_id=%s',(self.bucket,key))
  for key,value in self.values_cache.items():
   if key in self.deleted or value is _MISSING:continue
   raw=canonical(value)
   if raw==self.original.get(key):continue
   self.store.db.execute('INSERT INTO state_receipts(bucket_id,receipt_id,data) VALUES(%s,%s,%s) ON CONFLICT(bucket_id,receipt_id) DO UPDATE SET data=excluded.data',(self.bucket,key,raw))
  return {_RECEIPTS:dict(aggregate=self.aggregate,name=self.name)}
