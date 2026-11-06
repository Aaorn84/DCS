#!/usr/bin/env python3
"""Offline weather/carry research engine. Python stdlib only; no API/network.

Constant effective Cd/Cl, fixed backspin axis, uniform horizontal wind, flat
landing plane. Caller-supplied coefficients are NOT universal golf constants.
The output never authorizes an on-course recommendation.
"""
import argparse
import json
import math
import sys
from datetime import datetime, timezone

VERSION = 'weather-carry-0.1.0'
G = 9.80665
RD, RV = 287.05, 461.5
YARD_M = 0.9144


class InputError(ValueError):
    pass


def number(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f'{name}: finite number required')
    if not math.isfinite(value) or not low <= value <= high:
        raise InputError(f'{name}: must be in [{low}, {high}]')
    return float(value)


def timestamp(value):
    if not isinstance(value, str):
        raise InputError('timestamp: ISO 8601 string required')
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise InputError('invalid timestamp') from exc
    if dt.tzinfo is None:
        raise InputError('timestamp must include timezone')
    return dt.astimezone(timezone.utc)


def air_density(temperature_c, relative_humidity_pct, station_pressure_pa):
    """Ideal moist-air mixture, NWS liquid-water saturation approximation.

    Application domain -10..45 C (over liquid water), 70..108 kPa.
    Not a CIPM precision metrology implementation, nor a cold-ball model.
    """
    t = number(temperature_c, 'temperature_c', -10, 45)
    rh = number(relative_humidity_pct, 'relative_humidity_pct', 0, 100)
    pressure = number(station_pressure_pa, 'station_pressure_pa', 70000, 108000)
    es = 611.0 * 10.0 ** (7.5 * t / (237.3 + t))
    vapor = rh / 100.0 * es
    kelvin = t + 273.15
    return (pressure - vapor) / (RD * kelvin) + vapor / (RV * kelvin)


def wind_components(speed_mps, wind_from_deg, target_bearing_deg):
    """True-north bearings; x forward, y left. Meteorological FROM direction."""
    speed = number(speed_mps, 'wind_speed_mps', 0, 15)
    bearing = number(target_bearing_deg, 'target_bearing_deg', 0, 360)
    if speed == 0:
        return (0.0, 0.0)  # Direction may legitimately be null for calm.
    source = number(wind_from_deg, 'wind_from_deg', 0, 360)
    delta = math.radians(source - bearing)
    return (-speed * math.cos(delta), speed * math.sin(delta))


def validate_environment(env, now, max_age_s):
    if not isinstance(env, dict):
        raise InputError('environment object required')
    if env.get('pressure_kind') != 'station':
        raise InputError('pressure_kind must be station, not sea_level or unknown')
    for key in ('source', 'wind_sampling_note'):
        if not isinstance(env.get(key), str) or not env[key].strip():
            raise InputError(f'{key} required')
    age = (now - timestamp(env.get('observed_at'))).total_seconds()
    if age < 0 or age > max_age_s:
        raise InputError('weather future-dated or stale; refresh/resolve time first')
    air_density(env.get('temperature_c'), env.get('relative_humidity_pct'),
                env.get('station_pressure_pa'))
    wind_components(env.get('wind_speed_mps'), env.get('wind_from_deg'), 0)
    return dict(env)


def validate_profile(profile):
    if not isinstance(profile, dict):
        raise InputError('profile object required')
    limits = {
        'launch_angle_deg': (3, 65), 'drag_coefficient': (0, 0.8),
        'lift_coefficient': (0, 0.6), 'mass_kg': (0.03, 0.06),
        'diameter_m': (0.035, 0.05), 'speed_min_mps': (10, 100),
        'speed_max_mps': (10, 100),
    }
    out = dict(profile)
    for key, (low, high) in limits.items():
        out[key] = number(profile.get(key), key, low, high)
    if out['speed_min_mps'] >= out['speed_max_mps']:
        raise InputError('speed_min_mps must be below speed_max_mps')
    for key in ('profile_id', 'coefficient_source'):
        if not isinstance(profile.get(key), str) or not profile[key].strip():
            raise InputError(f'{key} required; no invented default aerodynamic profile')
    if profile.get('distance_type') != 'carry':
        raise InputError('profile distance_type must be carry, not GPS total distance')
    return out


