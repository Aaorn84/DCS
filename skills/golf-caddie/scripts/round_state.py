#!/usr/bin/env python3
"""Transactional round-state engine. Trusted host supplies authenticated owner.
No network, speech recognition, GPS swing detection or unrestricted NLP included.
"""
import copy
import hashlib
import json
import math
import re
import sqlite3
import time
from datetime import datetime

VERSION = '0.5.0'


class StateError(ValueError):
    pass


class Conflict(StateError):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def require(ok, message):
    if not ok:
        raise StateError(message)


def initial():
    return {'version': 0, 'facts': {}, 'evidence': {}, 'patches': {},
            'derived': {}, 'questions': {}, 'outbox': {}, 'interpretations': {}}


def field(path, value, status):
    require(isinstance(path, str), 'field path required')
    require(status in ('confirmed', 'estimated', 'unknown'), 'invalid fact status')
    require((value is None) == (status == 'unknown'), 'null requires unknown status')
    if path in ('context.quiet', 'context.preparing', 'preferences.proactive',
                'permissions.strategy', 'preferences.coaching'):
        require(type(value) is bool, 'boolean required')
        require(status == 'confirmed', 'preference must be explicit')
    elif path == 'context.active_hole':
        require(type(value) is int and 1 <= value <= 18, 'hole must be 1..18')
    elif re.fullmatch(r'holes\.([1-9]|1[0-8])\.(total|putts|penalties)', path):
        if value is not None:
            limit = 30
            require(type(value) is int and (1 if path.endswith('.total') else 0) <= value <= limit,
                    'invalid score count')
    elif path == 'context.ball_position' or re.fullmatch(r'shots\.[A-Za-z0-9_-]+\.(actual_club|planned_club|hole|position)', path):
        if value is not None:
            if path.endswith('.hole'):
                require(type(value) is int and 1 <= value <= 18, 'invalid shot hole')
            elif path.endswith('.position') or path == 'context.ball_position':
                require(isinstance(value, dict) and value.get('crs') == 'WGS84'
                        and value.get('ball_position_confirmed') is True, 'confirmed WGS84 ball position required')
                for key, low, high in [('latitude', -90, 90), ('longitude', -180, 180), ('accuracy_m', .01, 20000)]:
                    n = value.get(key)
                    require(type(n) in (int, float) and math.isfinite(n) and low <= n <= high, 'invalid position')
                try:
                    stamp = datetime.fromisoformat(value['observed_at'].replace('Z', '+00:00'))
                    require(stamp.tzinfo is not None, 'position time requires timezone')
                except (KeyError, TypeError, ValueError) as exc:
                    raise StateError('invalid position time') from exc
            else:
                require(isinstance(value, str) and bool(re.fullmatch(r'(driver|[3-9]w|[2-9]i|[2-9]h|pw|sw|lw|gw|putter|[4-6][0-9]deg)', value)), 'invalid club')
    else:
        raise StateError('unsupported field')


def valid_ref(s, ref):
    if ref.startswith('chain:'):
        from shot_chain import node_live
        node = s.get('shot_chain', {}).get('nodes', {}).get(ref[6:])
        return node if node_live(s, node) else None
    if ref.startswith('evidence:'):
        e = s['evidence'].get(ref[9:])
        return {'value': e, 'version': e['revision'] + 1, 'status': 'observed', 'valid': True} if e and e['active'] and e['phase'] == 'final' else None
    if ref.startswith('derived:'):
        d = s['derived'].get(ref[8:])
    else:
        d = s['facts'].get(ref)
    return d if d and d.get('valid', True) else None


def refs_current(s, refs):
    return isinstance(refs, dict) and all(type(v) is int and v > 0 and valid_ref(s, k) is not None
                                         and valid_ref(s, k)['version'] == v for k, v in refs.items())


def confirmed_lineage(s, ref):
    d = valid_ref(s, ref)
    if not d:
        return False
    if ref.startswith('derived:'):
        return all(confirmed_lineage(s, k) for k in d['deps'])
    return d['status'] == 'confirmed'


