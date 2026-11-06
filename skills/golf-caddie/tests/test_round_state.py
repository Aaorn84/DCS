import copy
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from round_state import Engine, StateError, Conflict, attribute, assess_ambiguity, missing_score_question, record_distance


class RoundStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.file = os.path.join(self.tmp.name, 'state.sqlite')
        self.e = Engine(self.file, 'alice')
        self.e.create('r')
        self.counter = 0

    def tearDown(self):
        self.e.close()
        self.tmp.cleanup()

    def cmd(self, kind, payload, **kwargs):
        self.counter += 1
        return self.e.command('r', str(self.counter), kind, payload, now=100, **kwargs)

    def evidence(self, id='u', revision=1, phase='final', source='user'):
        return self.cmd('evidence', dict(id=id, revision=revision, phase=phase, source=source,
                                       observed_at='2026-11-06T08:00:00+08:00', text='test'))['evidence_id']

    def propose(self, ops, eid=None, id=None, deps=None):
        eid = eid or self.evidence('u' + str(self.counter))
        id = id or 'p' + str(self.counter)
        result = self.cmd('propose', dict(id=id, base_version=self.e.state('r')['version'],
                        evidence_ids=[eid], read_versions=deps or {}, operations=ops))
        return id, result['confirmation_version']

    def set(self, path, value, status='confirmed'):
        id, version = self.propose([dict(path=path, value=value, status=status)])
        self.cmd('confirm', dict(id=id, confirmation_version=version, explicit=True))
        return id

    def derive(self, id, deps, kind='distance'):
        self.cmd('derive', dict(id=id, deps=deps, kind=kind, algorithm_version='test-1', value=10))

    def test_partial_cannot_propose(self):
        eid = self.evidence(phase='partial')
        with self.assertRaises(StateError):
            self.propose([dict(path='holes.1.total', value=5, status='confirmed')], eid)
        self.assertEqual(self.e.state('r')['facts'], {})

    def test_proposal_waits_for_explicit_confirmation(self):
        id, version = self.propose([dict(path='holes.1.total', value=5, status='confirmed')])
        self.assertFalse(self.e.state('r')['facts'])
        with self.assertRaises(StateError):
            self.cmd('confirm', dict(id=id, confirmation_version=version, explicit=False))
        self.cmd('confirm', dict(id=id, confirmation_version=version, explicit=True))
        self.assertEqual(self.e.state('r')['facts']['holes.1.total']['value'], 5)

    def test_idempotent_retry(self):
        p = dict(id='u', revision=0, phase='final', source='user', observed_at='2026-11-06T00:00:00Z')
        a = self.e.command('r', 'same', 'evidence', p, now=1)
        self.assertEqual(a, self.e.command('r', 'same', 'evidence', p, now=2))
        self.assertEqual(self.e.state('r')['version'], 1)
        with self.assertRaises(Conflict):
            self.e.command('r', 'same', 'evidence', dict(p, revision=1), now=2)

    def test_duplicate_final_different_transport_key_rejected(self):
        self.evidence()
        with self.assertRaises(StateError):
            self.evidence()

    def test_partial_revision_preserves_previous_final(self):
        self.set('shots.s.actual_club', '7i')
        s = self.e.state('r'); eid = s['facts']['shots.s.actual_club']['evidence_ids'][0]
        self.evidence(eid.rsplit(':', 1)[0], 2, 'partial')
        self.assertTrue(self.e.state('r')['facts']['shots.s.actual_club']['valid'])

    def test_final_revision_invalidates_fact_and_transitive_results(self):
        self.set('shots.s.actual_club', '7i')
        f = self.e.state('r')['facts']['shots.s.actual_club']
        self.derive('club', {'shots.s.actual_club': f['version']}, 'club_stats')
        self.derive('coach', {'derived:club': self.e.state('r')['derived']['club']['version']}, 'coaching')
        self.evidence(f['evidence_ids'][0].rsplit(':', 1)[0], 2)
        s = self.e.state('r')
        self.assertFalse(s['facts']['shots.s.actual_club']['valid'])
        self.assertFalse(s['derived']['club']['valid'])
        self.assertFalse(s['derived']['coach']['valid'])

    def test_score_constraints_atomic(self):
        self.set('holes.1.total', 4)
        self.set('holes.1.putts', 3)
        before = self.e.state('r')
        id, v = self.propose([dict(path='holes.1.penalties', value=2, status='confirmed')])
        at = self.e.state('r')
        with self.assertRaises(StateError):
            self.cmd('confirm', dict(id=id, confirmation_version=v, explicit=True))
        self.assertEqual(at, self.e.state('r'))
        self.assertNotIn('holes.1.penalties', before['facts'])

    def test_unknown_not_zero(self):
        self.set('holes.1.putts', None, 'unknown')
        self.assertIsNone(self.e.state('r')['facts']['holes.1.putts']['value'])
        with self.assertRaises(StateError):
            self.set('holes.1.penalties', None, 'confirmed')

    def test_estimated_putts_excluded_from_stats(self):
        self.set('holes.1.putts', 2, 'estimated')
        f = self.e.state('r')['facts']['holes.1.putts']
        with self.assertRaises(StateError):
            self.derive('stats', {'holes.1.putts': f['version']}, 'club_stats')

    def test_stale_confirmation(self):
        id, version = self.propose([dict(path='holes.1.total', value=4, status='confirmed')])
        self.evidence('other')
        with self.assertRaises(StateError):
            self.cmd('confirm', dict(id=id, confirmation_version=version, explicit=True))
        self.assertFalse(self.e.state('r')['facts'])

    def test_wrong_confirmation_token(self):
        id, v = self.propose([dict(path='holes.1.total', value=4, status='confirmed')])
        with self.assertRaises(StateError):
            self.cmd('confirm', dict(id=id, confirmation_version=v-1, explicit=True))

    def test_owner_isolation(self):
        other = Engine(self.file, 'bob')
        try:
            with self.assertRaises(StateError):
                other.state('r')
            with self.assertRaises(StateError):
                other.command('r', 'x', 'retract', dict(id='anything', explicit=True))
        finally:
            other.close()

    def test_multi_connection_version_conflict(self):
        other = Engine(self.file, 'alice')
        self.evidence()
        try:
            with self.assertRaises(Conflict):
                other.command('r', 'stale', 'evidence', {}, expected_version=0)
        finally:
            other.close()

    def test_late_score_keeps_active_hole(self):
        self.set('context.active_hole', 2)
        candidate = attribute('一号洞五杆', self.e.state('r'))
        id, v = self.propose(candidate['operations'])
        self.cmd('confirm', dict(id=id, confirmation_version=v, explicit=True))
        s = self.e.state('r')
        self.assertEqual(s['facts']['context.active_hole']['value'], 2)
        self.assertEqual(s['facts']['holes.1.total']['value'], 5)
        self.assertFalse(any(k.startswith('shots.') for k in s['facts']))

    def question(self, id='q', target='shots.old', field='actual_club', deps=None):
        self.cmd('question', dict(id=id, target=target, field=field, deps=deps or {}))

    def test_question_target_binding(self):
        self.question()
        self.set('context.active_hole', 2)
        c = attribute('三木', self.e.state('r'), question_id='q', shot_id='new')
        self.assertEqual(c['operations'][0]['path'], 'shots.old.actual_club')

    def test_only_one_question(self):
        self.question()
        with self.assertRaises(StateError):
            self.question('second')
        self.cmd('answer', dict(id='q'))
        self.question('second')

    def test_stale_question_no_misattribution(self):
        self.set('shots.old.hole', 1)
        f = self.e.state('r')['facts']['shots.old.hole']
        self.question(deps={'shots.old.hole': f['version']})
        self.set('shots.old.hole', 2)
        self.assertEqual(attribute('三木', self.e.state('r'), 'q')['status'], 'clarify')

    def test_intention_and_actual(self):
        c = attribute('本来想七铁，后来打了三木', self.e.state('r'), shot_id='s')
        self.assertEqual([o['value'] for o in c['operations']], ['7i', '3w'])
        self.assertEqual([o['path'] for o in c['operations']], ['shots.s.planned_club', 'shots.s.actual_club'])

    def test_correction_and_other_player(self):
        self.assertEqual(attribute('不是七铁，是三木', self.e.state('r'), shot_id='s')['operations'][0]['value'], '3w')
        self.assertEqual(attribute('他打了六杆', self.e.state('r'))['operations'], [])
        self.assertEqual(attribute('不是七铁，是三木', self.e.state('r'))['status'], 'clarify')

    def test_unsupported_text_never_creates_facts(self):
        for text in ['七铁可能够', '本来想七铁', 'OB好像没有', '撤销刚才', '还有多少']:
            self.assertEqual(attribute(text, self.e.state('r'), shot_id='s')['operations'], [])
        self.assertFalse(self.e.state('r')['facts'])

    def test_rollback_preserves_independent_data(self):
        club = self.set('shots.s.actual_club', '7i')
        self.set('shots.s.hole', 1)
        f = self.e.state('r')['facts']
        self.derive('distance', {'shots.s.hole': f['shots.s.hole']['version']})
        self.derive('club', {'shots.s.actual_club': f['shots.s.actual_club']['version'], 'derived:distance': self.e.state('r')['derived']['distance']['version']}, 'club_stats')
        self.set('holes.2.total', 5)
        self.cmd('retract', dict(id=club, explicit=True))
        s = self.e.state('r')
        self.assertTrue(s['derived']['distance']['valid'])
        self.assertFalse(s['derived']['club']['valid'])
        self.assertEqual(s['facts']['holes.2.total']['value'], 5)
        self.assertIsNone(s['facts']['shots.s.actual_club']['value'])

    def test_retraction_cannot_overwrite_later_edit(self):
        old = self.set('shots.s.actual_club', '7i')
        self.set('shots.s.actual_club', '3w')
        with self.assertRaises(StateError):
            self.cmd('retract', dict(id=old, explicit=True))
        self.assertEqual(self.e.state('r')['facts']['shots.s.actual_club']['value'], '3w')

    def enqueue(self, id='speech', deps=None, scope='current', **flags):
        self.cmd('enqueue', dict(id=id, text='145码', expires_at=200, scope=scope,
                                deps=deps or {}, strategy=flags.get('strategy', False), proactive=flags.get('proactive', False)))

    def test_quiet_cancels_speech_and_blocks_questions(self):
        self.set('context.active_hole', 1)
        self.enqueue()
        self.set('context.quiet', True)
        self.set('context.active_hole', 2)
        with self.assertRaises(StateError):
            self.question()
        result = self.cmd('dispatch', dict(id='speech'))
        self.assertIsNone(result['text'])
        self.assertTrue(self.e.state('r')['facts']['context.quiet']['value'])

    def test_hole_move_cancels_current_speech(self):
        self.set('context.active_hole', 1)
        self.enqueue()
        self.set('context.active_hole', 2)
        self.assertIsNone(self.cmd('dispatch', dict(id='speech'))['text'])

    def test_past_hole_answer_allowed(self):
        self.set('context.active_hole', 2)
        self.enqueue(scope='past')
        self.assertEqual(self.cmd('dispatch', dict(id='speech'))['text'], '145码')
        self.assertIsNone(self.cmd('dispatch', dict(id='speech'))['text'])

    def test_speech_expiry(self):
        self.enqueue(scope='past')
        self.counter += 1
        r = self.e.command('r', str(self.counter), 'dispatch', dict(id='speech'), now=201)
        self.assertEqual(r['status'], 'expired')

    def test_strategy_needs_position_and_permission(self):
        self.set('context.active_hole', 1)
        with self.assertRaises(StateError):
            self.enqueue(strategy=True)

    def test_proactive_requires_consent(self):
        with self.assertRaises(StateError):
            self.cmd('question', dict(id='q', target='holes.1', field='total', proactive=True))
        self.set('preferences.proactive', True)
        self.cmd('question', dict(id='q', target='holes.1', field='total', proactive=True))

    def test_replay_after_reopen(self):
        p = self.set('holes.1.total', 5)
        self.set('holes.2.total', 4)
        self.cmd('retract', dict(id=p, explicit=True))
        self.enqueue(scope='past')
        self.cmd('dispatch', dict(id='speech'))
        expected = self.e.state('r')
        self.e.close()
        self.e = Engine(self.file, 'alice')
        self.assertEqual(expected, self.e.replay('r'))
        self.assertEqual(expected, self.e.state('r'))

    def test_invalid_fields_and_non_finite_rejected(self):
        for path, value in [('shots.s.elevation', 0), ('holes.1.total', True), ('context.quiet', 'yes'), ('shots.s.actual_club', 'bomb')]:
            with self.assertRaises(StateError):
                self.set(path, value)
        with self.assertRaises(ValueError):
            self.cmd('evidence', dict(x=float('nan')))

    def test_rejected_command_does_not_advance_ledger(self):
        before = self.e.state('r')
        with self.assertRaises(StateError):
            self.cmd('unknown', {})
        self.assertEqual(before, self.e.state('r'))
        self.assertEqual(before, self.e.replay('r'))


    def test_partial_to_final_same_revision(self):
        self.evidence('same', 1, 'partial')
        final = self.evidence('same', 1, 'final')
        id, v = self.propose([dict(path='holes.1.total', value=5, status='confirmed')], final)
        self.cmd('confirm', dict(id=id, confirmation_version=v, explicit=True))
        self.assertEqual(self.e.state('r')['facts']['holes.1.total']['value'], 5)

    def test_gps_transition_no_swing_or_score_inference(self):
        eid = self.cmd('evidence', dict(id='gps', revision=1, phase='final', source='gps',
                      observed_at='2026-11-06T00:00:00Z', reliable_transition=True))['evidence_id']
        self.cmd('gps_transition', dict(evidence_id=eid, hole=2))
        self.assertEqual(list(self.e.state('r')['facts']), ['context.active_hole'])

    def test_unreliable_gps_cannot_move_hole(self):
        eid = self.evidence(source='gps')
        with self.assertRaises(StateError):
            self.cmd('gps_transition', dict(evidence_id=eid, hole=2))
        self.assertFalse(self.e.state('r')['facts'])

    def test_gps_cannot_confirm_score(self):
        eid = self.evidence(source='gps')
        id, v = self.propose([dict(path='holes.1.total', value=5, status='confirmed')], eid)
        with self.assertRaises(StateError):
            self.cmd('confirm', dict(id=id, confirmation_version=v, explicit=True))

    def test_explicit_control_immediately_quiet(self):
        eid = self.evidence()
        self.cmd('control', dict(path='context.quiet', value=True, evidence_id=eid, explicit=True))
        self.assertTrue(self.e.state('r')['facts']['context.quiet']['value'])
        with self.assertRaises(StateError):
            self.cmd('control', dict(path='context.quiet', value=False, evidence_id=eid, explicit=False))

    def test_score_followups_one_at_a_time(self):
        self.assertEqual(missing_score_question(self.e.state('r'), 1, 4), 'total')
        self.set('holes.1.total', 6)
        self.assertEqual(missing_score_question(self.e.state('r'), 1, 4), 'putts')
        self.set('holes.1.putts', 2)
        self.assertEqual(missing_score_question(self.e.state('r'), 1, 4), 'penalties')
        self.set('holes.1.penalties', 0)
        self.assertIsNone(missing_score_question(self.e.state('r'), 1, 4))

    def test_hypothetical_correction_remains_unresolved(self):
        c = attribute('不确定是不是七铁，是三木吗', self.e.state('r'), shot_id='s')
        self.assertEqual(c['operations'], [])

    def test_ambiguous_interpretation_requires_new_resolution(self):
        eid = self.evidence()
        candidates = [dict(operations=[dict(path='shots.s.actual_club', value=club, status='confirmed')],
                           outcome=AmbiguityTests().outcome(club)) for club in ('7i', '3w')]
        report = self.cmd('interpret', dict(id='i', evidence_id=eid, candidates=candidates, complete=True))
        self.assertEqual(report['decision'], 'clarify')
        payload = dict(id='p', base_version=self.e.state('r')['version'], evidence_ids=[eid],
                       interpretation_id='i', operations=candidates[0]['operations'])
        with self.assertRaises(StateError):
            self.cmd('propose', payload)
        resolve = self.evidence('resolution')
        payload.update(base_version=self.e.state('r')['version'], evidence_ids=[eid, resolve],
                       resolved_explicit=True, resolution_evidence_id=resolve)
        r = self.cmd('propose', payload)
        self.cmd('confirm', dict(id='p', confirmation_version=r['confirmation_version'], explicit=True))
        self.assertEqual(self.e.state('r')['facts']['shots.s.actual_club']['value'], '7i')

    def test_retracted_fact_not_revived_by_old_evidence(self):
        self.set('shots.s.actual_club', '7i')
        f = self.e.state('r')['facts']['shots.s.actual_club']
        old_eid = f['evidence_ids'][0].rsplit(':', 1)[0]
        newer = self.set('shots.s.actual_club', '3w')
        self.evidence(old_eid, 2)
        self.cmd('retract', dict(id=newer, explicit=True))
        self.assertFalse(self.e.state('r')['facts']['shots.s.actual_club']['valid'])

    def position(self, longitude, stamp):
        return dict(latitude=31, longitude=longitude, accuracy_m=1, crs='WGS84',
                    hole_id='1', observed_at=stamp, ball_position_confirmed=True)

    def distance_setup(self):
        start = self.set('shots.start.position', self.position(121, '2026-11-06T00:00:00Z'))
        self.set('shots.end.position', self.position(121.002, '2026-11-06T00:04:00Z'))
        evidence = dict(recording_consent=True, single_stroke_confirmed=True, intervening_strokes=0,
                        relief_or_provisional=False, gap_open=False, max_position_error_sum_m=10)
        record_distance(self.e, 'r', 'distance', 'd', 'shots.start.position', 'shots.end.position', evidence)
        return start, evidence

    def test_distance_endpoint_rollback_invalidates_transitive_speech(self):
        start, _ = self.distance_setup()
        d = self.e.state('r')['derived']['d']
        self.assertGreater(d['value']['total_horizontal_m'], 100)
        self.assertFalse(d['value']['usable_for_carry_stats'])
        self.derive('strategy', {'derived:d': d['version']}, 'strategy')
        self.enqueue(scope='past', deps={'derived:strategy': self.e.state('r')['derived']['strategy']['version']})
        self.cmd('retract', dict(id=start, explicit=True))
        s = self.e.state('r')
        self.assertFalse(s['derived']['d']['valid'])
        self.assertFalse(s['derived']['strategy']['valid'])
        self.assertIsNone(self.cmd('dispatch', dict(id='speech'))['text'])

    def test_distance_gap_is_not_a_single_shot(self):
        _, evidence = self.distance_setup()
        evidence['gap_open'] = True
        with self.assertRaises(StateError):
            record_distance(self.e, 'r', 'bad-distance', 'd2', 'shots.start.position', 'shots.end.position', evidence)
        self.assertNotIn('d2', self.e.state('r')['derived'])

    def test_strategy_position_and_revoked_permission(self):
        self.set('context.active_hole', 1)
        self.set('permissions.strategy', True)
        self.set('context.ball_position', self.position(121, '2026-11-06T00:00:00Z'))
        f = self.e.state('r')['facts']['context.ball_position']
        self.enqueue(strategy=True, deps={'context.ball_position': f['version']})
        self.set('permissions.strategy', False)
        self.assertIsNone(self.cmd('dispatch', dict(id='speech'))['text'])

    def test_ball_position_change_cancels_strategy(self):
        self.set('context.active_hole', 1)
        self.set('permissions.strategy', True)
        self.set('context.ball_position', self.position(121, '2026-11-06T00:00:00Z'))
        f = self.e.state('r')['facts']['context.ball_position']
        self.enqueue(strategy=True, deps={'context.ball_position': f['version']})
        self.set('context.ball_position', self.position(121.002, '2026-11-06T00:04:00Z'))
        self.assertIsNone(self.cmd('dispatch', dict(id='speech'))['text'])

    def test_replay_full_mixed_workflow(self):
        self.distance_setup()
        self.set('holes.1.total', 5)
        self.question(target='holes.1', field='putts')
        self.cmd('answer', dict(id='q'))
        self.set('holes.1.putts', 2)
        self.assertEqual(self.e.state('r'), self.e.replay('r'))

    def test_silence_asr_revision_does_not_reopen_microphone_flow(self):
        self.set('context.quiet', True)
        eid = self.e.state('r')['facts']['context.quiet']['evidence_ids'][0].rsplit(':', 1)[0]
        self.evidence(eid, 2)
        with self.assertRaises(StateError):
            self.question()

    def test_out_of_order_gps_does_not_rewind_hole(self):
        for id, stamp, hole in [('new', '2026-11-06T02:00:00Z', 2), ('old', '2026-11-06T01:00:00Z', 1)]:
            eid = self.cmd('evidence', dict(id=id, revision=1, phase='final', source='gps',
                           observed_at=stamp, reliable_transition=True))['evidence_id']
            if hole == 2:
                self.cmd('gps_transition', dict(evidence_id=eid, hole=hole))
            else:
                with self.assertRaises(StateError):
                    self.cmd('gps_transition', dict(evidence_id=eid, hole=hole))
        self.assertEqual(self.e.state('r')['facts']['context.active_hole']['value'], 2)

    def test_estimated_lineage_cannot_train_through_derived_result(self):
        self.set('holes.1.putts', 2, 'estimated')
        f = self.e.state('r')['facts']['holes.1.putts']
        self.derive('first', {'holes.1.putts': f['version']}, 'coaching')
        with self.assertRaises(StateError):
            self.derive('stats', {'derived:first': self.e.state('r')['derived']['first']['version']}, 'club_stats')

    def test_missing_dependency_with_null_version_is_rejected(self):
        with self.assertRaises(StateError):
            self.derive('bad', {'missing.fact': None})
        self.assertFalse(self.e.state('r')['derived'])

    def course(self, revision=1, data=None):
        return self.cmd('evidence', dict(id='course', revision=revision, phase='final', source='course',
                        observed_at='2026-11-06T00:00:00Z',
                        data=data if data is not None else dict(course_id='c', map_version=str(revision), crs='WGS84')))['evidence_id']

    def test_three_sources_join_without_inventing_strokes(self):
        course = self.course()
        gps = self.evidence('g', source='gps')
        voice = self.evidence('v')
        self.derive('situation', {'evidence:' + e: 2 for e in (course, gps, voice)}, 'strategy')
        self.assertTrue(self.e.state('r')['derived']['situation']['valid'])
        self.assertEqual(self.e.state('r')['facts'], {})
        self.assertEqual(self.e.state('r'), self.e.replay('r'))

    def test_map_revision_invalidates_dependent_distance_and_speech(self):
        course = self.course()
        self.derive('target_distance', {'evidence:' + course: 2})
        d = self.e.state('r')['derived']['target_distance']
        self.enqueue(scope='past', deps={'derived:target_distance': d['version']})
        self.course(2)
        self.assertFalse(self.e.state('r')['derived']['target_distance']['valid'])
        self.assertIsNone(self.cmd('dispatch', dict(id='speech'))['text'])

    def test_partial_evidence_cannot_be_derived_dependency(self):
        eid = self.evidence('partial', phase='partial')
        with self.assertRaises(StateError):
            self.derive('bad', {'evidence:' + eid: 2})

    def test_unversioned_course_snapshot_rejected(self):
        with self.assertRaises(StateError):
            self.course(data=dict(course_id='c', crs='WGS84'))
        self.assertEqual(self.e.state('r')['evidence'], {})

    def test_map_observation_does_not_train_player_stats(self):
        eid = self.course()
        with self.assertRaises(StateError):
            self.derive('bad_stats', {'evidence:' + eid: 2}, 'club_stats')


