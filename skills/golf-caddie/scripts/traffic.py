"""Bounded admission and rate limits. Redis is shared across production replicas."""
import hashlib,threading,time
from collections import OrderedDict
from runtime_control import CapacityError
class RateLimited(CapacityError):pass
class Limits:
 def __init__(self,redis_url=None,slots=10000,clock=time.monotonic):
  self.lock=threading.Lock();self.entries=OrderedDict();self.slots=slots;self.clock=clock
  self.redis=None
  if redis_url:
   import redis
   self.redis=redis.Redis.from_url(redis_url,socket_connect_timeout=1,socket_timeout=1,decode_responses=True)
   self.redis.ping()
 def check(self,category,identity,limit,window=60):
  key='caddie:limit:'+category+':'+hashlib.sha256(identity.encode()).hexdigest()
  if self.redis:
   try:
    count=self.redis.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n",1,key,window)
   except Exception as exc:raise CapacityError('rate limit service unavailable') from exc
   if count>limit:raise RateLimited('request rate exceeded')
   return
  with self.lock:
   now=self.clock()
   while self.entries and next(iter(self.entries.values()))[0]<=now:self.entries.popitem(last=False)
   expires,count=self.entries.get(key,(now+window,0))
   if expires<=now:expires,count=now+window,0
   if key not in self.entries and len(self.entries)>=self.slots:raise CapacityError('rate limit capacity exceeded')
   self.entries[key]=(expires,count+1)
   # Fixed expiry ordering: don't move active keys on each request.
   if count+1>limit:raise RateLimited('request rate exceeded')