def fact_value(s, path, default=None):
    f = valid_ref(s, path)
    if not f and path in ('context.quiet', 'context.preparing') and path in s['facts']:
        return True  # uncertain silence/preparation is fail-closed until explicit resolution
    return f['value'] if f else default


def invalidate(s):
    # Materialized node validity follows evidence without deleting historical nodes.
    from_chain=s.get('shot_chain',{}).get('nodes',{})
    if from_chain:
        from shot_chain import node_live
        for node in from_chain.values():
            if node.get('valid',True) and not node_live(s,node):
                node['valid']=False
                node['learning_eligibility']['total_distance_candidate']=False
    # Repeated until transitive derived dependencies stop changing.
    changed = True
    while changed:
        changed = False
        for d in s['derived'].values():
            if d['valid'] and not refs_current(s, d['deps']):
                d['valid'] = False
                changed = True
    for shot in s.get('shot_chain',{}).get('shots',{}).values():
        ex=from_chain.get(shot['slots'].get('execution'))
        if ex:
            ex['learning_eligibility']['total_distance_candidate']=ex.get('valid',True) and any(
                s['derived'].get(lid,{}).get('valid') and
                ('chain:'+ex['node_id']) in s['derived'][lid]['deps']
                for lid in shot['learning_candidates'])
    for q in s['questions'].values():
        if q['status'] == 'pending' and not refs_current(s, q['deps']):
            q['status'] = 'stale'
    for speech in s['outbox'].values():
        if speech['status'] == 'queued' and (not refs_current(s, speech['deps'])
                or fact_value(s, 'context.quiet', False)
                or fact_value(s, 'context.preparing', False)
                or (speech['strategy'] and fact_value(s, 'permissions.strategy') is not True)
                or (speech['proactive'] and fact_value(s, 'preferences.proactive') is not True)):
            speech['status'] = 'cancelled'


def score_check(facts):
    for hole in range(1, 19):
        def val(name):
            f = facts.get(f'holes.{hole}.{name}', {})
            return f.get('value') if f.get('valid', True) else None
        total, putts, penalties = (val(x) for x in ('total', 'putts', 'penalties'))
        if total is not None:
            require(sum(x or 0 for x in (putts, penalties)) <= total, 'putts + penalties exceed total (penalties already included)')


def apply_patch(s, patch, seq):
    require(patch['base_version'] == s['version'], 'stale proposal version')
    require(refs_current(s, patch['read_versions']), 'stale proposal dependencies')
    for eid in patch['evidence_ids']:
        require(s['evidence'].get(eid, {}).get('active') is True and
                s['evidence'][eid]['phase'] == 'final', 'final active evidence required')
    facts = copy.deepcopy(s['facts'])
    before = {}
    for op in patch['operations']:
        path = op['path']
        field(path, op['value'], op['status'])
        before[path] = copy.deepcopy(facts.get(path))
        facts[path] = {'value': op['value'], 'status': op['status'], 'version': seq,
                       'valid': True, 'evidence_ids': patch['evidence_ids']}
    score_check(facts)
    s['facts'] = facts
    patch.update(status='committed', before=before, committed_version=seq)
    invalidate(s)


