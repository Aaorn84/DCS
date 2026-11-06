"""Numerical and behavioral invariants; synthetic fixtures are NOT field validation."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('weather_engine', ROOT / 'scripts/weather_engine.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
NOW = datetime(2026, 11, 6, 7, tzinfo=timezone.utc)


def environment(**updates):
    env = dict(temperature_c=20, relative_humidity_pct=50, station_pressure_pa=101325,
               pressure_kind='station', wind_speed_mps=0, wind_from_deg=None,
               source='synthetic_test_not_observation', observed_at='2026-11-06T06:50:00Z',
               wind_sampling_note='synthetic uniform wind at all heights')
    env.update(updates)
    return env


def profile(**updates):
    p = dict(profile_id='synthetic_iron_NOT_PLAYER_CALIBRATION', distance_type='carry',
             coefficient_source='synthetic numerics fixture; NOT measured or validated',
             launch_angle_deg=20, drag_coefficient=0.25, lift_coefficient=0.12,
             mass_kg=0.0459, diameter_m=0.0427, speed_min_mps=35, speed_max_mps=65)
    p.update(updates)
    return p


def request(**updates):
    r = dict(mode='research', target_distance=150, distance_unit='m', target_bearing_deg=0,
             height_difference_m=None, max_weather_age_seconds=1800,
             weather=environment(), baseline=environment(), profile=profile())
    r.update(updates)
    return r


class AtmosphereTests(unittest.TestCase):
    def test_dry_ideal_gas_reference(self):
        self.assertAlmostEqual(w.air_density(15, 0, 101325), 1.225, places=3)

    def test_density_separates_temperature_humidity_and_pressure(self):
        base = w.air_density(20, 0, 101325)
        self.assertLess(w.air_density(30, 0, 101325), base)
        self.assertLess(w.air_density(20, 100, 101325), base)
        self.assertLess(w.air_density(20, 0, 90000), base)

    def test_reject_invalid_and_missing_weather(self):
        for args in [(float('nan'), 50, 101325), (20, 101, 101325),
                     (20, None, 101325), (20, 50, 1013.25), (True, 50, 101325)]:
            with self.assertRaises(w.InputError):
                w.air_density(*args)
        for updates in [dict(pressure_kind='sea_level'), dict(observed_at='2026-11-05T00:00:00Z'),
                        dict(observed_at='2026-11-07T00:00:00Z'), dict(observed_at='2026-11-06T07:00:00'),
                        dict(source=''), dict(wind_speed_mps=4, wind_from_deg=None)]:
            with self.assertRaises(w.InputError):
                w.validate_environment(environment(**updates), NOW, 1800)

    def test_wind_from_convention_and_rotation(self):
        self.assertAlmostEqual(w.wind_components(5, 0, 0)[0], -5)
        self.assertAlmostEqual(w.wind_components(5, 180, 0)[0], 5)
        self.assertAlmostEqual(w.wind_components(5, 90, 0)[1], 5)
        a, b = w.wind_components(5, 120, 40), w.wind_components(5, 180, 100)
        self.assertAlmostEqual(a[0], b[0])
        self.assertAlmostEqual(a[1], b[1])
        self.assertEqual(w.wind_components(0, None, 0), (0, 0))


class TrajectoryTests(unittest.TestCase):
    def test_vacuum_limit_against_analytic_range(self):
        p = profile(drag_coefficient=0, lift_coefficient=0)
        result = w.simulate(p, 50, 1.2, (0, 0), dt=0.01)
        expected = 50 ** 2 * math.sin(math.radians(40)) / w.G
        self.assertAlmostEqual(result['carry_forward_m'], expected, delta=0.001)
        self.assertAlmostEqual(result['drift_left_m'], 0)

    def test_rk4_timestep_convergence(self):
        a = w.simulate(profile(), 50, 1.2, (-3, 2), dt=0.02)
        b = w.simulate(profile(), 50, 1.2, (-3, 2), dt=0.01)
        self.assertAlmostEqual(a['carry_forward_m'], b['carry_forward_m'], delta=0.01)
        self.assertAlmostEqual(a['drift_left_m'], b['drift_left_m'], delta=0.01)

    def test_crosswind_mirror_and_headwind_effect(self):
        p = profile()
        left = w.simulate(p, 50, 1.2, (0, 4))
        right = w.simulate(p, 50, 1.2, (0, -4))
        self.assertAlmostEqual(left['carry_forward_m'], right['carry_forward_m'], places=6)
        self.assertAlmostEqual(left['drift_left_m'], -right['drift_left_m'], places=6)
        self.assertGreater(left['drift_left_m'], 0)
        calm = w.simulate(p, 50, 1.2, (0, 0))['carry_forward_m']
        head = w.simulate(p, 50, 1.2, (-5, 0))['carry_forward_m']
        tail = w.simulate(p, 50, 1.2, (5, 0))['carry_forward_m']
        self.assertLess(head, calm)
        self.assertGreater(tail, calm)

    def test_inverse_recovers_launch_speed(self):
        distance = w.simulate(profile(), 50, 1.2, (-2, 1))['carry_forward_m']
        self.assertAlmostEqual(w.solve_speed(profile(), distance, 1.2, (-2, 1)), 50, places=5)
        with self.assertRaises(w.InputError):
            w.solve_speed(profile(), 999, 1.2, (0, 0))


class PipelineTests(unittest.TestCase):
    def test_atmosphere_mode_without_player_profile(self):
        raw = request(mode='atmosphere', weather=environment(wind_speed_mps=3, wind_from_deg=90))
        del raw['profile']
        del raw['baseline']
        result = w.calculate(raw, now=NOW)
        self.assertGreater(result['air_density_kg_m3'], 1)
        self.assertAlmostEqual(result['wind_left_mps'], 3)
        self.assertIsNone(result['model_equivalent_carry'])
        self.assertFalse(result['recommendation_allowed'])

    def test_identical_environment_no_adjustment(self):
        result = w.calculate(request(), now=NOW)
        self.assertAlmostEqual(result['model_equivalent_carry'], 150, delta=0.001)
        self.assertFalse(result['recommendation_allowed'])
        self.assertIsNone(result['scenario_envelope'])
        self.assertEqual(result['height_difference'], 'unavailable_flat_landing_plane_assumption')

    def test_headwind_requires_more_equivalent_carry_and_ledger_balances(self):
        result = w.calculate(request(weather=environment(wind_speed_mps=5, wind_from_deg=0,
                                                         temperature_c=10, relative_humidity_pct=80)), now=NOW)
        self.assertGreater(result['model_equivalent_carry'], 150)
        total = 150 + sum(x['conditional_delta'] for x in result['ordered_conditional_adjustments'])
        self.assertAlmostEqual(total, result['model_equivalent_carry'], places=6)
        self.assertEqual(result['decomposition_order'], ['pressure', 'temperature', 'humidity', 'wind'])

    def test_unit_equivalence_and_input_not_mutated(self):
        raw = request(distance_unit='yd', target_distance=150 / w.YARD_M)
        saved = copy.deepcopy(raw)
        result = w.calculate(raw, now=NOW)
        self.assertAlmostEqual(result['model_equivalent_carry'] * w.YARD_M, 150, delta=0.001)
        self.assertEqual(raw, saved)

    def test_scenario_envelope_contains_each_case_not_probability(self):
        scenarios = [environment(wind_speed_mps=3, wind_from_deg=0),
                     environment(wind_speed_mps=3, wind_from_deg=180)]
        result = w.calculate(request(weather_scenarios=scenarios), now=NOW)
        self.assertLess(result['scenario_envelope'][0], 150)
        self.assertGreater(result['scenario_envelope'][1], 150)
        self.assertEqual(result['scenario_count_including_nominal'], 3)
        self.assertIn('not_confidence', result['range_kind'])

    def test_reject_unimplemented_or_untrusted_operating_mode(self):
        for updates in [dict(mode='competition'), dict(mode='recommendation'),
                        dict(height_difference_m=10), dict(distance_unit='feet'),
                        dict(profile=profile(distance_type='total')),
                        dict(profile=profile(coefficient_source=''))]:
            with self.assertRaises(w.InputError):
                w.calculate(request(**updates), now=NOW)

    def test_example_fixture_valid_json_and_research_label(self):
        fixture = json.loads((ROOT / 'assets/weather-example.json').read_text())
        result = w.calculate(fixture, now=NOW)
        self.assertEqual(result['status'], 'research_only_not_field_validated')
        self.assertGreater(result['model_equivalent_carry'], fixture['target_distance'])


if __name__ == '__main__':
    unittest.main()