class AmbiguityTests(unittest.TestCase):
    def outcome(self, c):
        return dict(answer='145码', feasible=True, forced_carry=False, target='center', club='7i',
                    score_effect=None, record_effect=c, permission_effect=None)

    def test_common_answer_without_record_commit(self):
        r = assess_ambiguity(['3w', 'driver'], self.outcome)
        self.assertEqual(r['common_answer'], '145码')
        self.assertEqual(r['decision'], 'clarify')
        self.assertFalse(r['commit_allowed'])

    def test_same_consequences(self):
        self.assertEqual(assess_ambiguity([1, 2], lambda c: self.outcome(0))['decision'], 'common_answer')

    def test_different_water_and_quiet(self):
        def planner(c):
            return dict(self.outcome(None), forced_carry=c, answer=str(c))
        self.assertEqual(assess_ambiguity([True, False], planner)['decision'], 'clarify')
        self.assertEqual(assess_ambiguity([True, False], planner, quiet=True)['decision'], 'defer')

    def test_fail_closed(self):
        def broken(c):
            raise RuntimeError('offline')
        for candidates, planner, complete in [([], self.outcome, True), ([1], broken, True), ([1], lambda c: {}, True), ([1], self.outcome, False)]:
            self.assertEqual(assess_ambiguity(candidates, planner, complete=complete)['decision'], 'unknown')
