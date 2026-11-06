"""Hybrid invariants and planted synthetic calibration; not field validation."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('hybrid',ROOT/'scripts/weather_hybrid.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
NOW=datetime(2026,11,6,7,tzinfo=timezone.utc)


def env(**updates):
    raw=dict(source='synthetic-not-field-weather',observed_at='2026-11-06T06:55:00Z',
             temperature_c=20,relative_humidity_pct=50,station_pressure_pa=101325,
             pressure_kind='station',wind_speed_mps=0,wind_from_deg=None,wind_gust_mps=0)
    raw.update(updates);return raw


def prof(**updates):
    raw=dict(club_id='7i',flight_group='stock',ball_id='test-ball',source='synthetic carry baseline',
             distance_type='carry',distance_unit='m',baseline_carry=150,baseline_id='test-ref')
    raw.update(updates);return raw


def request(**updates):
    raw=dict(mode='hybrid',rules_mode='practice',target_distance=150,distance_unit='m',
             target_bearing_deg=0,height_difference_m=None,max_weather_age_seconds=1800,
             profile=prof(),baseline=env(reference_id='test-ref'),weather=env())
    raw.update(updates);return raw


class HybridTests(unittest.TestCase):
    def test_stable_entry_dispatches_hybrid_and_reconciles(self):
        spec=importlib.util.spec_from_file_location('public_weather_entry',ROOT/'scripts/weather_engine.py')
        public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)
        r=public.calculate(request(weather=env(wind_speed_mps=3,wind_from_deg=0,wind_gust_mps=5)),NOW)
        self.assertEqual(r['engine_version'],'0.1.1')
        self.assertEqual(r['model'],'carry_hybrid')
        self.assertAlmostEqual(r['raw_horizontal_distance']+sum(r['shapley_adjustments'].values()),
                               r['nominal_for_audit_not_exact_advice'],places=7)
        with self.assertRaises(public.InputError):
            public.calculate(request(target_bearing_deg=None),NOW)

    def test_cipm_reference_and_domain(self):
        self.assertAlmostEqual(h.density_cipm2007(20,50,101325),1.1993,delta=.0001)
        with self.assertRaises(h.InputError):h.density_cipm2007(10,50,101325)
        self.assertIn('outside',h.density(10,50,101325)[1])
        self.assertIn('CIPM',h.density(20,50,101325)[1])

    def test_moisture_temperature_and_pressure_density_effect(self):
        rho=h.density(20,0,101325)[0]
        self.assertLess(h.density(25,0,101325)[0],rho)
        self.assertLess(h.density(20,100,101325)[0],rho)
        self.assertLess(h.density(20,0,95000)[0],rho)

    def test_missing_pressure_is_explicit_not_silently_zero(self):
        result=h.calculate(request(weather=env(station_pressure_pa=None)),NOW)
        weather=result['provenance']['weather']
        self.assertEqual(weather['station_pressure_pa'],101325)
        self.assertTrue(weather['pressure_assumption'])
        self.assertEqual(result['confidence']['level'],'low')
        self.assertIn('standard_pressure',str(result['confidence']['reasons']))
        with self.assertRaises(h.InputError):
            h.calculate(request(weather=env(pressure_kind='sea_level')),NOW)

    def test_missing_data_stale_or_invalid_rejected(self):
        cases=[dict(target_bearing_deg=None),dict(profile=None),dict(weather=env(temperature_c=None)),
               dict(weather=env(wind_speed_mps=3,wind_from_deg=None,wind_gust_mps=3)),
               dict(weather=env(observed_at='2026-11-05T00:00:00Z')),
               dict(weather=env(observed_at='2026-11-07T00:00:00Z')),
               dict(weather=env(relative_humidity_pct=101)),dict(target_distance=float('nan')),
               dict(weather=env(wind_speed_mps=3,wind_from_deg=0,wind_gust_mps=2)),
               dict(profile=prof(distance_type='total')),dict(profile=prof(baseline_id='wrong')),
               dict(profile=prof(coefficients=[],coefficient_source='test',coefficient_status='test'))]
        for updates in cases:
            with self.subTest(updates=updates):
                with self.assertRaises(h.InputError):h.calculate(request(**updates),NOW)

    def test_calm_identical_baseline_zero_adjustment(self):
        r=h.calculate(request(),NOW)
        self.assertEqual(r['playing_distance_range'],[150,150])
        self.assertAlmostEqual(sum(r['shapley_adjustments'].values()),0,places=8)
        self.assertFalse(r['recommendation_allowed'])
        self.assertIn('engineering_prior',r['provenance']['profile']['coefficient_status'])

    def test_headwind_tailwind_asymmetric_and_crosswind_separate(self):
        head=h.calculate(request(weather=env(wind_speed_mps=5,wind_from_deg=0,wind_gust_mps=5)),NOW)
        tail=h.calculate(request(weather=env(wind_speed_mps=5,wind_from_deg=180,wind_gust_mps=5)),NOW)
        self.assertGreater(head['playing_distance_range'][0],150)
        self.assertLess(tail['playing_distance_range'][1],150)
        self.assertGreater(head['nominal_for_audit_not_exact_advice']-150,150-tail['nominal_for_audit_not_exact_advice'])
        cross=h.calculate(request(weather=env(wind_speed_mps=5,wind_from_deg=90,wind_gust_mps=5)),NOW)
        self.assertAlmostEqual(cross['nominal_for_audit_not_exact_advice'],150,places=7)
        self.assertGreater(cross['lateral_drift_left_range'][0],0)
        mirror=h.calculate(request(weather=env(wind_speed_mps=5,wind_from_deg=270,wind_gust_mps=5)),NOW)
        self.assertAlmostEqual(cross['lateral_drift_left_range'][1],-mirror['lateral_drift_left_range'][0])

    def test_gust_scenarios_and_coefficient_range_expand_sensitivity(self):
        calm=h.calculate(request(weather=env(wind_speed_mps=3,wind_from_deg=0,wind_gust_mps=3)),NOW)
        gust=h.calculate(request(weather=env(wind_speed_mps=3,wind_from_deg=0,wind_gust_mps=7)),NOW)
        self.assertGreater(gust['playing_distance_range'][1],calm['playing_distance_range'][1])
        self.assertIn('not_confidence',gust['range_kind'])

    def test_symmetric_ledger_reconciles_and_no_double_count(self):
        r=h.calculate(request(weather=env(temperature_c=25,relative_humidity_pct=90,
                                          station_pressure_pa=95000,wind_speed_mps=4,wind_from_deg=20,wind_gust_mps=6)),NOW)
        self.assertAlmostEqual(150+sum(r['shapley_adjustments'].values()),r['nominal_for_audit_not_exact_advice'],places=7)
        # Wind attribution can interact with density, but these four shares sum once.
        self.assertEqual(len(r['shapley_adjustments']),4)

    def test_temperature_humidity_attribution_matches_symmetric_two_factor_case(self):
        b=h.environment(env(reference_id='test-ref'),historical=True)
        c=h.environment(env(temperature_c=25,relative_humidity_pct=90),NOW,1800)
        coeff=h.midpoints(h.profile(prof()))
        f=lambda e:h.evaluate(150,150,b,e,0,coeff)['equivalent']
        temp=dict(b,temperature_c=25);humid=dict(b,relative_humidity_pct=90)
        ledger=h.shapley_ledger(150,150,b,c,0,coeff)
        self.assertAlmostEqual(ledger['temperature_c'],.5*((f(temp)-f(b))+(f(c)-f(humid))),places=7)
        self.assertAlmostEqual(ledger['relative_humidity_pct'],.5*((f(humid)-f(b))+(f(c)-f(temp))),places=7)

    def test_units_rotation_and_input_immutability(self):
        raw=request(weather=env(wind_speed_mps=3,wind_from_deg=40,wind_gust_mps=3),target_bearing_deg=10)
        original=copy.deepcopy(raw);a=h.calculate(raw,NOW)
        b=h.calculate(request(weather=env(wind_speed_mps=3,wind_from_deg=100,wind_gust_mps=3),
                              target_bearing_deg=70,target_distance=150/h.YARD_M,distance_unit='yd'),NOW)
        self.assertAlmostEqual(a['nominal_for_audit_not_exact_advice'],b['nominal_for_audit_not_exact_advice']*h.YARD_M,places=6)
        self.assertEqual(raw,original)

    def test_competition_elevation_and_out_of_domain(self):
        for updates in [dict(rules_mode='competition'),dict(rules_mode='unknown'),
                        dict(height_difference_m=10),dict(target_distance=250),
                        dict(weather=env(wind_speed_mps=11,wind_from_deg=0,wind_gust_mps=11))]:
            with self.assertRaises(h.InputError):h.calculate(request(**updates),NOW)


def samples(phase,rounds):
    p=h.profile(prof());base=h.environment(env(reference_id='test-ref'),historical=True)
    planted=dict(headwind_per_mps=.017,tailwind_per_mps=.004,crosswind_per_mps=.008,density_exponent=.74)
    out=[]
    for rid in range(rounds):
        for i in range(12):
            speed=(0,3,5)[i%3];direction=0 if i%3==1 else (180 if i%3==2 else None)
            weather=env(temperature_c=15+(i%4)*4,relative_humidity_pct=30+i*4,
                        station_pressure_pa=95000+(i%4)*3000,
                        wind_speed_mps=speed,wind_from_deg=direction,wind_gust_mps=speed)
            e=h.environment(weather,historical=True)
            value=h.evaluate(150,150,base,e,0,planted)['predicted_club_carry']
            out.append(dict(sample_id=f'{phase}-{rid}-{i}',round_id=f'{phase}-{rid}',
                            club_id='7i',flight_group='stock',ball_id='test-ball',distance_type='carry',
                            distance_unit='m',confirmed=True,comparable_lie=True,height_difference_m=0,
                            shot_at='2026-11-06T07:00:00Z',
                            measured_carry=value,target_bearing_deg=0,weather=weather))
    return out


class CalibrationTests(unittest.TestCase):
    def test_separate_round_holdout_proposes_without_applying(self):
        r=h.propose_calibration(samples('train',3),samples('valid',2),prof(),env(reference_id='test-ref'))
        self.assertEqual(r['status'],'personal_candidate_pending_release')
        self.assertFalse(r['auto_applied'])
        c=r['profile']['calibration']
        self.assertLess(c['holdout_mae_after_m'],c['holdout_mae_before_m'])
        self.assertEqual(r['profile']['coefficients']['crosswind_per_mps'],h.COEFFICIENTS['crosswind_per_mps'])

    def test_insufficient_samples_keep_prior(self):
        r=h.propose_calibration(samples('train',1),samples('valid',1),prof(),env(reference_id='test-ref'))
        self.assertIn('insufficient',r['status'])

    def test_duplicate_round_leakage_and_total_distance_rejected(self):
        for label in ('round','sample','total','stale'):
            train,valid=samples('train',3),samples('valid',2)
            if label=='round':valid[0]['round_id']=train[0]['round_id']
            elif label=='sample':valid[0]['sample_id']=train[0]['sample_id']
            elif label=='total':train[0]['distance_type']='total'
            else:train[0]['shot_at']='2026-11-07T07:00:00Z'
            with self.assertRaises(h.InputError):h.propose_calibration(train,valid,prof(),env(reference_id='test-ref'))

    def test_lateral_training_without_holdout_does_not_replace_crosswind(self):
        train,valid=samples('train',3),samples('valid',2)
        # Existing carry coverage remains, add separately observed crosswind rows.
        for rid in range(3):
            for i in range(4):
                s=copy.deepcopy(train[rid*12+i]);s.update(sample_id=f'cross-{rid}-{i}')
                s['weather'].update(wind_speed_mps=4,wind_from_deg=90,wind_gust_mps=4)
                e=h.environment(s['weather'],historical=True)
                b=h.environment(env(reference_id='test-ref'),historical=True)
                coeff=dict(headwind_per_mps=.017,tailwind_per_mps=.004,crosswind_per_mps=.008,density_exponent=.74)
                values=h.evaluate(150,150,b,e,0,coeff)
                s.update(measured_carry=values['predicted_club_carry'],drift_left=values['drift_left'],drift_confirmed=True)
                train.append(s)
        r=h.propose_calibration(train,valid,prof(),env(reference_id='test-ref'))
        self.assertEqual(r['status'],'personal_candidate_pending_release')
        self.assertEqual(r['profile']['coefficients']['crosswind_per_mps'],h.COEFFICIENTS['crosswind_per_mps'])
        self.assertFalse(r['profile']['calibration']['lateral_holdout_accepted'])

    def test_density_coverage_required(self):
        train,valid=samples('train',3),samples('valid',2)
        for s in train:s['weather'].update(temperature_c=20,relative_humidity_pct=50,station_pressure_pa=101325)
        r=h.propose_calibration(train,valid,prof(),env(reference_id='test-ref'))
        self.assertIn('not_identifiable',r['status'])


if __name__=='__main__':unittest.main()
