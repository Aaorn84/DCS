"""Normalized candidate attribution. No ASR, arbitrary NLP, or long-term training.
State is a projection of the parent Engine's append-only transactional commands.
"""
import copy
import hashlib
import re
from round_state import require, StateError, canonical, fact_value, invalidate, score_check, field

VERSION = '0.1.0'
VOICE_TYPES = {'fact_request', 'player_intent', 'decision_commitment', 'execution_report',
 'shot_outcome', 'feel_or_cause', 'correction', 'score_report', 'state_transition',
 'interaction_override', 'companion_dialogue'}
INGRESS_TYPES = {'system_advice', 'gps_context', 'course_context'}
STAGES = {'system_advice':'advice', 'player_intent':'intent', 'decision_commitment':'decision',
 'execution_report':'execution', 'shot_outcome':'outcome', 'feel_or_cause':'cause', 'gps_context':'gps'}
EFFECTS = ('club', 'target', 'route', 'score', 'hole_state', 'learning', 'safety')


def chain_state(s):
    return s.setdefault('shot_chain', {'shots': {}, 'nodes': {}, 'events': {},
        'active_shot': None, 'active_hole': None, 'pending_question': None,
        'interaction': {'mode':'normal', 'quiet_remaining':None}})


def node_live(s, node):
    return node and node.get('valid',True) and node['status'] not in ('retracted','superseded','conflict') and all(
        s['evidence'].get(e, {}).get('active') and s['evidence'][e]['phase']=='final'
        for e in node['evidence_ids']) and all(
            (s['evidence'].get(k[9:],{}).get('active') and s['evidence'][k[9:]]['revision']+1==v)
            for k,v in node.get('deps',{}).items())


def assess(candidates, current_action=True):
    """Compare consequences independently of ASR confidence; never pick by score."""
    if len(candidates) == 1:
        return {'level':'low','reason':'single_candidate','difference':None}
    if not all(isinstance(c.get('effects'),dict) and all(k in c['effects'] for k in EFFECTS) for c in candidates):
        return {'level':'high' if current_action else 'medium','reason':'impact_unknown','difference':'meaning'}
    for key in ('shot_id','hole','stroke_number'):
        if len({canonical(c.get(key)) for c in candidates}) > 1:
            return {'level':'high' if current_action else 'medium','reason':'attribution_changes','difference':key}
    for key in ('club','target','route','total','putts','penalties','relative'):
        if len({canonical(c.get('value',{}).get(key)) for c in candidates})>1:
            return {'level':'high' if current_action else 'medium','reason':'direct_value_changes','difference':'score' if key in ('total','putts','penalties','relative') else key}
    differences = [key for key in EFFECTS if len({canonical(c['effects'][key]) for c in candidates})>1]
    if not differences:
        return {'level':'low','reason':'same_strategy_consequences','difference':None}
    return {'level':'high' if current_action else 'medium','reason':'consequences_change','difference':differences[0]}


def value_schema(stage, v):
    require(isinstance(v,dict), 'structured stage value required')
    allowed = {
      'advice': {'club','target','route','style'}, 'intent': {'club','target','route','style'},
      'decision': {'club','target','route','style'}, 'execution': {'club','style'},
      'outcome': {'longitudinal','lateral','lie'}, 'cause': {'self_report'},
      'gps': {'start','end','single_stroke_confirmed','intervening_strokes','relief_or_provisional','gap_open','max_position_error_sum_m','hole'},
    }
    require(stage in allowed and bool(v) and set(v)<=allowed[stage], 'unsupported stage fields')
    if 'club' in v:
        field('shots.schema.actual_club',v['club'],'confirmed')
    for key in ('target','route','style','self_report'):
        if key in v: require(isinstance(v[key],str) and 0<len(v[key])<=500, 'invalid stage text')
    if 'longitudinal' in v: require(v['longitudinal'] in ('short','long','on_target','unknown'), 'invalid longitudinal result')
    if 'lateral' in v: require(v['lateral'] in ('left','right','on_line','unknown'), 'invalid lateral result')
    if 'lie' in v: require(v['lie'] in ('fairway','rough','bunker','water','green','ob','unknown'), 'invalid lie result')
    if stage=='gps':
        from shot_evidence import position
        for key in ('start','end'):
            if key in v: position(v[key])
        if 'hole' in v: require(type(v['hole']) is int and 1<=v['hole']<=18, 'invalid GPS candidate hole')


