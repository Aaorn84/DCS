"""Deterministic three-input session adapter; synthetic point/bbox geometry only.
No model writes, speech recognition, polygon/OB adjudication or carry inference.
"""
import math
import re
from datetime import datetime
from round_state import reduce, require, StateError, fact_value, valid_ref, attribute, numeral
from shot_evidence import haversine

VERSION = '0.1.0'
N = r'(十八|十七|十六|十五|十四|十三|十二|十一|十|[零一二两三四五六七八九]|\d{1,2})'


def count(s):
    return 0 if s == '零' else numeral(s)


def position(p):
    require(isinstance(p, dict), 'position object required')
    for name, lo, hi in [('latitude', -85, 85), ('longitude', -180, 180), ('accuracy_m', .01, 10000)]:
        require(type(p.get(name)) in (int, float) and math.isfinite(p[name]) and lo <= p[name] <= hi, 'invalid GPS position')
    return p


def course_schema(data):
    require(isinstance(data, dict) and data.get('crs') == 'WGS84' and isinstance(data.get('course_id'), str)
            and data['course_id'] and isinstance(data.get('map_version'), str) and data['map_version'], 'versioned WGS84 course required')
    require(isinstance(data.get('holes'), list) and 0 < len(data['holes']) <= 18, '1..18 holes required')
    seen = set()
    for h in data['holes']:
        require(isinstance(h, dict) and type(h.get('number')) is int and 1 <= h['number'] <= 18
                and h['number'] not in seen and type(h.get('par')) is int and 3 <= h['par'] <= 6, 'invalid or duplicate hole')
        seen.add(h['number'])
        box = h.get('bbox')
        require(isinstance(box, list) and len(box) == 4 and all(type(x) in (int, float) and math.isfinite(x) for x in box), 'bbox required')
        w, south, e, north = box
        require(-180 <= w < e <= 180 and -85 <= south < north <= 85, 'unsupported bbox')
        objects = h.get('objects')
        require(isinstance(objects, list) and 0 < len(objects) <= 100, 'point objects required')
        ids = set()
        for obj in objects:
            require(isinstance(obj, dict) and isinstance(obj.get('id'), str) and obj['id'] and obj['id'] not in ids, 'duplicate or invalid object')
            ids.add(obj['id'])
            require(obj.get('kind') in ('green_center', 'hazard_reference', 'landing_reference', 'ob_reference'), 'unsupported point object')
            position(dict(obj, accuracy_m=1))
    return data


def gps_matches(course, gps):
    matches = []
    # Conservative rectangular uncertainty envelope; no antimeridian geometry.
    dy = gps['accuracy_m'] / 111000
    dx = dy / max(.05, math.cos(math.radians(gps['latitude'])))
    for h in course['holes']:
        w, south, e, north = h['bbox']
        if w <= gps['longitude'] - dx and gps['longitude'] + dx <= e and south <= gps['latitude'] - dy and gps['latitude'] + dy <= north:
            matches.append(h['number'])
    return matches


