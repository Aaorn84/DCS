"""Owner-scoped event store; all golf rules execute in the shared core."""
import copy,hashlib,json,math,re,time
VERSION='1.0.0'
class StateError(ValueError):
    pass

class Conflict(StateError):
    pass

def _mapping_json(value):
    from collections.abc import Mapping
    if isinstance(value,Mapping):return dict(value.items())
    raise TypeError('unsupported JSON value')

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False, default=_mapping_json)

def require(ok, message):
    if not ok:
        raise StateError(message)

def initial():
    return {'version': 0, 'facts': {}, 'evidence': {}}

class Engine:
    """Owner is an authenticated host principal, NEVER an untrusted request body."""
    def __init__(self, database, owner):
        from database import connect,ensure_schema,namespace
        require(isinstance(owner, str) and bool(owner), 'owner required')
        self.owner = owner
        self.db = connect(database,owner=owner)
        try:
            ensure_schema(self.db)
            from state_components import Components
            self.components=Components(self.db,self.owner,namespace(self.db,database))
            self._committed=None
        except Exception:
            self.db.close();raise

    def close(self):
        self.db.close()

    def create(self, round_id):
        require(isinstance(round_id, str) and bool(round_id), 'round id required')
        self.db.execute('INSERT INTO rounds VALUES(%s,%s,%s) ON CONFLICT(owner,id) DO NOTHING', (self.owner, round_id, canonical(initial())))

    def state(self, round_id, *, lazy=False):
        from state_components import materialize
        own_transaction=not lazy and not self.db.in_transaction
        if own_transaction:self.db.execute('BEGIN')
        try:
            row=self.db.execute('SELECT state FROM rounds WHERE owner=%s AND id=%s',(self.owner,round_id)).fetchone()
            require(row is not None,'round not found for authenticated owner')
            self.components.aggregate=round_id
            state=self.components.decode(json.loads(row[0]))
            result=state if lazy else materialize(state)
            if own_transaction:self.db.execute('COMMIT')
            return result
        except Exception:
            if own_transaction:self.db.execute('ROLLBACK')
            raise

    def response_state(self,round_id):
        version=self.db.execute("SELECT (state::jsonb->>'version')::bigint FROM rounds WHERE owner=%s AND id=%s",(self.owner,round_id)).fetchone()
        require(version is not None,'round not found for authenticated owner')
        if self._committed and self._committed[0]==round_id and self._committed[1]['version']==version[0]:return self._committed[1]
        return self.state(round_id,lazy=True)

    def compact(self,round_id):
        self.db.begin()
        try:
            state=self.state(round_id,lazy=True)
            self.db.execute('UPDATE rounds SET state=%s WHERE owner=%s AND id=%s',(canonical(self.components.encode(state)),self.owner,round_id))
            self.db.execute('COMMIT')
        except Exception:
            self.db.execute('ROLLBACK');raise

    def command(self, round_id, command_id, kind, payload, expected_version=None, now=None, *, guard=None, on_commit=None):
        require(isinstance(command_id, str) and bool(command_id), 'command id required')
        payload = json.loads(canonical(payload))
        digest = hashlib.sha256(canonical([kind, payload, expected_version]).encode()).hexdigest()
        at = time.time() if now is None else now
        require(type(at) in (float, int) and math.isfinite(at), 'invalid clock')
        # Compute against a consistent read snapshot, without holding a database write lock.
        # Commit rechecks the version under the authenticated owner's transaction lock.
        self.db.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        try:
            s = self.state(round_id,lazy=True)
            base=s['version']
            prev=self.db.execute('SELECT digest,result FROM commands WHERE owner=%s AND round_id=%s AND command_id=%s',(self.owner,round_id,command_id)).fetchone()
            if prev:
                if prev[0]!=digest:raise Conflict('idempotency key reused with different payload')
                self.db.execute('COMMIT');self._committed=(round_id,s);return json.loads(prev[1])
            if expected_version is not None and base!=expected_version:raise Conflict('aggregate version conflict')
            if guard is not None:guard(s)
            seq=base+1
            result=dict(reduce(s,kind,payload,seq,at),version=seq)
            self.db.execute('COMMIT')
        except Exception:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise
        self.db.begin()
        try:
            # A simultaneous retry may have committed while this request was computing.
            prev=self.db.execute('SELECT digest,result FROM commands WHERE owner=%s AND round_id=%s AND command_id=%s',(self.owner,round_id,command_id)).fetchone()
            if prev:
                if prev[0]!=digest:raise Conflict('idempotency key reused with different payload')
                current=self.state(round_id,lazy=True)
                self.db.execute('COMMIT');self._committed=(round_id,current);return json.loads(prev[1])
            current=self.state(round_id,lazy=True)
            if current['version']!=base:raise Conflict('aggregate version conflict')
            if guard is not None:guard(current)
            self.db.execute('INSERT INTO commands VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(self.owner,round_id,command_id,digest,kind,canonical(payload),at,seq,canonical(result)))
            self.db.execute('UPDATE rounds SET state=%s WHERE owner=%s AND id=%s',(canonical(self.components.encode(s)),self.owner,round_id))
            if on_commit is not None:on_commit(s,result)
            self.db.execute('COMMIT');self._committed=(round_id,s)
            return result
        except Exception:
            if self.db.in_transaction:self.db.execute('ROLLBACK')
            raise

    def replay(self, round_id):
        self.state(round_id)  # ownership check even for empty round
        s = initial()
        for kind, payload, at, seq in self.db.execute('SELECT kind,payload,at,seq FROM commands WHERE owner=%s AND round_id=%s ORDER BY seq', (self.owner, round_id)):
            reduce(s, kind, json.loads(payload), seq, at)
        return s

def fact_value(s,path,default=None):
 f=s.get('facts',{}).get(path)
 return f.get('value',default) if f and f.get('valid',True) else default

def reduce(s,kind,p,seq,now):
 if kind=='native_postgame_event':
  from native_postgame import reduce_postgame as reduce_event
 elif kind=='shared_web_event':
  from shared_web import reduce_event
 elif kind=='offline_rules_event':
  from offline_rules_adapter import reduce_event
 elif kind=='application_event':
  from application import reduce_event
 elif kind=='international_event':
  from international import reduce_event
 else:raise StateError('unsupported event kind; legacy reducers removed')
 result=reduce_event(s,p,seq,now);s['version']=seq
 return result