def reduce_event(s, e, seq, now):
    ch = chain_state(s)
    require(isinstance(e,dict), 'normalized event object required')
    eid = e.get('event_id')
    require(isinstance(eid,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]{1,100}',eid)), 'invalid normalized event id')
    digest = hashlib.sha256(canonical(e).encode()).hexdigest()
    if eid in ch['events']:
        require(ch['events'][eid]['digest']==digest, 'event id reused with different content')
        return dict(ch['events'][eid]['result'], duplicate=True)
    require(e.get('phase','final')=='final','only final normalized events are accepted')
    typ, source = e.get('type'), e.get('source')
    require(typ in VOICE_TYPES|INGRESS_TYPES, 'unsupported event taxonomy')
    require(source in ('voice','gps','course','user_correction','system'), 'invalid source')
    require(typ not in VOICE_TYPES or source in ('voice','user_correction'), 'voice taxonomy needs voice source')
    require(typ!='system_advice' or source=='system', 'advice must be system-origin')
    require(typ!='gps_context' or source=='gps', 'GPS context needs GPS source')
    require(typ!='course_context' or source=='course', 'course context needs course source')
    from datetime import datetime
    try:
        stamp=datetime.fromisoformat(e['occurred_at'].replace('Z','+00:00'))
        require(stamp.tzinfo is not None,'event time requires timezone')
    except (KeyError,ValueError,TypeError) as exc:
        raise StateError('invalid event time') from exc
    confidence=e.get('confidence',{'asr':None,'attribution':None})
    require(isinstance(confidence,dict) and set(confidence)<= {'asr','attribution'}, 'separate confidence dimensions required')
    for n in confidence.values():
        require(n is None or (type(n) in (int,float) and 0<=n<=1), 'confidence must be 0..1 or unknown')
    # Record a source event without advancing a second aggregate transaction/version.
    evidence_id='chain-'+eid+':1'
    require(evidence_id not in s['evidence'],'normalized evidence id collision')
    s['evidence'][evidence_id]=dict(id='chain-'+eid,revision=1,phase='final',source={'voice':'user','user_correction':'user','system':'sensor'}.get(source,source),
        observed_at=e['occurred_at'],received_at=now,active=True,normalized=copy.deepcopy(e))

    def finish(action, reason, level='low', question=None, **extra):
        result={'action':action,'reason':reason,'impact':level,'question':question, 'event_id':eid,
                'long_term_model_updated':False, 'status':'conflict' if 'conflict' in reason else ('candidate' if action in ('defer','clarify') else 'confirmed'), **extra}
        ch['events'][eid]={'digest':digest,'input':copy.deepcopy(e),'result':copy.deepcopy(result),'version':seq}
        invalidate(s)
        return result

    def unresolved(cands, impact, reason=None):
        basis={sid:copy.deepcopy(ch['shots'][sid]['slots']) for sid in {c.get('shot_id') for c in cands} if sid in ch['shots']}
        quiet=fact_value(s,'context.quiet',False) or fact_value(s,'context.preparing',False)
        restricted=ch['interaction']['mode']=='scores_only' and typ!='score_report'
        existing=ch['pending_question'] or any(q['status']=='pending' for q in s['questions'].values())
        if impact['level']=='high' and not quiet and not restricted and not existing:
            prompts={'shot_id':'你说的是哪一杆？','hole':'你说的是哪一洞？','stroke_number':'你说的是这洞第几杆？',
                     'club':'实际用的是哪支杆？','target':'你最终选的是哪个目标？',
                     'route':'你最终选的是哪条路线？','score':'这项成绩实际是多少？',
                     'safety':'当前需要按哪种现场情况处理？','meaning':'这句话具体指哪一种情况？'}
            q={'id':eid+'-question','event_id':eid,'text':('这一洞标准杆是多少？' if impact['reason']=='standard_par_unknown' else '你指的是哪个目标？' if typ=='fact_request' else prompts.get(impact['difference'],'你说的是哪一种情况？'))}
            ch['pending_question']=q
            return finish('clarify',reason or impact['reason'],impact['level'],question=q,candidates=cands,read_basis=basis)
        return finish('defer',reason or impact['reason'],impact['level'],candidates=cands,read_basis=basis)

    if e.get('resolves_event_id'):
        original=ch['events'].get(e['resolves_event_id'])
        require(original and original['result']['action'] in ('defer','clarify') and e.get('explicit') is True,
                'known pending interpretation and explicit resolution required')
        require(typ==original['input']['type'],'resolution event type mismatch')
        old=original['result'].get('candidates',[])
        chosen=e.get('candidates',[])
        require(len(chosen)==1 and any(canonical(chosen[0])==canonical(c) for c in old),'resolution must select an unchanged candidate')
        require(all(ch['shots'].get(sid,{}).get('slots')==slots for sid,slots in original['result'].get('read_basis',{}).items()),'stale ambiguity resolution')
        if ch['pending_question'] and ch['pending_question']['event_id']==e['resolves_event_id']:
            ch['pending_question']=None
    if typ=='companion_dialogue':
        return finish('commit','dialogue_only_no_round_facts')
    if typ=='fact_request':
        cs=e.get('candidates',[])
        require(isinstance(cs,list) and cs and all(isinstance(c,dict) for c in cs), 'request candidates required')
        report=assess(cs,e.get('current_action',True))
        if len(cs)>1:return unresolved(cs,report)
        return finish('commit','request_logged_without_shot_facts',request=cs[0])
    if typ=='state_transition':
        v=e.get('value',{})
        require(e.get('explicit') is True, 'transition requires explicit normalized evidence')
        if v.get('kind')=='open_shot':
            sid,hole,ordinal=v.get('shot_id'),v.get('hole'),v.get('stroke_number')
            require(isinstance(sid,str) and bool(re.fullmatch(r'[A-Za-z0-9_-]+',sid)) and sid not in ch['shots'], 'new shot id required')
            require(type(hole) is int and 1<=hole<=18, 'shot hole required')
            require(ordinal is None or (type(ordinal) is int and 1<=ordinal<=30), 'stroke number integer or unknown')
            if ordinal is not None:
                require(not any(x['hole']==hole and x['stroke_number']==ordinal for x in ch['shots'].values()), 'duplicate known stroke ordinal')
            ch['shots'][sid]={'shot_id':sid,'hole':hole,'stroke_number':ordinal,'open':True,'slots':{},'history':[],'learning_candidates':[]}
            ch['active_shot'],ch['active_hole']=sid,hole
        elif v.get('kind') in ('enter_hole','finish_shot','end_round'):
            if v['kind']=='enter_hole':
                hole=v.get('hole');require(type(hole) is int and 1<=hole<=18,'hole required')
                if hole!=ch['active_hole']:
                    ch['active_shot']=None
                    remaining=ch['interaction']['quiet_remaining']
                    if remaining is not None:
                        remaining=max(0,remaining-1);ch['interaction']['quiet_remaining']=remaining or None
                        if remaining==0:
                            s['facts']['context.quiet']=dict(value=False,status='confirmed',version=seq,valid=True,evidence_ids=[evidence_id])
                            ch['interaction']['mode']='normal'
                ch['active_hole']=hole
            elif v['kind']=='finish_shot':
                sid=v.get('shot_id') or ch['active_shot'];require(sid in ch['shots'],'known shot required')
                ch['shots'][sid]['open']=False
            else:
                ch['active_shot']=None
        else:raise StateError('unsupported transition')
        return finish('commit','explicit_transition')
    if typ=='course_context':
        v=e.get('value');require(isinstance(v,dict) and isinstance(v.get('evidence_id'),str),'course evidence reference required')
        ev=s['evidence'].get(v['evidence_id'],{})
        require(ev.get('source')=='course' and ev.get('active') and ev.get('phase')=='final','active course snapshot required')
        ch['course_evidence']=v['evidence_id']
        return finish('commit','course_reference_only')
    if typ=='interaction_override' and e.get('reference')!='previous_decision':
        v=e.get('value',{});mode=v.get('mode')
        require(e.get('explicit') is True and mode in ('quiet_holes','quiet','resume','scores_only','normal'), 'explicit supported override required')
        if mode=='quiet_holes':require(type(v.get('holes')) is int and 1<=v['holes']<=18,'quiet hole count required')
        ch['interaction']={'mode':mode,'quiet_remaining':v['holes'] if mode=='quiet_holes' else None}
        if mode in ('quiet_holes','quiet','resume'):
            s['facts']['context.quiet']=dict(value=mode!='resume',status='confirmed',version=seq,valid=True,evidence_ids=[evidence_id])
        return finish('commit','interaction_only')

    candidates=copy.deepcopy(e.get('candidates',[]))
    require(isinstance(candidates,list) and candidates and all(isinstance(c,dict) for c in candidates),'normalized candidates required')
    candidate_ids=[c.get('id') for c in candidates]
    require(all(isinstance(x,str) and x for x in candidate_ids) and len(set(candidate_ids))==len(candidate_ids),'unique candidate ids required')
    for c in candidates:
        target=ch['nodes'].get(c.get('corrects_node')) if typ=='correction' else None
        if target:
            if c.get('shot_id') is not None:require(c['shot_id']==target['shot_id'],'correction target shot conflict')
            c['shot_id']=target['shot_id']
        if not c.get('shot_id'):
            active=ch['active_shot']
            if active and ch['shots'][active]['open']:c['shot_id']=active
        shot=ch['shots'].get(c.get('shot_id'))
        if shot:
            c.setdefault('hole',shot['hole']);c.setdefault('stroke_number',shot['stroke_number'])
    report=assess(candidates,e.get('current_action',True))
    if len(candidates)>1:return unresolved(candidates,report)
    c=candidates[0]
    if typ=='correction' and c.get('score_target') is not None:
        require(e.get('explicit') is True and e.get('explicit_confirmation') is True,'score correction needs explicit confirmation')
        require(not c.get('corrects_node'),'mixed correction targets rejected')
        target=c['score_target'];hole=target.get('hole');values=c.get('value',{})
        require(type(hole) is int and 1<=hole<=18 and isinstance(values,dict) and values and set(values)<= {'total','putts','penalties'},'exact score target required')
        expected=target.get('read_versions',{})
        paths={f'holes.{hole}.{k}' for k in values}
        from round_state import refs_current
        require(set(expected)==paths and refs_current(s,expected),'stale score correction')
        before={path:copy.deepcopy(s['facts'][path]) for path in paths}
        facts=copy.deepcopy(s['facts'])
        for name,value in values.items():
            path=f'holes.{hole}.{name}';status='unknown' if value is None else 'confirmed';field(path,value,status)
            facts[path]=dict(value=value,status=status,version=seq,valid=True,evidence_ids=[evidence_id])
        score_check(facts);s['facts']=facts
        ch.setdefault('score_revisions',[]).append(dict(event_id=eid,hole=hole,before=before,
            after={path:copy.deepcopy(facts[path]) for path in paths},version=seq))
        return finish('commit','confirmed_score_correction')
    shot=ch['shots'].get(c.get('shot_id'))
    if typ=='score_report' and not shot and type(c.get('hole')) is int and 1<=c['hole']<=18:
        shot={'hole':c['hole']}
    if not shot:return unresolved(candidates,dict(level='high',reason='shot_unknown',difference='shot_id'))
    if c['hole']!=shot['hole'] or (typ!='score_report' and c['stroke_number']!=shot['stroke_number']):
        return unresolved(candidates,dict(level='high',reason='attribution_conflict',difference='shot_id'))
    stage=STAGES.get(typ)
    previous=None
    if typ=='interaction_override':
        require(e.get('reference')=='previous_decision','unsupported decision reference')
        previous=next((ch['nodes'][nid] for nid in reversed(shot['history']) if ch['nodes'][nid]['stage']=='decision' and node_live(s,ch['nodes'][nid])),None)
        if not previous:return unresolved(candidates,dict(level='high',reason='no_valid_decision',difference='meaning'))
        stage='decision';c['value']=copy.deepcopy(previous['value'])
    if typ=='correction':
        previous=ch['nodes'].get(c.get('corrects_node'))
        require(previous and node_live(s,previous) and previous['shot_id']==shot['shot_id'],'live exact correction target required')
        require(e.get('explicit') is True,'explicit correction required')
        require(shot['slots'].get(previous['stage'])==previous['node_id'],'correction target superseded by a later version')
        stage=previous['stage']
        if c.get('retract') is True:
            previous['status']='retracted';previous['valid']=False
            previous['learning_eligibility']['total_distance_candidate']=False
            shot['slots'][stage]=None
            if stage=='execution':
                s['facts'][f"shots.{shot['shot_id']}.actual_club"]=dict(value=None,status='unknown',version=seq,valid=True,evidence_ids=[evidence_id])
            return finish('commit','retracted_stage',node_id=previous['node_id'],shot_id=shot['shot_id'])
        c['value']={**previous['value'],**c.get('value',{})}
    if typ=='score_report':
        # Normalized scores belong to a known hole, but never invent unreported strokes.
        v=c.get('value',{});require(isinstance(v,dict) and v and set(v)<= {'total','putts','penalties','relative'},'score fields required')
        score_evidence=[evidence_id]
        calculation=None
        if 'relative' in v:
            require(type(v['relative']) is int and -5<=v['relative']<=29,'relative score integer required')
            ce=s['evidence'].get(ch.get('course_evidence'),{})
            hole_data=next((h for h in ce.get('data',{}).get('holes',[]) if h.get('number')==shot['hole']),{})
            par=hole_data.get('par')
            if not ce.get('active') or ce.get('phase')!='final' or type(par) is not int or not 3<=par<=6:
                return unresolved(candidates,dict(level='high' if e.get('current_action',True) else 'medium',reason='standard_par_unknown',difference='meaning'))
            total=par+v['relative']
            require('total' not in v or v['total']==total,'relative and total conflict')
            calculation={'relative':v['relative'],'par':par,'total':total,'course_evidence':ch['course_evidence']}
            v={k:x for k,x in v.items() if k!='relative'}|{'total':total}
            score_evidence.append(ch['course_evidence'])
        if e.get('explicit_confirmation') is not True:
            return finish('defer','score_confirmation_required',candidates=candidates,calculation=calculation)
        facts=copy.deepcopy(s['facts'])
        for name,val in v.items():
            path=f"holes.{shot['hole']}.{name}";status='unknown' if val is None else 'confirmed';field(path,val,status)
            facts[path]=dict(value=val,status=status,version=seq,valid=True,evidence_ids=score_evidence if name=='total' else [evidence_id])
        score_check(facts);s['facts']=facts
        return finish('commit','confirmed_score_no_stroke_reconstruction',calculation=calculation)
    require(stage is not None,'stage not mapped')
    value_schema(stage,c.get('value'))
    if stage=='gps' and c['value'].get('hole') not in (None,shot['hole']):
        return unresolved(candidates,dict(level='high',reason='gps_voice_conflict',difference='hole'))
    deps={}
    for ref in c.get('object_refs',[]):
        ev=s['evidence'].get(ref.get('evidence_id'),{})
        require(ev.get('source')=='course' and ev.get('active') and ev.get('phase')=='final','active map object evidence required')
        holes=ev.get('data',{}).get('holes',[])
        require(any(h.get('number')==shot['hole'] and any(o.get('id')==ref.get('object_id') for o in h.get('objects',[])) for h in holes),'course object not in target hole')
        deps['evidence:'+ref['evidence_id']]=ev['revision']+1
    old_id=shot['slots'].get(stage)
    if previous is None and old_id:
        old=ch['nodes'][old_id]
        if node_live(s,old):
            changed=any(k in old['value'] and old['value'][k]!=v for k,v in c['value'].items())
            allowed=(stage in ('intent','decision') and e.get('explicit') is True) or (e.get('resolves_event_id') and e.get('explicit') is True)
            if changed and not allowed:
                return unresolved(candidates,dict(level='high',reason='existing_fact_conflict',difference='club' if stage=='execution' else 'meaning'))
            previous=old
            c['value']={**old['value'],**c['value']}
    nid=eid+'-node'
    if previous:
        previous['status']='superseded'
        previous['learning_eligibility']['total_distance_candidate']=False
    # GPS endpoint evidence is a candidate until link/position gates independently establish it.
    status='candidate' if stage=='gps' else 'confirmed'
    prior_event=c.get('previous_event_id')
    if prior_event is not None:require(prior_event in ch['events'],'previous event must exist')
    if prior_event is None:
        linked=previous
        if linked is None:
            for key in (('execution','outcome','decision','advice') if stage in ('outcome','cause') else ('decision','intent','advice','execution')):
                n=ch['nodes'].get(shot['slots'].get(key))
                if n and node_live(s,n):linked=n;break
        prior_event=linked['event_id'] if linked else None
    node=dict(node_id=nid,event_id=eid,shot_id=shot['shot_id'],hole=shot['hole'],stroke_number=shot['stroke_number'],
        stage=stage,source=source,status=status,valid=True,confidence=confidence,occurred_at=e['occurred_at'],
        previous_event_id=prior_event,version=seq,supersedes=previous['node_id'] if previous else None,supersedes_version=previous['version'] if previous else None,
        value=copy.deepcopy(c['value']),evidence_ids=[evidence_id],deps=deps,
        learning_eligibility={'total_distance_candidate':False,'carry_calibration':False,'long_term_model':False})
    ch['nodes'][nid]=node;shot['slots'][stage]=nid;shot['history'].append(nid)
    if stage=='execution' and 'club' in node['value']:
        s['facts'][f"shots.{shot['shot_id']}.actual_club"]=dict(value=node['value']['club'],status='confirmed',version=seq,valid=True,evidence_ids=[evidence_id])
    # No distribution/club calibration is changed here. Only a reviewable total-distance candidate.
    ex=ch['nodes'].get(shot['slots'].get('execution'));gps=ch['nodes'].get(shot['slots'].get('gps'))
    if ex:ex['learning_eligibility']['total_distance_candidate']=False
    if node_live(s,ex) and node_live(s,gps) and ex['value'].get('club'):
        from shot_evidence import assess as assess_shot
        try:
            result=assess_shot(dict(gps['value'],recording_consent=e.get('recording_consent') is True,club_id=ex['value']['club'],club_confirmed=True))
        except ValueError:
            result={'usable_for_club_total_stats':False}
        if result['usable_for_club_total_stats']:
            lid='learn-'+ex['node_id']+'-'+gps['node_id']
            if lid not in s['derived']:
                s['derived'][lid]=dict(id=lid,kind='learning_candidate',algorithm_version=VERSION,version=seq,valid=True,
                    deps={'chain:'+ex['node_id']:ex['version'],'chain:'+gps['node_id']:gps['version'],**ex['deps'],**gps['deps']},
                    value=dict(club=ex['value']['club'],total_horizontal_m=result['total_horizontal_m'],carry=False,long_term_model=False))
            if lid not in shot['learning_candidates']:shot['learning_candidates'].append(lid)
            ex['learning_eligibility']['total_distance_candidate']=True
    return finish('commit','attributed_stage',node_id=nid,shot_id=shot['shot_id'])


def shot_view(state, shot_id):
    """Auditable complete chain, retaining explicit unknown slots and history."""
    ch=state.get('shot_chain',{})
    shot=ch.get('shots',{}).get(shot_id)
    require(shot is not None,'shot not found')
    result={k:copy.deepcopy(shot[k]) for k in ('shot_id','hole','stroke_number','open')}
    result['chain']={}
    for stage in ('advice','intent','decision','execution','outcome','cause','gps'):
        n=ch['nodes'].get(shot['slots'].get(stage))
        if n and node_live(state,n):result['chain'][stage]=copy.deepcopy(n)
        else:result['chain'][stage]={'status':'unknown','value':None,'historical_node_id':n['node_id'] if n else None}
    result['history']=[copy.deepcopy(ch['nodes'][nid]) for nid in shot['history']]
    result['learning_candidates']=[copy.deepcopy(state['derived'][lid]) for lid in shot['learning_candidates']]
    result['conflicts']=[{'event_id':eid,**copy.deepcopy(e['result'])} for eid,e in ch['events'].items()
        if e['result'].get('status')=='conflict' and any(c.get('shot_id')==shot_id for c in e['result'].get('candidates',[]))]
    return result