def reduce(s, kind, p, seq, now):
    """Pure deterministic reducer, shared by commit and replay."""
    result = {}
    if kind == 'attribution_event':
        from shot_chain import reduce_event
        result = reduce_event(s, p, seq, now)
    elif kind == 'session_event':
        from round_session import reduce_event
        result = reduce_event(s, p, seq, now)
    elif kind == 'evidence':
        eid = p['id']
        require(isinstance(eid, str) and eid, 'evidence id required')
        require(type(p['revision']) is int and p['revision'] >= 0, 'invalid revision')
        require(p['phase'] in ('partial', 'final'), 'invalid ASR phase')
        require(p.get('source') in ('user', 'gps', 'course', 'sensor'), 'unsupported evidence source')
        if p['source'] == 'course':
            data = p.get('data')
            require(isinstance(data, dict) and isinstance(data.get('course_id'), str) and bool(data['course_id'])
                    and isinstance(data.get('map_version'), str) and bool(data['map_version'])
                    and (data.get('crs') == 'WGS84' or (data.get('crs') is None
                    and data.get('coordinate_status') == 'unverified' and data.get('spatial_use_allowed') is False
                    and data.get('holes') == [])), 'versioned course snapshot or explicitly non-spatial catalogue required')
        require(isinstance(p.get('observed_at'), str), 'observation time required')
        try:
            t = datetime.fromisoformat(p['observed_at'].replace('Z', '+00:00'))
            require(t.tzinfo is not None, 'timezone required')
        except ValueError as exc:
            raise StateError('invalid observation time') from exc
        prior = [(k, v) for k, v in s['evidence'].items() if v['id'] == eid]
        require(not prior or p['revision'] > max(v['revision'] for _, v in prior)
                or (p['phase'] == 'final' and p['revision'] == max(v['revision'] for _, v in prior)
                    and not any(v['revision'] == p['revision'] and v['phase'] == 'final' for _, v in prior)),
                'stale or duplicate evidence revision')
        # Partial revision does not supersede a final fact. New final invalidates old evidence-derived facts.
        if p['phase'] == 'final':
            retired = set()
            for k, v in prior:
                if v['active']:
                    v['active'] = False
                    retired.add(k)
            for f in s['facts'].values():
                if retired.intersection(f.get('evidence_ids', [])):
                    f['valid'] = False
        key = f'{eid}:{p["revision"]}' + (':partial' if p['phase'] == 'partial' else '')
        s['evidence'][key] = dict(copy.deepcopy(p), active=True, received_at=now)
        invalidate(s)
        result = {'evidence_id': key}
    elif kind in ('control', 'gps_transition'):
        ev = s['evidence'].get(p['evidence_id'])
        require(ev and ev['active'] and ev['phase'] == 'final', 'active final evidence required')
        if kind == 'control':
            require(ev['source'] == 'user' and p.get('explicit') is True, 'explicit user control required')
            require(p['path'] in ('context.quiet', 'context.preparing', 'preferences.proactive', 'preferences.coaching', 'permissions.strategy'), 'invalid control field')
            path, value = p['path'], p['value']
        else:
            require(ev['source'] == 'gps' and ev.get('reliable_transition') is True, 'reliable GPS transition required')
            old_hole = s['facts'].get('context.active_hole')
            if old_hole:
                old_times = [s['evidence'][e]['observed_at'] for e in old_hole['evidence_ids'] if e in s['evidence']]
                incoming = datetime.fromisoformat(ev['observed_at'].replace('Z', '+00:00'))
                require(all(incoming >= datetime.fromisoformat(t.replace('Z', '+00:00')) for t in old_times), 'late GPS transition')
            path, value = 'context.active_hole', p['hole']
        field(path, value, 'confirmed')
        s['facts'][path] = dict(value=value, status='confirmed', version=seq, valid=True, evidence_ids=[p['evidence_id']])
        invalidate(s)
    elif kind == 'interpret':
        ev = s['evidence'].get(p['evidence_id'])
        require(ev and ev['active'] and ev['phase'] == 'final', 'interpretation requires final evidence')
        require(p['id'] not in s['interpretations'], 'interpretation id exists')
        require(isinstance(p['candidates'], list) and bool(p['candidates']), 'candidate interpretations required')
        for c in p['candidates']:
            require(isinstance(c, dict) and isinstance(c.get('operations'), list), 'structured candidate required')
            for op in c['operations']:
                field(op['path'], op['value'], op['status'])
        report = assess_ambiguity(p['candidates'], lambda c: c['outcome'],
                                  quiet=fact_value(s, 'context.quiet', False) or fact_value(s, 'context.preparing', False),
                                  complete=p.get('complete') is True)
        s['interpretations'][p['id']] = dict(copy.deepcopy(p), report=report, version=seq)
        result = report
    elif kind == 'question':
        require(not any(q['status'] == 'pending' for q in s['questions'].values()) and not s.get('shot_chain',{}).get('pending_question'), 'only one pending question')
        require(not fact_value(s, 'context.quiet', False) and not fact_value(s, 'context.preparing', False), 'question deferred')
        require(not p.get('proactive') or fact_value(s, 'preferences.proactive') is True, 'proactive not authorized')
        require(p['field'] in ('actual_club', 'ball_position', 'total', 'putts', 'penalties'), 'unsupported question field')
        require(isinstance(p['target'], str) and bool(re.fullmatch(r'(shots\.[A-Za-z0-9_-]+|holes\.([1-9]|1[0-8]))', p['target'])), 'invalid question target')
        require((p['target'].startswith('shots.') and p['field'] in ('actual_club', 'ball_position')) or (p['target'].startswith('holes.') and p['field'] in ('total', 'putts', 'penalties')), 'question target/field mismatch')
        require(p['id'] not in s['questions'] and refs_current(s, p.get('deps', {})), 'question conflict')
        s['questions'][p['id']] = dict(copy.deepcopy(p), deps=p.get('deps', {}), status='pending')
    elif kind == 'propose':
        require(p['id'] not in s['patches'], 'patch already exists')
        require(p['base_version'] == s['version'], 'stale proposal version')
        require(p.get('evidence_ids') and all(s['evidence'].get(e, {}).get('active') and s['evidence'][e]['phase'] == 'final' for e in p['evidence_ids']), 'active final evidence required')
        require(p.get('operations') and len({op['path'] for op in p['operations']}) == len(p['operations']), 'empty or duplicate operations')
        if p.get('interpretation_id'):
            interpretation = s['interpretations'].get(p['interpretation_id'])
            require(interpretation is not None and interpretation['evidence_id'] in p['evidence_ids'], 'interpretation evidence mismatch')
            require(any(c['operations'] == p['operations'] for c in interpretation['candidates']), 'proposal not a recorded candidate')
            alternatives = {canonical(c['operations']) for c in interpretation['candidates']}
            if interpretation['report']['decision'] != 'common_answer' or len(alternatives) != 1:
                resolution = s['evidence'].get(p.get('resolution_evidence_id'), {})
                require(p.get('resolved_explicit') is True and resolution.get('source') == 'user'
                        and resolution.get('active') and resolution.get('phase') == 'final'
                        and p['resolution_evidence_id'] in p['evidence_ids']
                        and p['resolution_evidence_id'] != interpretation['evidence_id'], 'unresolved interpretation cannot commit')
        require(refs_current(s, p.get('read_versions', {})), 'stale read set')
        for op in p['operations']:
            field(op['path'], op['value'], op['status'])
        # Proposal itself advances aggregate version; bind confirmation to that new version.
        s['patches'][p['id']] = dict(copy.deepcopy(p), base_version=seq, read_versions=p.get('read_versions', {}), status='needs_confirmation')
        result = {'patch_id': p['id'], 'confirmation_version': seq}
    elif kind == 'confirm':
        patch = s['patches'].get(p['id'])
        require(patch is not None and patch['status'] == 'needs_confirmation', 'patch not awaiting confirmation')
        require(p.get('explicit') is True, 'explicit confirmation required')
        require(p['confirmation_version'] == patch['base_version'], 'wrong confirmation version')
        # Preference, score and actual shot fields require user-origin evidence, not GPS alone.
        require(any(s['evidence'][e]['source'] == 'user' for e in patch['evidence_ids']), 'user evidence required')
        apply_patch(s, patch, seq)
    elif kind == 'retract':
        patch = s['patches'].get(p['id'])
        require(patch is not None and patch['status'] == 'committed', 'patch not committed')
        require(p.get('explicit') is True, 'explicit retraction required')
        require(all(s['facts'][path]['version'] == patch['committed_version'] for path in patch['before']), 'later edits conflict with retraction')
        candidate = copy.deepcopy(s['facts'])
        for path, old in patch['before'].items():
            # A fresh version prevents ABA restoration of stale derived results.
            candidate[path] = dict(copy.deepcopy(old) if old else {'value': None, 'status': 'unknown', 'valid': True, 'evidence_ids': []}, version=seq)
            if old and any(not s['evidence'].get(e, {}).get('active') for e in old.get('evidence_ids', [])):
                candidate[path]['valid'] = False
        score_check(candidate)
        s['facts'] = candidate
        patch['status'] = 'retracted'
        patch['retracted_version'] = seq
        invalidate(s)
    elif kind == 'derive':
        require(p.get('deps') and refs_current(s, p['deps']), 'valid dependencies required')
        require(p['id'] not in s['derived'], 'derived id already exists; use a new version id')
        require(isinstance(p.get('algorithm_version'), str), 'algorithm version required')
        require(p.get('kind') in ('distance', 'club_stats', 'strategy', 'coaching'), 'unsupported derivation kind')
        if p['kind'] == 'club_stats':
            require(all(confirmed_lineage(s, k) for k in p['deps']), 'estimated facts cannot train stats')
        s['derived'][p['id']] = dict(copy.deepcopy(p), version=seq, valid=True)
    elif kind == 'enqueue':
        require(p['id'] not in s['outbox'] and refs_current(s, p.get('deps', {})), 'speech conflict or stale dependencies')
        require(isinstance(p.get('text'), str) and p['text'].strip(), 'speech text required')
        require(type(p.get('expires_at')) in (int, float) and math.isfinite(p['expires_at']) and p['expires_at'] > now, 'speech expiry required')
        require(type(p.get('strategy')) is bool and type(p.get('proactive')) is bool, 'speech flags required')
        require(p.get('scope') in ('current', 'past'), 'speech scope required')
        deps = dict(p.get('deps', {}))
        if p['scope'] == 'current':
            for key in ('context.active_hole',):
                require(valid_ref(s, key) is not None, 'current context unknown')
                deps[key] = s['facts'][key]['version']
            # A round-level current ball fact prevents stale speech when a new shot ID appears.
            if valid_ref(s, 'context.ball_position'):
                deps['context.ball_position'] = s['facts']['context.ball_position']['version']
            if p['strategy']:
                require('context.ball_position' in deps, 'strategy needs current ball position dependency')
        s['outbox'][p['id']] = dict(copy.deepcopy(p), deps=deps, status='queued')
        invalidate(s)
    elif kind == 'dispatch':
        invalidate(s)
        speech = s['outbox'].get(p['id'])
        require(speech is not None, 'unknown speech')
        if speech['status'] == 'queued' and now >= speech['expires_at']:
            speech['status'] = 'expired'
        if speech['status'] == 'queued':
            speech['status'] = 'claimed'
            result = {'text': speech['text'], 'delivery_id': p['id']}
        else:
            result = {'text': None, 'status': speech['status']}
    elif kind == 'answer':
        q = s['questions'].get(p['id'])
        require(q is not None and q['status'] == 'pending' and refs_current(s, q['deps']), 'question stale or missing')
        q['status'] = 'answered'
    else:
        raise StateError('unsupported command')
    s['version'] = seq
    return result


