import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from round_state import Engine, StateError
from shot_chain import VOICE_TYPES

TIME='2026-11-06T08:00:00+08:00'


def effects(**kw):
    return dict(club='7i',target='center',route='straight',score='unchanged',
                hole_state='unchanged',learning='blocked',safety='unchanged',**{})|kw


class ChainTests(unittest.TestCase):
    def setUp(self):
        self.e=Engine(':memory:','alice');self.e.create('r');self.n=0
    def tearDown(self):self.e.close()
    def event(self,type,source='voice',candidates=None,**extra):
        self.n+=1
        e=dict(event_id='e'+str(self.n),type=type,source=source,occurred_at=TIME,
               confidence=dict(asr=.95,attribution=.9))|extra
        if candidates is not None:e['candidates']=candidates
        self.last=e
        return self.e.command('r',e['event_id'],'attribution_event',e,now=100)
    def open(self,sid='s1',hole=1,ordinal=1):
        return self.event('state_transition',explicit=True,value=dict(kind='open_shot',shot_id=sid,hole=hole,stroke_number=ordinal))
    def stage(self,type,value,source='voice',**extra):
        return self.event(type,source,[dict(id='c',value=value)],**extra)
    def node(self,result):return self.e.state('r')['shot_chain']['nodes'][result['node_id']]
    def setup_shot(self,club='7i'):
        self.open();return self.stage('system_advice',dict(club=club,target='green center'),source='system')
    def test_still_used_7i_binds_unfinished_shot_and_previous_advice(self):
        advice=self.setup_shot()
        r=self.stage('execution_report',dict(club='7i'),text='我还是用了7铁')
        n=self.node(r)
        self.assertEqual(n['shot_id'],'s1');self.assertEqual(n['previous_event_id'],advice['event_id'])
        self.assertNotIn('club_bag',self.e.state('r'))
        self.assertFalse(n['learning_eligibility']['long_term_model'])
    def test_outcome_and_self_reported_cause_same_shot(self):
        self.setup_shot();self.stage('execution_report',dict(club='7i'))
        a=self.stage('shot_outcome',dict(longitudinal='short'),text='有点短')
        b=self.stage('shot_outcome',dict(lateral='right'),text='右边')
        self.assertEqual(self.node(b)['value'],dict(longitudinal='short',lateral='right'))
        self.assertEqual(self.node(a)['status'],'superseded')
        c=self.stage('feel_or_cause',dict(self_report='打厚了'))
        self.assertEqual(self.node(c)['shot_id'],'s1')
        self.assertFalse(self.node(c)['learning_eligibility']['long_term_model'])
    def gps(self,**changes):
        def point(lon,t):return dict(latitude=31,longitude=lon,accuracy_m=1,crs='WGS84',hole_id='1',ball_position_confirmed=True,observed_at=t)
        value=dict(start=point(121,'2026-11-06T00:00:00Z'),end=point(121.002,'2026-11-06T00:04:00Z'),
                   single_stroke_confirmed=True,intervening_strokes=0,relief_or_provisional=False,gap_open=False,max_position_error_sum_m=10)
        value.update(changes)
        return self.stage('gps_context',value,source='gps',recording_consent=True)
    def test_8i_to_9i_retracts_learning_preserves_gps_and_score(self):
        self.setup_shot('8i');old=self.stage('execution_report',dict(club='8i'));gps=self.gps()
        self.event('score_report',candidates=[dict(id='score',hole=1,value=dict(total=5,putts=2))],explicit_confirmation=True)
        s=self.e.state('r');old_learning=s['shot_chain']['shots']['s1']['learning_candidates'][-1]
        corrected=self.event('correction',source='user_correction',explicit=True,recording_consent=True,
               candidates=[dict(id='fix',corrects_node=old['node_id'],value=dict(club='9i'))],text='刚才不是8铁，是9铁')
        s=self.e.state('r')
        self.assertEqual(s['shot_chain']['nodes'][old['node_id']]['status'],'superseded')
        self.assertEqual(self.node(corrected)['supersedes'],old['node_id'])
        self.assertFalse(s['derived'][old_learning]['valid'])
        self.assertEqual(s['shot_chain']['nodes'][gps['node_id']]['value'],self.node(gps)['value'])
        self.assertEqual(s['facts']['holes.1.total']['value'],5)
        self.assertEqual(s['facts']['shots.s1.actual_club']['value'],'9i')
        current=s['shot_chain']['shots']['s1']['learning_candidates'][-1]
        self.assertEqual(s['derived'][current]['value']['club'],'9i')
        self.assertFalse(s['derived'][current]['value']['carry'])
    def test_previous_valid_decision_not_previous_execution(self):
        self.setup_shot();old=self.stage('decision_commitment',dict(club='8i'),explicit=True)
        latest=self.stage('decision_commitment',dict(club='7i'),explicit=True)
        r=self.event('interaction_override',reference='previous_decision',candidates=[dict(id='old',value={})],text='按原来的')
        self.assertEqual(self.node(r)['value']['club'],'7i')
        self.assertEqual(self.node(r)['previous_event_id'],latest['event_id'])
        self.assertEqual(self.node(old)['status'],'superseded')
        self.assertNotIn('shots.s1.actual_club',self.e.state('r')['facts'])
    def test_two_bunkers_change_club_clarify(self):
        self.open()
        r=self.event('fact_request',candidates=[dict(id='near',distance=110,effects=effects(club='8i')),
                                              dict(id='far',distance=140,effects=effects(club='6i'))])
        self.assertEqual(r['action'],'clarify');self.assertEqual(r['impact'],'high')
        self.assertEqual(r['question']['text'],'你指的是哪个目标？')
    def test_equivalent_strategy_no_interruption_and_no_exact_distance(self):
        r=self.event('fact_request',candidates=[dict(id='a',distance=110,effects=effects()),dict(id='b',distance=112,effects=effects())])
        self.assertEqual(r['action'],'defer');self.assertEqual(r['impact'],'low');self.assertIsNone(r['question'])
        self.assertEqual(self.e.state('r')['facts'],{})
    def test_gps_voice_conflict_retained_not_overwritten(self):
        self.open()
        r=self.gps(hole=2)
        self.assertEqual(r['status'],'conflict');self.assertEqual(r['reason'],'gps_voice_conflict')
        self.assertEqual(self.e.state('r')['shot_chain']['shots']['s1']['hole'],1)
        self.assertEqual(r['candidates'][0]['value']['hole'],2)
    def test_missing_endpoints_do_not_erase_execution_or_invent_distance(self):
        self.open();self.stage('execution_report',dict(club='7i'))
        r=self.stage('gps_context',dict(start=None,end=None),source='gps',recording_consent=True)
        s=self.e.state('r');self.assertFalse(s['derived']);self.assertEqual(s['facts']['shots.s1.actual_club']['value'],'7i')
        self.assertEqual(self.node(r)['status'],'candidate')
    def test_missing_club_never_uses_advice_as_actual(self):
        self.setup_shot();self.gps()
        self.assertFalse(self.e.state('r')['derived']);self.assertNotIn('shots.s1.actual_club',self.e.state('r')['facts'])
    def test_duplicate_event_does_not_add_shot_or_node(self):
        r=self.open();event=copy.deepcopy(self.last)
        self.assertEqual(r,self.e.command('r',event['event_id'],'attribution_event',event,now=200))
        again=self.e.command('r','transport-retry','attribution_event',event)
        self.assertTrue(again['duplicate']);self.assertEqual(len(self.e.state('r')['shot_chain']['shots']),1)
        event['value']['hole']=2
        with self.assertRaises(StateError):self.e.command('r','other','attribution_event',event)
    def test_correction_after_hole_change_keeps_current_hole(self):
        self.setup_shot('8i');old=self.stage('execution_report',dict(club='8i'))
        self.event('state_transition',explicit=True,value=dict(kind='enter_hole',hole=2))
        self.open('s2',2,1)
        r=self.event('correction',source='user_correction',explicit=True,candidates=[dict(id='fix',corrects_node=old['node_id'],value=dict(club='9i'))])
        self.assertEqual(self.node(r)['hole'],1);self.assertEqual(self.e.state('r')['shot_chain']['active_hole'],2)
    def test_at_most_one_outstanding_question(self):
        a=self.stage('execution_report',dict(club='7i'))
        b=self.stage('shot_outcome',dict(lateral='right'))
        self.assertIsNotNone(a['question']);self.assertIsNone(b['question']);self.assertEqual(b['action'],'defer')
    def test_temporary_outcome_does_not_change_long_term_or_carry(self):
        self.setup_shot();self.stage('execution_report',dict(club='7i'))
        self.stage('shot_outcome',dict(longitudinal='short',lateral='right'))
        s=self.e.state('r');self.assertFalse(s['derived'])
        self.assertEqual(set(s['facts']),{'shots.s1.actual_club'})
        self.assertFalse(any(n['learning_eligibility']['carry_calibration'] for n in s['shot_chain']['nodes'].values()))
    def test_medium_impact_defers_until_later(self):
        self.open()
        r=self.event('execution_report',current_action=False,candidates=[dict(id='a',value=dict(club='7i'),effects=effects(club='7i')),
                                                                     dict(id='b',value=dict(club='8i'),effects=effects(club='8i'))])
        self.assertEqual(r['impact'],'medium');self.assertEqual(r['action'],'defer');self.assertIsNone(r['question'])
    def test_high_impact_while_quiet_is_deferred(self):
        self.open();self.event('interaction_override',explicit=True,value=dict(mode='quiet'))
        r=self.event('fact_request',candidates=[dict(id='a',effects=effects(safety='water')),dict(id='b',effects=effects(safety='clear'))])
        self.assertEqual(r['impact'],'high');self.assertEqual(r['action'],'defer');self.assertIsNone(r['question'])
    def test_explicit_resolution_selects_original_candidate(self):
        self.open()
        r=self.event('execution_report',candidates=[dict(id='a',value=dict(club='7i'),effects=effects(club='7i')),
                                                  dict(id='b',value=dict(club='8i'),effects=effects(club='8i'))])
        resolved=self.event('execution_report',explicit=True,resolves_event_id=r['event_id'],candidates=[r['candidates'][0]])
        self.assertEqual(resolved['action'],'commit');self.assertEqual(self.node(resolved)['value']['club'],'7i')
        self.assertIsNone(self.e.state('r')['shot_chain']['pending_question'])
    def test_companion_dialogue_never_becomes_club_or_score(self):
        self.event('companion_dialogue',text='昨天聊到我买了7铁，我朋友打了八杆')
        s=self.e.state('r');self.assertFalse(s['facts']);self.assertFalse(s['shot_chain']['nodes'])
    def test_confidence_cannot_resolve_different_safety(self):
        self.open()
        r=self.event('fact_request',confidence=dict(asr=1,attribution=1),candidates=[dict(id='a',effects=effects(safety='water')),dict(id='b',effects=effects(safety='clear'))])
        self.assertEqual(r['action'],'clarify')
    def test_hole_only_score_does_not_require_fake_shot(self):
        r=self.event('score_report',explicit_confirmation=True,candidates=[dict(id='score',hole=2,value=dict(total=6,putts=None))])
        self.assertEqual(r['action'],'commit');self.assertFalse(self.e.state('r')['shot_chain']['shots'])
        self.assertIsNone(self.e.state('r')['facts']['holes.2.putts']['value'])
    def test_score_unconfirmed_never_writes_facts(self):
        r=self.event('score_report',candidates=[dict(id='score',hole=2,value=dict(total=6))])
        self.assertEqual(r['action'],'defer');self.assertFalse(self.e.state('r')['facts'])
    def test_course_object_and_endpoints_join_with_audit_refs(self):
        data=dict(course_id='c',map_version='1',crs='WGS84',holes=[dict(number=1,objects=[dict(id='bunker',kind='hazard_reference')])])
        self.e.command('r','map','evidence',dict(id='map',revision=1,phase='final',source='course',observed_at=TIME,data=data))
        self.open()
        r=self.event('system_advice','system',[dict(id='c',value=dict(club='7i',target='left of bunker'),object_refs=[dict(evidence_id='map:1',object_id='bunker')])])
        self.assertEqual(self.node(r)['deps'],{'evidence:map:1':2})
        self.e.command('r','map2','evidence',dict(id='map',revision=2,phase='final',source='course',observed_at=TIME,data=data))
        from round_state import valid_ref
        self.assertIsNone(valid_ref(self.e.state('r'),'chain:'+r['node_id']))
    def test_unknown_map_object_rejected_atomically(self):
        self.open();before=self.e.state('r')
        with self.assertRaises(StateError):self.event('system_advice','system',[dict(id='c',value=dict(club='7i'),object_refs=[dict(evidence_id='missing',object_id='bunker')])])
        self.assertEqual(before,self.e.state('r'))
    def test_replay_after_correction_is_identical(self):
        self.setup_shot('8i');a=self.stage('execution_report',dict(club='8i'));self.gps()
        self.event('correction',source='user_correction',explicit=True,candidates=[dict(id='fix',corrects_node=a['node_id'],value=dict(club='9i'))])
        self.assertEqual(self.e.state('r'),self.e.replay('r'))
    def test_known_ordinal_not_inferred_and_duplicate_rejected(self):
        self.open(ordinal=None)
        self.assertIsNone(self.e.state('r')['shot_chain']['shots']['s1']['stroke_number'])
        self.open('s2',1,2)
        with self.assertRaises(StateError):self.open('s3',1,2)
    def test_unknown_event_rejected(self):
        with self.assertRaises(StateError):self.event('club_calibration')
        self.assertEqual(self.e.state('r')['version'],0)
    def test_taxonomy_complete(self):
        self.assertEqual(len(VOICE_TYPES),11)

    def test_quiet_two_holes_expires_only_on_explicit_hole_changes(self):
        self.open();self.event('interaction_override',explicit=True,value=dict(mode='quiet_holes',holes=2))
        self.gps(hole=2)
        self.assertTrue(self.e.state('r')['facts']['context.quiet']['value'])
        self.event('state_transition',explicit=True,value=dict(kind='enter_hole',hole=2))
        self.assertTrue(self.e.state('r')['facts']['context.quiet']['value'])
        self.event('state_transition',explicit=True,value=dict(kind='enter_hole',hole=3))
        self.assertFalse(self.e.state('r')['facts']['context.quiet']['value'])
    def test_fact_request_resolution_clears_pending_question(self):
        r=self.event('fact_request',candidates=[dict(id='a',effects=effects(club='8i')),dict(id='b',effects=effects(club='6i'))])
        r2=self.event('fact_request',explicit=True,resolves_event_id=r['event_id'],candidates=[r['candidates'][0]])
        self.assertEqual(r2['action'],'commit');self.assertIsNone(self.e.state('r')['shot_chain']['pending_question'])
    def test_stale_resolution_cannot_overwrite_new_execution(self):
        self.open()
        r=self.event('execution_report',candidates=[dict(id='a',value=dict(club='7i'),effects=effects(club='7i')),dict(id='b',value=dict(club='8i'),effects=effects(club='8i'))])
        self.stage('execution_report',dict(club='9i'))
        with self.assertRaises(StateError):self.event('execution_report',explicit=True,resolves_event_id=r['event_id'],candidates=[r['candidates'][0]])
        self.assertEqual(self.e.state('r')['facts']['shots.s1.actual_club']['value'],'9i')
    def test_partial_normalized_event_rejected(self):
        self.open()
        with self.assertRaises(StateError):self.stage('execution_report',dict(club='7i'),phase='partial')
        self.assertNotIn('shots.s1.actual_club',self.e.state('r')['facts'])
    def test_scores_only_suppresses_optional_clarifications(self):
        self.open();self.event('interaction_override',explicit=True,value=dict(mode='scores_only'))
        r=self.event('execution_report',candidates=[dict(id='a',value=dict(club='7i'),effects=effects(club='7i')),dict(id='b',value=dict(club='8i'),effects=effects(club='8i'))])
        self.assertEqual(r['action'],'defer');self.assertIsNone(r['question'])
    def test_source_cannot_impersonate_advice(self):
        self.open()
        with self.assertRaises(StateError):self.stage('system_advice',dict(club='7i'))
    def test_invalidated_evidence_marks_node_invalid(self):
        self.setup_shot();r=self.stage('execution_report',dict(club='7i'))
        ev='chain-'+r['event_id']
        self.e.command('r','asr-revision','evidence',dict(id=ev,revision=2,phase='final',source='user',observed_at=TIME))
        self.assertFalse(self.node(r)['valid'])
    def test_missing_impact_model_never_means_low_impact(self):
        r=self.event('fact_request',candidates=[dict(id='a',distance=110),dict(id='b',distance=115)])
        self.assertEqual(r['impact'],'high');self.assertEqual(r['action'],'clarify')
    def test_score_constraints_failure_is_atomic(self):
        before=self.e.state('r')
        with self.assertRaises(StateError):self.event('score_report',explicit_confirmation=True,candidates=[dict(id='s',hole=1,value=dict(total=4,putts=3,penalties=2))])
        self.assertEqual(before,self.e.state('r'))

    def test_relative_score_uses_versioned_course_par(self):
        data=dict(course_id='c',map_version='1',crs='WGS84',holes=[dict(number=1,par=4)])
        self.e.command('r','map','evidence',dict(id='map',revision=1,phase='final',source='course',observed_at=TIME,data=data))
        self.event('course_context',source='course',value=dict(evidence_id='map:1'))
        r=self.event('score_report',explicit_confirmation=True,candidates=[dict(id='s',hole=1,value=dict(relative=2,putts=2))])
        self.assertEqual(r['calculation']['total'],6);self.assertEqual(self.e.state('r')['facts']['holes.1.total']['value'],6)
        self.e.command('r','map2','evidence',dict(id='map',revision=2,phase='final',source='course',observed_at=TIME,data=data))
        self.assertFalse(self.e.state('r')['facts']['holes.1.total']['valid'])
        self.assertTrue(self.e.state('r')['facts']['holes.1.putts']['valid'])
    def test_relative_score_without_par_stays_unknown(self):
        r=self.event('score_report',explicit_confirmation=True,candidates=[dict(id='s',hole=1,value=dict(relative=2))])
        self.assertNotEqual(r['action'],'commit');self.assertFalse(self.e.state('r')['facts'])
    def test_direct_club_changes_override_incorrect_equal_effects(self):
        self.open()
        r=self.event('execution_report',candidates=[dict(id='a',value=dict(club='7i'),effects=effects()),dict(id='b',value=dict(club='8i'),effects=effects())])
        self.assertEqual(r['action'],'clarify');self.assertEqual(r['impact'],'high')

    def test_shot_view_shows_unknown_slots_and_retains_history(self):
        from shot_chain import shot_view
        self.setup_shot();self.stage('execution_report',dict(club='7i'))
        view=shot_view(self.e.state('r'),'s1')
        self.assertEqual(view['chain']['execution']['value']['club'],'7i')
        self.assertEqual(view['chain']['outcome'],dict(status='unknown',value=None,historical_node_id=None))
        self.assertEqual(len(view['history']),2)

    def test_outcome_does_not_duplicate_same_learning_candidate(self):
        self.setup_shot();self.stage('execution_report',dict(club='7i'));self.gps()
        self.stage('shot_outcome',dict(longitudinal='short'),recording_consent=True)
        self.stage('shot_outcome',dict(lateral='right'),recording_consent=True)
        shot=self.e.state('r')['shot_chain']['shots']['s1']
        self.assertEqual(len(shot['learning_candidates']),1)

    def test_score_correction_preserves_putts_and_gps(self):
        self.setup_shot();gps=self.gps()
        self.event('score_report',explicit_confirmation=True,candidates=[dict(id='s',hole=1,value=dict(total=6,putts=2,penalties=0))])
        version=self.e.state('r')['facts']['holes.1.total']['version']
        r=self.event('correction',source='user_correction',explicit=True,explicit_confirmation=True,
          candidates=[dict(id='fix',score_target=dict(hole=1,read_versions={'holes.1.total':version}),value=dict(total=5))])
        s=self.e.state('r');self.assertEqual(r['action'],'commit');self.assertEqual(s['facts']['holes.1.total']['value'],5)
        self.assertEqual(s['facts']['holes.1.putts']['value'],2);self.assertTrue(self.node(gps)['valid'])
        self.assertEqual(s['shot_chain']['score_revisions'][0]['before']['holes.1.total']['value'],6)
        self.assertEqual(s,self.e.replay('r'))
    def test_stale_score_correction_rejected(self):
        self.event('score_report',explicit_confirmation=True,candidates=[dict(id='s',hole=1,value=dict(total=6))])
        with self.assertRaises(StateError):self.event('correction',source='user_correction',explicit=True,explicit_confirmation=True,
          candidates=[dict(id='fix',score_target=dict(hole=1,read_versions={'holes.1.total':999}),value=dict(total=5))])
        self.assertEqual(self.e.state('r')['facts']['holes.1.total']['value'],6)
    def test_outcome_correction_preserves_other_result_dimension(self):
        self.open();a=self.stage('shot_outcome',dict(longitudinal='short',lateral='right'))
        r=self.event('correction',source='user_correction',explicit=True,candidates=[dict(id='fix',corrects_node=a['node_id'],value=dict(lateral='left'))])
        self.assertEqual(self.node(r)['value'],dict(longitudinal='short',lateral='left'))
        self.assertEqual(self.node(a)['status'],'superseded')

    def test_explicit_retraction_withdraws_execution_only(self):
        self.setup_shot();ex=self.stage('execution_report',dict(club='7i'));gps=self.gps()
        lid=self.e.state('r')['shot_chain']['shots']['s1']['learning_candidates'][-1]
        r=self.event('correction',source='user_correction',explicit=True,
                     candidates=[dict(id='undo',corrects_node=ex['node_id'],retract=True)])
        self.assertEqual(r['reason'],'retracted_stage');self.assertEqual(self.node(ex)['status'],'retracted')
        self.assertFalse(self.e.state('r')['derived'][lid]['valid']);self.assertTrue(self.node(gps)['valid'])
        self.assertIsNone(self.e.state('r')['facts']['shots.s1.actual_club']['value'])
        self.assertEqual(self.e.state('r'),self.e.replay('r'))
    def test_retraction_requires_explicit_instruction(self):
        self.setup_shot();ex=self.stage('execution_report',dict(club='7i'))
        with self.assertRaises(StateError):self.event('correction',source='user_correction',
                     candidates=[dict(id='undo',corrects_node=ex['node_id'],retract=True)])
        self.assertEqual(self.node(ex)['status'],'confirmed')

    def test_gps_cannot_supply_actual_club(self):
        self.open();before=self.e.state('r')
        with self.assertRaises(StateError):self.stage('execution_report',dict(club='7i'),source='gps')
        self.assertEqual(before,self.e.state('r'))
    def test_voice_cannot_impersonate_survey_course_source(self):
        before=self.e.state('r')
        with self.assertRaises(StateError):self.event('course_context',source='voice',value=dict(evidence_id='map:1'))
        self.assertEqual(before,self.e.state('r'))
    def test_user_gps_correction_preserves_original_measurement(self):
        self.open();g=self.gps()
        original=self.node(g)
        raw_id=original['evidence_ids'][0]
        raw=copy.deepcopy(self.e.state('r')['evidence'][raw_id])
        revised=copy.deepcopy(original['value']['end']);revised['longitude']=121.003
        r=self.event('correction',source='user_correction',explicit=True,
                     candidates=[dict(id='fix',corrects_node=g['node_id'],value=dict(end=revised))])
        self.assertEqual(self.e.state('r')['evidence'][raw_id],raw)
        self.assertEqual(self.node(g)['value'],original['value'])
        self.assertEqual(self.node(r)['status'],'candidate')
        self.assertEqual(self.node(r)['source'],'user_correction')
        self.assertFalse(self.e.state('r')['derived'])