def simulate(profile, speed_mps, density, wind_xy, dt=0.02):
    """RK4 point mass integration; interpolate first ground crossing.

    Research-domain solver; coefficients constant throughout flight.
    Local x=forward, y=left, z=up. Backspin lift uses spin axis (0,-1,0).
    """
    speed = number(speed_mps, 'launch_speed_mps', 1, 100)
    rho = number(density, 'air_density', 0.5, 1.6)
    step = number(dt, 'dt', 0.002, 0.05)
    angle = math.radians(profile['launch_angle_deg'])
    factor = rho * math.pi * (profile['diameter_m'] / 2) ** 2 / (2 * profile['mass_kg'])
    cd, cl = profile['drag_coefficient'], profile['lift_coefficient']
    wx, wy = wind_xy
    state = (0.0, 0.0, 0.0, speed * math.cos(angle), 0.0, speed * math.sin(angle))
    apex, elapsed = 0.0, 0.0

    def derivative(s):
        vx, vy, vz = s[3:]
        ux, uy, uz = vx - wx, vy - wy, vz
        u = math.sqrt(ux * ux + uy * uy + uz * uz)
        # omega x relative_velocity = (-uz, 0, ux).
        lift_norm = math.hypot(ux, uz)
        lift_scale = factor * cl * u * u / lift_norm if lift_norm > 1e-12 else 0.0
        return (vx, vy, vz,
                -factor * cd * u * ux - lift_scale * uz,
                -factor * cd * u * uy,
                -G - factor * cd * u * uz + lift_scale * ux)

    while elapsed < 30:
        previous = state
        k1 = derivative(state)
        k2 = derivative(tuple(v + step * k / 2 for v, k in zip(state, k1)))
        k3 = derivative(tuple(v + step * k / 2 for v, k in zip(state, k2)))
        k4 = derivative(tuple(v + step * k for v, k in zip(state, k3)))
        state = tuple(v + step * (a + 2*b + 2*c + d) / 6
                      for v, a, b, c, d in zip(state, k1, k2, k3, k4))
        if not all(math.isfinite(v) for v in state):
            raise InputError('trajectory diverged')
        apex = max(apex, state[2])
        elapsed += step
        if state[2] <= 0:
            fraction = previous[2] / (previous[2] - state[2])
            x = previous[0] + fraction * (state[0] - previous[0])
            y = previous[1] + fraction * (state[1] - previous[1])
            if x <= 0:
                raise InputError('trajectory not downrange; unsupported conditions')
            return {'carry_forward_m': x, 'drift_left_m': y,
                    'flight_time_s': elapsed - step + step * fraction, 'apex_m': apex}
    raise InputError('trajectory did not land within solver domain')


def solve_speed(profile, distance_m, density, wind_xy):
    """Invert carry on caller-supplied speed domain; refuse nonmonotonic branch."""
    lo, hi = profile['speed_min_mps'], profile['speed_max_mps']
    samples = [lo + (hi - lo) * i / 8 for i in range(9)]
    carries = [simulate(profile, s, density, wind_xy)['carry_forward_m'] for s in samples]
    if any(b <= a for a, b in zip(carries, carries[1:])):
        raise InputError('carry not monotonic in speed domain; split/recalibrate profile')
    if not carries[0] <= distance_m <= carries[-1]:
        raise InputError('target outside profile speed domain; no extrapolation')
    for _ in range(25):
        mid = (lo + hi) / 2
        if simulate(profile, mid, density, wind_xy)['carry_forward_m'] < distance_m:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def equivalent(profile, target_m, environment, baseline, bearing):
    rho = air_density(environment['temperature_c'], environment['relative_humidity_pct'],
                      environment['station_pressure_pa'])
    wind = wind_components(environment['wind_speed_mps'], environment['wind_from_deg'], bearing)
    speed = solve_speed(profile, target_m, rho, wind)
    actual = simulate(profile, speed, rho, wind)
    base_rho = air_density(baseline['temperature_c'], baseline['relative_humidity_pct'],
                           baseline['station_pressure_pa'])
    base_wind = wind_components(baseline['wind_speed_mps'], baseline['wind_from_deg'], bearing)
    base = simulate(profile, speed, base_rho, base_wind)
    return {'equivalent_carry_m': base['carry_forward_m'],
            'required_launch_speed_mps': speed, 'drift_left_m': actual['drift_left_m'],
            'air_density_kg_m3': rho, 'wind_forward_mps': wind[0], 'wind_left_mps': wind[1]}