def reduce_event(s, p, seq, now):
    require(p.get('type') in ('course', 'gps', 'voice'), 'unsupported session event type')
    require(isinstance(p.get('event_id'), str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}', p['event_id'])), 'invalid event id')
    event = p['event_id']
    base = s['version']
    session = s.setdefault('session', {'course_evidence': None, 'gps_evidence': None,
        'draft': None, 'question_id': None, 'pending_patch': None, 'last_patch': None})

    def step(kind, payload):
        # Nested steps are one aggregate transaction and one replayable session event.
        r = reduce(s, kind, payload, seq, now)
        s['version'] = base
        return r

    def evidence(source, data=None):
        return step('evidence', dict(id=event, revision=p.get('revision', 1), phase=p.get('phase', 'final'),
                    source=source, observed_at=p['observed_at'], **(data or {})))['evidence_id']

    def active_evidence(eid):
        e = s['evidence'].get(eid)
        return e if e and e['active'] and e['phase'] == 'final' else None

    def say(text, **extra):
        return {'text': text, 'saved': False, **extra}

    def close_question():
        qid = session['question_id']
        if qid and s['questions'].get(qid, {}).get('status') == 'pending':
            step('answer', {'id': qid})
        session['question_id'] = None

    def ask(field, text):
        close_question()
        if fact_value(s, 'context.quiet', False) or fact_value(s, 'context.preparing', False):
            return say('', deferred=True)
        qid = event + '-question'
        step('question', dict(id=qid, target=f"holes.{session['draft']['hole']}", field=field, deps={}))
        session['question_id'] = qid
        session['draft']['awaiting'] = field
        return say(text, question_id=qid)

    def finish_draft():
        d = session['draft']
        if 'putts' not in d:
            return ask('putts', '这一洞几推？')
        ce = active_evidence(session['course_evidence'])
        par = next((h['par'] for h in ce['data']['holes'] if h['number'] == d['hole']), None) if ce else None
        if par is not None and d['total'] - par >= 2 and 'penalties' not in d:
            return ask('penalties', '这一洞有OB、下水或其他罚杆吗？告诉我罚杆数，不清楚也可以跳过。')
        if sum(d.get(k) or 0 for k in ('putts', 'penalties')) > d['total']:
            return ask('putts', '推杆和罚杆合计超过了总杆。这洞实际几推？')
        close_question()
        ops = [dict(path=f"holes.{d['hole']}.{k}", value=d.get(k), status='unknown' if d.get(k) is None else 'confirmed') for k in ('total', 'putts', 'penalties')]
        patch_id = event + '-score'
        step('propose', dict(id=patch_id, base_version=base, evidence_ids=d['evidence_ids'], operations=ops))
        session['pending_patch'] = patch_id
        d['awaiting'] = 'confirm'
        def describe(k):
            return '未知' if d.get(k) is None else str(d[k])
        return say(f"第{d['hole']}洞{d['total']}杆（已含罚杆），{describe('putts')}推、罚杆{describe('penalties')}。确认记录吗？", confirmation=dict(patch_id=patch_id, version=seq))

    if p['type'] == 'course':
        require(p.get('phase', 'final') == 'final', 'course snapshots must be final')
        data = course_schema(p.get('data'))
        eid = evidence('course', {'data': data})
        session['course_evidence'] = eid
        # Changing snapshot IDs also invalidates all computations that read the selected course.
        s['facts']['context.course_snapshot'] = dict(value=eid, status='confirmed', valid=True, version=seq, evidence_ids=[eid])
        from round_state import invalidate
        invalidate(s)
        return say('', course_loaded=True)

    if p['type'] == 'gps':
        require(p.get('phase', 'final') == 'final', 'GPS fixes must be final')
        gps = position(p.get('data'))
        eid = evidence('gps', {'data': gps})
        ce = active_evidence(session['course_evidence'])
        require(ce is not None, 'load course before GPS')
        observed = datetime.fromisoformat(p['observed_at'].replace('Z', '+00:00')).timestamp()
        fresh = -5 <= now - observed <= 60 and gps['accuracy_m'] <= 30
        old = active_evidence(session['gps_evidence'])
        if old:
            previous = datetime.fromisoformat(old['observed_at'].replace('Z', '+00:00')).timestamp()
            if observed < previous:
                return say('', ignored=True, reason='out_of_order_gps')
        session['gps_evidence'] = eid
        matches = gps_matches(ce['data'], gps)
        # A geometric match is a candidate, not proof the previous hole was completed.
        previous_hole = fact_value(s, 'context.active_hole')
        if fresh and len(matches) == 1:
            if previous_hole != matches[0]:
                s['evidence'][eid]['reliable_transition'] = True
                step('gps_transition', dict(evidence_id=eid, hole=matches[0]))
        from round_state import invalidate
        s['facts']['context.device_position'] = dict(value=dict(gps, observed_at=p['observed_at']), status='confirmed', valid=True, version=seq, evidence_ids=[eid])
        invalidate(s)
        extra = dict(candidate_holes=matches, usable_for_distance=fresh, ball_position_confirmed=False)
        if (fresh and len(matches) == 1 and previous_hole is not None and previous_hole != matches[0]
            and fact_value(s, 'preferences.proactive') is True
            and not fact_value(s, 'context.quiet', False) and not fact_value(s, 'context.preparing', False)
            and fact_value(s, f'holes.{previous_hole}.total') is None
            and not session['draft'] and not any(q['status'] == 'pending' for q in s['questions'].values())):
            qid = event + '-previous-score'
            step('question', dict(id=qid, target=f'holes.{previous_hole}', field='total', deps={}, proactive=True))
            session['question_id'] = qid
            session['score_target'] = previous_hole
            return say(f'到了下一洞附近，上一洞一共几杆？', question_id=qid, **extra)
        return say('', **extra)

    require(isinstance(p.get('text'), str) and 0 < len(p['text'].strip()) <= 2000, 'voice text required')
    eid = evidence('user', {'text': p['text']})
    if p.get('phase', 'final') != 'final':
        return say('', partial=True)
    text = p['text'].strip()
    clean = re.sub(r'[，。！？!?\s]', '', text)
    if clean in ('安静', '停一下', '先安静'):
        step('control', dict(evidence_id=eid, path='context.quiet', value=True, explicit=True))
        return say('', pause=True)
    if clean in ('换洞时提醒记分', '不要主动提醒'):
        step('control', dict(evidence_id=eid, path='preferences.proactive', value=clean == '换洞时提醒记分', explicit=True))
        return say('好，按这个约定来。')
    if clean in ('继续', '恢复语音'):
        step('control', dict(evidence_id=eid, path='context.quiet', value=False, explicit=True))
        return say('我在，需要时叫我。')
    # Direct requests may be displayed; ambient GPS never resumes voice. No unsolicited TTS flag.
    if clean in ('先不记', '取消记录', '跳过这洞'):
        close_question()
        session['draft'] = session['pending_patch'] = None
        session['score_target'] = None
        return say('好，先留空。')
    if clean in ('撤销上一条记分', '撤销刚才的记分'):
        require(session['last_patch'] is not None, 'no committed score to retract')
        step('retract', dict(id=session['last_patch'], explicit=True))
        session['last_patch'] = None
        return say('已撤销上一条记分。', retracted=True)
    if clean in ('确认', '确认记录', '确认保存'):
        pid = session['pending_patch']
        require(pid is not None and session['draft'] is not None, 'no pending score confirmation')
        patch = s['patches'][pid]
        if patch['base_version'] != base:
            # Re-read and re-propose, require a new confirmation after any intervening state write.
            return finish_draft()
        step('confirm', dict(id=pid, confirmation_version=patch['base_version'], explicit=True))
        session['last_patch'] = pid
        session['draft'] = session['pending_patch'] = None
        return say('已确认并记录。', saved=True, patch_id=pid)

    if clean in ('还有多少', '还有多少码', '还有多少米'):
        ce, ge = active_evidence(session['course_evidence']), active_evidence(session['gps_evidence'])
        require(ce and ge, 'course and GPS required for distance')
        observed = datetime.fromisoformat(ge['observed_at'].replace('Z', '+00:00')).timestamp()
        require(-5 <= now - observed <= 60 and ge['data']['accuracy_m'] <= 30, 'GPS stale or inaccurate')
        hole = fact_value(s, 'context.active_hole')
        matches = gps_matches(ce['data'], ge['data'])
        require(matches == [hole], 'hole matching ambiguous; confirm location before distance')
        h = next(h for h in ce['data']['holes'] if h['number'] == hole)
        targets = [o for o in h['objects'] if o['kind'] == 'green_center']
        require(len(targets) == 1, 'unique green center required')
        target = targets[0]
        meters = haversine(ge['data'], target)
        deps = {'context.course_snapshot': s['facts']['context.course_snapshot']['version'],
                'context.device_position': s['facts']['context.device_position']['version'],
                'evidence:' + session['course_evidence']: ce['revision'] + 1,
                'evidence:' + session['gps_evidence']: ge['revision'] + 1}
        step('derive', dict(id=event + '-target-distance', kind='distance', deps=deps,
             algorithm_version='point-haversine-0.1.0', value=dict(meters=meters,
             target_id=target['id'], target='green_center', origin='device_gps',
             accuracy_m=ge['data']['accuracy_m'], carry=False, hole=hole)))
        amount = round(meters / .9144) if '码' in clean else round(meters)
        unit = '码' if '码' in clean else '米'
        return say(f'从当前设备位置到果岭中心约{amount}{unit}，不是旗杆距离。', distance=dict(meters=meters, origin='device_gps', target='green_center', carry=False))

    # A small grammar is deliberate: unsupported or uncertain statements remain unrecorded.
    match = re.fullmatch(r'(?:(?:' + N + r')号洞|这洞|本洞)?' + N + r'杆(?:[，,]' + N + r'推)?(?:[，,]' + N + r'罚(?:杆)?)?[。!！]?', text)
    # Capturing groups: hole, total, putts, penalties.
    if match:
        groups = match.groups()
        explicit_hole, total, putts, penalties = groups
        hole = count(explicit_hole) if explicit_hole else (session.get('score_target') or fact_value(s, 'context.active_hole'))
        require(type(hole) is int and 1 <= hole <= 18, 'hole unknown; say explicit hole number')
        require(1 <= count(total) <= 30, 'invalid total')
        d = dict(hole=hole, total=count(total), evidence_ids=[eid])
        if putts is not None:
            d['putts'] = count(putts)
        if penalties is not None:
            d['penalties'] = count(penalties)
        close_question()
        session['draft'], session['pending_patch'] = d, None
        session['score_target'] = None
        return finish_draft()
    if session['draft'] and session['draft'].get('awaiting') in ('putts', 'penalties'):
        d = session['draft']; field = d['awaiting']
        value_match = re.fullmatch(N + (r'(?:推)?' if field == 'putts' else r'(?:罚|罚杆)?'), clean)
        if clean in ('不知道', '不清楚', '跳过这一项'):
            value = None
        elif field == 'penalties' and clean in ('没有罚杆', '没罚杆', '无罚杆'):
            value = 0
        elif value_match:
            value = count(value_match.group(1))
        else:
            return say('这一项没有听清，也可以说“不清楚”。')
        require(value is None or 0 <= value <= 30, 'invalid count')
        close_question(); d[field] = value; d['evidence_ids'].append(eid)
        session['pending_patch'] = None
        return finish_draft()
    result = attribute(text, s, question_id=p.get('question_id'), shot_id=p.get('shot_id'))
    return say('这句话还没有生成可确认的记录。', attribution=result, unsupported=True)