class Engine:
    """Owner is an authenticated host principal, NEVER an untrusted request body."""
    def __init__(self, database, owner):
        require(isinstance(owner, str) and bool(owner), 'owner required')
        self.owner = owner
        self.db = sqlite3.connect(database, isolation_level=None, timeout=10)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS rounds(owner TEXT, id TEXT, state TEXT NOT NULL,
          PRIMARY KEY(owner,id));
        CREATE TABLE IF NOT EXISTS commands(owner TEXT, round_id TEXT, command_id TEXT,
          digest TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, at REAL NOT NULL,
          seq INTEGER NOT NULL, result TEXT NOT NULL,
          PRIMARY KEY(owner,round_id,command_id), UNIQUE(owner,round_id,seq),
          FOREIGN KEY(owner,round_id) REFERENCES rounds(owner,id));
        ''')

    def close(self):
        self.db.close()

    def create(self, round_id):
        require(isinstance(round_id, str) and bool(round_id), 'round id required')
        self.db.execute('INSERT OR IGNORE INTO rounds VALUES(?,?,?)', (self.owner, round_id, canonical(initial())))

    def state(self, round_id):
        row = self.db.execute('SELECT state FROM rounds WHERE owner=? AND id=?', (self.owner, round_id)).fetchone()
        require(row is not None, 'round not found for authenticated owner')
        return json.loads(row[0])

    def command(self, round_id, command_id, kind, payload, expected_version=None, now=None):
        require(isinstance(command_id, str) and bool(command_id), 'command id required')
        payload = json.loads(canonical(payload))
        digest = hashlib.sha256(canonical([kind, payload, expected_version]).encode()).hexdigest()
        at = time.time() if now is None else now
        require(type(at) in (float, int) and math.isfinite(at), 'invalid clock')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            s = self.state(round_id)
            prev = self.db.execute('SELECT digest,result FROM commands WHERE owner=? AND round_id=? AND command_id=?', (self.owner, round_id, command_id)).fetchone()
            if prev:
                if prev[0] != digest:
                    raise Conflict('idempotency key reused with different payload')
                self.db.execute('COMMIT')
                return json.loads(prev[1])
            if expected_version is not None and s['version'] != expected_version:
                raise Conflict('aggregate version conflict')
            seq = s['version'] + 1
            result = dict(reduce(s, kind, payload, seq, at), version=seq)
            self.db.execute('INSERT INTO commands VALUES(?,?,?,?,?,?,?,?,?)', (self.owner, round_id, command_id, digest, kind, canonical(payload), at, seq, canonical(result)))
            self.db.execute('UPDATE rounds SET state=? WHERE owner=? AND id=?', (canonical(s), self.owner, round_id))
            self.db.execute('COMMIT')
            return result
        except Exception:
            self.db.execute('ROLLBACK')
            raise

    def replay(self, round_id):
        self.state(round_id)  # ownership check even for empty round
        s = initial()
        for kind, payload, at, seq in self.db.execute('SELECT kind,payload,at,seq FROM commands WHERE owner=? AND round_id=? ORDER BY seq', (self.owner, round_id)):
            reduce(s, kind, json.loads(payload), seq, at)
        return s


def assess_ambiguity(candidates, planner, quiet=False, complete=True):
    """Read-only planner emits comparable current-answer and consequence fields.
    Empty/missing/incomplete results fail closed. No candidate is committed here.
    """
    keys = ('answer', 'feasible', 'forced_carry', 'target', 'club', 'score_effect',
            'record_effect', 'permission_effect')
    try:
        require(complete and bool(candidates), 'candidate coverage unknown')
        outcomes = [planner(copy.deepcopy(c)) for c in candidates]
        require(all(isinstance(o, dict) and all(k in o for k in keys) for o in outcomes), 'incomplete planner result')
        same = len({canonical(o) for o in outcomes}) == 1
        answers = [o['answer'] for o in outcomes]
        common = answers[0] if all(canonical(a) == canonical(answers[0]) for a in answers) else None
        return {'decision': 'common_answer' if same else ('defer' if quiet else 'clarify'),
                'common_answer': common, 'commit_allowed': False,
                'reason': 'same_consequences' if same else 'different_consequences'}
    except Exception:
        return {'decision': 'unknown', 'common_answer': None, 'commit_allowed': False,
                'reason': 'incomplete_or_failed_evaluation'}


NUM = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9,
       '十': 10, '十一': 11, '十二': 12, '十三': 13, '十四': 14, '十五': 15, '十六': 16, '十七': 17, '十八': 18}


def numeral(s):
    return int(s) if s.isdigit() else NUM.get(s)


def attribute(text, state, question_id=None, shot_id=None):
    """Conservative Chinese transcript adapter; returns proposals, NEVER writes.
    Unsupported language/ambiguous reference stays unresolved. Host/LLM adapters
    may emit richer candidates but must use the same transactional gate.
    """
    require(isinstance(text, str), 'text required')
    if re.search(r'他|她|同伴|球友', text):
        return {'status': 'other_player', 'operations': []}
    q = state['questions'].get(question_id) if question_id else None
    if question_id and (not q or q['status'] != 'pending' or not refs_current(state, q['deps'])):
        return {'status': 'clarify', 'operations': []}
    target = q['target'] if q else ('shots.' + shot_id if shot_id else None)
    ops = []
    number = r'(十八|十七|十六|十五|十四|十三|十二|十一|十|[一二两三四五六七八九]|\d{1,2})'
    score = re.fullmatch(r'\s*' + number + r'号洞\s*' + number + r'杆[。！!\s]*', text)
    if score:
        h, n = map(numeral, score.groups())
        if h and n and 1 <= h <= 18:
            return {'status': 'candidate', 'operations': [{'path': f'holes.{h}.total', 'value': n, 'status': 'confirmed'}]}
    if not target:
        return {'status': 'clarify', 'operations': []}
    if q and q['field'] in ('putts', 'penalties', 'total'):
        count = re.fullmatch(r'\s*' + number + r'(?:推|杆)?[。！!\s]*', text)
        if count:
            return {'status': 'candidate', 'operations': [{'path': target + '.' + q['field'], 'value': numeral(count.group(1)), 'status': 'confirmed'}]}
    clubs = list(re.finditer(r'一号木|[一二三四五六七八九1-9](?:号)?(?:木|铁|混合杆)', text))
    def club(m):
        word = m.group()
        n = numeral(word[0])
        return 'driver' if n == 1 and '木' in word else str(n) + ('w' if '木' in word else 'h' if '混合杆' in word else 'i')
    if target.startswith('shots.') and clubs:
        if len(clubs) == 2 and re.fullmatch(r'本来想' + re.escape(clubs[0].group()) + r'[，,]?后来打了' + re.escape(clubs[1].group()) + r'[。！!]*', text):
            ops = [{'path': target + '.planned_club', 'value': club(clubs[0]), 'status': 'confirmed'},
                   {'path': target + '.actual_club', 'value': club(clubs[1]), 'status': 'confirmed'}]
        elif len(clubs) == 2 and re.fullmatch(r'不是' + re.escape(clubs[0].group()) + r'[，,]?是' + re.escape(clubs[1].group()) + r'[。！!]*', text):
            ops = [{'path': target + '.actual_club', 'value': club(clubs[-1]), 'status': 'confirmed'}]
        elif len(clubs) == 1 and (re.fullmatch(r'\s*' + re.escape(clubs[0].group()) + r'[。！!\s]*', text) and q and q['field'] == 'actual_club'):
            ops = [{'path': target + '.actual_club', 'value': club(clubs[0]), 'status': 'confirmed'}]
    return {'status': 'candidate' if ops else 'unresolved', 'operations': ops}


def missing_score_question(state, hole, par=None):
    """Suggest one missing field. Host still obtains proactive consent/quiet gate.
    No inference of strokes or automatic persistence.
    """
    require(type(hole) is int and 1 <= hole <= 18, 'invalid hole')
    if any(q['status'] == 'pending' for q in state['questions'].values()):
        return None
    if fact_value(state, 'context.quiet', False) or fact_value(state, 'context.preparing', False):
        return None
    total = fact_value(state, f'holes.{hole}.total')
    if total is None:
        return 'total'
    putts = valid_ref(state, f'holes.{hole}.putts')
    if not putts or putts['status'] == 'unknown':
        return 'putts'
    if par is not None:
        require(type(par) is int and 3 <= par <= 6, 'invalid par')
        penalty = valid_ref(state, f'holes.{hole}.penalties')
        if total - par >= 2 and (not penalty or penalty['status'] == 'unknown'):
            return 'penalties'
    return None


def record_distance(engine, round_id, command_id, derived_id, start_path, end_path, evidence):
    """Compute using existing shot gate. Host supplies explicit single-shot link.
    Stores measured total only, never carry. Requires confirmed endpoint facts.
    """
    from shot_evidence import assess
    s = engine.state(round_id)
    start, end = valid_ref(s, start_path), valid_ref(s, end_path)
    require(start and end and start_path.endswith('.position') and end_path.endswith('.position'), 'valid endpoint facts required')
    require(start['status'] == end['status'] == 'confirmed', 'confirmed endpoints required')
    event = dict(evidence, start=start['value'], end=end['value'], club_confirmed=False, club_id=None)
    result = assess(event)
    require(result['total_horizontal_m'] is not None, 'single-shot distance evidence incomplete: ' + ','.join(result['missing_fields']))
    return engine.command(round_id, command_id, 'derive', dict(id=derived_id, kind='distance',
        deps={start_path: start['version'], end_path: end['version']},
        algorithm_version='shot-evidence-0.1.0', value=result), expected_version=s['version'])