def calculate_physics(request, now=None):
    if not isinstance(request, dict):
        raise InputError('request object required')
    if request.get('mode') not in ('research', 'atmosphere'):
        raise InputError('v0.1 permits atmosphere/research only, not competition/recommendation mode')
    if request.get('height_difference_m') is not None:
        raise InputError('height difference not implemented; cannot silently ignore it')
    unit = request.get('distance_unit')
    if unit not in ('m', 'yd'):
        raise InputError('distance_unit must be m or yd')
    scale = YARD_M if unit == 'yd' else 1.0
    target = number(request.get('target_distance'), 'target_distance', 10, 400) * scale
    bearing = number(request.get('target_bearing_deg'), 'target_bearing_deg', 0, 360)
    now = now or datetime.now(timezone.utc)
    max_age = number(request.get('max_weather_age_seconds'), 'max_weather_age_seconds', 1, 7200)
    env = validate_environment(request.get('weather'), now, max_age)
    if request.get('mode') == 'atmosphere':
        wind = wind_components(env['wind_speed_mps'], env['wind_from_deg'], bearing)
        return {'engine_version': VERSION, 'status': 'atmosphere_only_no_distance_adjustment',
                'recommendation_allowed': False, 'evaluated_at': now.isoformat(),
                'air_density_kg_m3': air_density(env['temperature_c'], env['relative_humidity_pct'],
                                               env['station_pressure_pa']),
                'wind_forward_mps': wind[0], 'wind_left_mps': wind[1],
                'raw_horizontal_target': target / scale, 'distance_unit': unit,
                'target_bearing_deg': bearing,
                'model_equivalent_carry': None, 'scenario_envelope': None,
                'height_difference': 'unavailable', 'provenance': env}
    baseline = request.get('baseline')
    if not isinstance(baseline, dict) or not baseline.get('source'):
        raise InputError('explicit baseline and source required')
    if baseline.get('pressure_kind') != 'station':
        raise InputError('baseline pressure must be station')
    air_density(baseline.get('temperature_c'), baseline.get('relative_humidity_pct'),
                baseline.get('station_pressure_pa'))
    wind_components(baseline.get('wind_speed_mps'), baseline.get('wind_from_deg'), bearing)
    profile = validate_profile(request.get('profile'))
    nominal = equivalent(profile, target, env, baseline, bearing)

    # Ordered conditional decomposition: pressure -> temperature -> RH -> wind.
    # Each delta compares full inverse solutions, so interactions are allocated
    # to the later step. This is NOT independent causal attribution.
    state = dict(baseline)
    last = equivalent(profile, target, state, baseline, bearing)['equivalent_carry_m']
    initial = last
    ledger = []
    for label, keys in (('pressure', ('station_pressure_pa',)),
                        ('temperature', ('temperature_c',)),
                        ('humidity', ('relative_humidity_pct',)),
                        ('wind', ('wind_speed_mps', 'wind_from_deg'))):
        state.update({key: env[key] for key in keys})
        current = equivalent(profile, target, state, baseline, bearing)['equivalent_carry_m']
        ledger.append({'factor': label, 'conditional_delta': (current - last) / scale})
        last = current
    # Preserve tiny inversion error as an explicit numerical residual.
    ledger.insert(0, {'factor': 'solver_residual', 'conditional_delta': (initial - target) / scale})
    if abs(target + sum(x['conditional_delta'] * scale for x in ledger)
           - nominal['equivalent_carry_m']) > 1e-5:
        raise InputError('decomposition consistency failed')

    # Optional finite scenario set. Not a guaranteed bound or probability interval.
    scenarios = request.get('weather_scenarios', [])
    if not isinstance(scenarios, list) or len(scenarios) > 24:
        raise InputError('weather_scenarios must be a list of at most 24 complete weather objects')
    results = [nominal]
    for scenario in scenarios:
        valid = validate_environment(scenario, now, max_age)
        results.append(equivalent(profile, target, valid, baseline, bearing))
    values = [r['equivalent_carry_m'] / scale for r in results]
    drift = [r['drift_left_m'] / scale for r in results]
    return {
        'engine_version': VERSION, 'status': 'research_only_not_field_validated',
        'evaluated_at': now.isoformat(), 'max_weather_age_seconds': max_age,
        'recommendation_allowed': False, 'distance_unit': unit,
        'raw_horizontal_target': target / scale, 'target_bearing_deg': bearing,
        'solver_settings': {'method': 'RK4', 'dt_seconds': 0.02, 'inversion_iterations': 25,
                            'gravity_m_s2': G, 'dry_air_gas_constant': RD, 'vapor_gas_constant': RV},
        'model_equivalent_carry': nominal['equivalent_carry_m'] / scale,
        'scenario_envelope': [min(values), max(values)] if scenarios else None,
        'range_kind': 'finite_scenario_sensitivity_not_confidence_interval' if scenarios else None,
        'scenario_count_including_nominal': len(results),
        'drift_left_at_original_aim': nominal['drift_left_m'] / scale,
        'drift_scenario_envelope': [min(drift), max(drift)] if scenarios else None,
        'nominal_environment': nominal, 'ordered_conditional_adjustments': ledger,
        'decomposition_order': ['pressure', 'temperature', 'humidity', 'wind'],
        'height_difference': 'unavailable_flat_landing_plane_assumption',
        'roll': 'not_modeled_carry_only', 'profile': profile,
        'provenance': {'weather': env, 'baseline': baseline, 'weather_scenarios': scenarios},
        'limitations': [
            'Constant effective drag/lift; no spin decay, sidespin, wind shear or gust timing.',
            'Atmospheric effect only; no cold-ball impact, wet-face contact, rain or ground roll.',
            'Scenario envelope excludes unprovided uncertainty and player dispersion.',
            'Side drift is not an aim offset; compensating aim changes wind components.',
            'Unknown elevation difference is not measured zero; do not treat estimate as full plays-like distance.',
            'Caller must independently validate metadata, local applicability and permitted features.',
        ],
    }


_HYBRID = None


def calculate(request, now=None):
    """Stable entry point: hybrid v0.1.1, or explicit legacy research modes."""
    global _HYBRID
    if isinstance(request, dict) and (request.get('mode') == 'hybrid' or request.get('action') == 'calibrate'):
        if _HYBRID is None:
            import importlib.util
            from pathlib import Path
            spec = importlib.util.spec_from_file_location('caddie_weather_hybrid', Path(__file__).with_name('weather_hybrid.py'))
            _HYBRID = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(_HYBRID)
        try:
            if request.get('action') == 'calibrate':
                return _HYBRID.propose_calibration(request.get('training'), request.get('validation'),
                                                   request.get('profile'), request.get('baseline'))
            return _HYBRID.calculate(request, now=now)
        except _HYBRID.InputError as exc:
            raise InputError(str(exc)) from exc
    return calculate_physics(request, now=now)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', help='JSON input file, or - for stdin')
    parser.add_argument('--as-of', help='explicit historical replay time (ISO 8601); not live weather')
    args = parser.parse_args()
    try:
        if args.input == '-':
            request = json.load(sys.stdin)
        else:
            with open(args.input, encoding='utf-8') as stream:
                request = json.load(stream)
        now = timestamp(args.as_of) if args.as_of else None
        result = calculate(request, now=now)
        result['time_mode'] = 'historical_replay' if args.as_of else 'current_utc'
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (InputError, KeyError, TypeError, ValueError, OSError) as exc:
        print(json.dumps({'status': 'unavailable', 'error': str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
