#!/usr/bin/env python3
"""v0.1.1 carry-based hybrid weather model. No launch-data/API dependency.

Default coefficient intervals are ENGINEERING PRIORS, not NIST/NASA/TrackMan
fitting results. All estimates remain unvalidated until an independent release.
"""
import argparse
import copy
import itertools
import json
import math
import statistics
import sys
from datetime import datetime, timezone

VERSION = '0.1.1'
STANDARD_PRESSURE_PA = 101325.0
YARD_M = 0.9144
COEFFICIENTS = {
    'headwind_per_mps': [0.008, 0.018],
    'tailwind_per_mps': [0.003, 0.008],
    'crosswind_per_mps': [0.003, 0.010],
    'density_exponent': [0.3, 0.8],
}
COEFF_LIMITS = {'headwind_per_mps': (0, .04), 'tailwind_per_mps': (0, .03),
                'crosswind_per_mps': (0, .03), 'density_exponent': (0, 1.5)}


class InputError(ValueError):
    pass


def num(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f'{name}: finite number required')
    if not math.isfinite(value) or not low <= value <= high:
        raise InputError(f'{name}: outside [{low}, {high}]')
    return float(value)


def stamp(value):
    if not isinstance(value, str):
        raise InputError('timezone-aware observed_at required')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise InputError('invalid ISO timestamp') from exc
    if result.tzinfo is None:
        raise InputError('timestamp must include timezone')
    return result.astimezone(timezone.utc)


def density_cipm2007(t, rh, p):
    """CIPM-2007 eq(1), Appendix A; fixed assumed CO2 amount fraction 400 ppm.

    Strict published recommended temperature/pressure domain; outside it the
    public density() dispatches to a labeled ideal-mixture approximation.
    """
    t = num(t, 'temperature_c', 15, 27)
    rh = num(rh, 'relative_humidity_pct', 0, 100)
    p = num(p, 'station_pressure_pa', 60000, 110000)
    k = t + 273.15
    psv = math.exp(1.2378847e-5*k*k - 1.9121316e-2*k + 33.93711047 - 6343.1645/k)
    enhancement = 1.00062 + 3.14e-8*p + 5.6e-7*t*t
    xv = rh / 100 * enhancement * psv / p
    z = (1 - p/k * (1.58123e-6 - 2.9331e-8*t + 1.1043e-10*t*t
                    + (5.707e-6 - 2.051e-8*t)*xv
                    + (1.9898e-4 - 2.376e-6*t)*xv*xv)
         + (p/k)**2 * (1.83e-11 - .765e-8*xv*xv))
    ma, mv, r = .02896546, .01801528, 8.314472
    return p*ma/(z*r*k) * (1 - xv*(1 - mv/ma))


def density(t, rh, p):
    t = num(t, 'temperature_c', -10, 45)
    rh = num(rh, 'relative_humidity_pct', 0, 100)
    p = num(p, 'station_pressure_pa', 60000, 110000)
    if 15 <= t <= 27:
        return density_cipm2007(t, rh, p), 'CIPM-2007_CO2_assumed_400ppm'
    # NWS liquid-water approximation; NOT claimed CIPM recommended precision.
    vapor = rh/100 * 611 * 10**(7.5*t/(237.3+t))
    return ((p-vapor)/(287.05*(t+273.15)) + vapor/(461.5*(t+273.15)),
            'ideal_moist_air_NWS_outside_CIPM_temperature_domain')


def components(speed, wind_from, bearing):
    speed = num(speed, 'wind_speed_mps', 0, 10)
    bearing = num(bearing, 'target_bearing_deg', 0, 360)
    if speed == 0:
        return (0., 0.)
    angle = math.radians(num(wind_from, 'wind_from_deg', 0, 360) - bearing)
    return (-speed*math.cos(angle), speed*math.sin(angle))  # forward, left


def environment(raw, now=None, max_age=None, historical=False):
    if not isinstance(raw, dict) or not isinstance(raw.get('source'), str) or not raw['source'].strip():
        raise InputError('environment source required')
    result = copy.deepcopy(raw)
    if not historical:
        age = (now-stamp(raw.get('observed_at'))).total_seconds()
        if age < 0 or age > max_age:
            raise InputError('weather stale or future-dated')
    else:
        stamp(raw.get('observed_at'))  # baseline provenance, not current-weather freshness
    if raw.get('station_pressure_pa') is None:
        result['station_pressure_pa'] = STANDARD_PRESSURE_PA
        result['pressure_kind'] = 'assumed_standard'
        result['pressure_assumption'] = True
    else:
        if raw.get('pressure_kind') != 'station':
            raise InputError('supplied pressure must be local station pressure, not sea_level')
        result['pressure_assumption'] = False
    rho, method = density(raw.get('temperature_c'), raw.get('relative_humidity_pct'),
                          result['station_pressure_pa'])
    result['density_kg_m3'], result['density_method'] = rho, method
    speed = num(raw.get('wind_speed_mps'), 'wind_speed_mps', 0, 10)
    if speed > 0:
        num(raw.get('wind_from_deg'), 'wind_from_deg', 0, 360)
    gust = raw.get('wind_gust_mps')
    if gust is not None:
        num(gust, 'wind_gust_mps', speed, 10)
    result['gust_available'] = gust is not None
    return result


def profile(raw):
    if not isinstance(raw, dict):
        raise InputError('carry profile required')
    out = copy.deepcopy(raw)
    for field in ('club_id', 'flight_group', 'ball_id', 'source', 'baseline_id'):
        if not isinstance(out.get(field), str) or not out[field].strip():
            raise InputError(f'profile.{field} required')
    if out.get('distance_type') != 'carry':
        raise InputError('baseline must be carry, not GPS total distance')
    out['baseline_carry'] = num(out.get('baseline_carry'), 'baseline_carry', 20, 350)
    if out.get('distance_unit') not in ('m', 'yd'):
        raise InputError('profile.distance_unit required (m/yd)')
    coeff = out.get('coefficients')
    if coeff is None:
        out['coefficients'] = copy.deepcopy(COEFFICIENTS)
        out['coefficient_status'] = 'engineering_prior_not_field_calibrated'
        out['coefficient_source'] = 'golf-caddie-v0.1.1 engineering intervals; not published constants'
    else:
        if not isinstance(coeff, dict):
            raise InputError('coefficients must be a named interval object')
        if set(coeff) != set(COEFFICIENTS):
            raise InputError('coefficient keys must match the four named model intervals')
        if not out.get('coefficient_source') or not out.get('coefficient_status'):
            raise InputError('personal coefficients require explicit source/status')
        for name, (low, high) in COEFF_LIMITS.items():
            bounds = coeff.get(name)
            if not isinstance(bounds, list) or len(bounds) != 2:
                raise InputError(f'{name}: two ordered bounds required')
            a, b = (num(v, name, low, high) for v in bounds)
            if a > b:
                raise InputError(f'{name}: reversed interval')
        if coeff['headwind_per_mps'][0] < coeff['tailwind_per_mps'][1]:
            raise InputError('headwind interval must not overlap weaker asymmetric tailwind interval')
    return out


def midpoints(p):
    return {k: sum(v)/2 for k, v in p['coefficients'].items()}


def evaluate(target, carry, base, current, bearing, c):
    rho0 = density(base['temperature_c'], base['relative_humidity_pct'], base['station_pressure_pa'])[0]
    rho = density(current['temperature_c'], current['relative_humidity_pct'], current['station_pressure_pa'])[0]
    forward, left = components(current['wind_speed_mps'], current.get('wind_from_deg'), bearing)
    head, tail = max(-forward, 0), max(forward, 0)
    wind_factor = 1 - c['headwind_per_mps']*head + c['tailwind_per_mps']*tail
    if not .65 <= wind_factor <= 1.25:
        raise InputError('wind response outside hybrid local-approximation domain')
    density_factor = (rho0/rho)**c['density_exponent']
    factor = density_factor * wind_factor
    equivalent = target / factor
    # Drift of the specified baseline-carry club, not automatic re-aim at target.
    drift = carry*density_factor*c['crosswind_per_mps']*left
    return {'equivalent': equivalent, 'drift_left': drift,
            'predicted_club_carry': carry*factor, 'carry_factor': factor,
            'wind_forward_mps': forward, 'wind_left_mps': left}


def shapley_ledger(target, carry, base, current, bearing, coeff):
    """Four-factor exact Shapley, 16 full-model evaluations; no double counting."""
    keys = ('station_pressure_pa', 'temperature_c', 'relative_humidity_pct', 'wind')
    cache = {}
    for mask in range(16):
        env = dict(base)
        for i, key in enumerate(keys):
            if mask & (1 << i):
                if key == 'wind':
                    env.update(wind_speed_mps=current['wind_speed_mps'], wind_from_deg=current.get('wind_from_deg'))
                else:
                    env[key] = current[key]
        cache[mask] = evaluate(target, carry, base, env, bearing, coeff)['equivalent']
    ledger = {}
    for i, key in enumerate(keys):
        value = 0.
        for mask in range(16):
            if mask & (1 << i):
                continue
            size = mask.bit_count()
            weight = math.factorial(size)*math.factorial(3-size)/math.factorial(4)
            value += weight*(cache[mask | (1 << i)]-cache[mask])
        ledger[key] = value
    if abs(target + sum(ledger.values()) - cache[15]) > 1e-7:
        raise InputError('Shapley ledger does not reconcile')
    return ledger


def display_range(values):
    """Outward integer display without amplifying sub-nanounit float noise."""
    def snap(value):
        nearest = round(value)
        return nearest if abs(value-nearest) < 1e-10 else value
    return [math.floor(snap(min(values))), math.ceil(snap(max(values)))]


def calculate(request, now=None):
    if not isinstance(request, dict) or request.get('mode') != 'hybrid':
        raise InputError('mode=hybrid required')
    if request.get('rules_mode') not in ('practice', 'informal'):
        raise InputError('hybrid adjustments disabled for competition/unknown rules mode')
    if request.get('height_difference_m') is not None:
        raise InputError('elevation correction not implemented')
    unit = request.get('distance_unit')
    if unit not in ('m', 'yd'):
        raise InputError('distance_unit m/yd required')
    scale = YARD_M if unit == 'yd' else 1.
    target = num(request.get('target_distance'), 'target_distance', 20, 350)*scale
    bearing = num(request.get('target_bearing_deg'), 'target_bearing_deg', 0, 360)
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise InputError('evaluation time must include timezone')
    max_age = num(request.get('max_weather_age_seconds'), 'max_weather_age_seconds', 1, 7200)
    current = environment(request.get('weather'), now, max_age)
    base = environment(request.get('baseline'), historical=True)
    if stamp(base['observed_at']) > now:
        raise InputError('baseline cannot originate in the future of the estimate')
    if base['wind_speed_mps'] != 0:
        raise InputError('baseline carry must refer to calm conditions; normalize separately')
    p = profile(request.get('profile'))
    if p['baseline_id'] != base.get('reference_id'):
        raise InputError('profile baseline_id does not match baseline reference_id')
    carry = p['baseline_carry'] * (YARD_M if p['distance_unit'] == 'yd' else 1.)
    if not .65 <= target/carry <= 1.35:
        raise InputError('target too far from this club baseline; choose a suitable carry profile')
    nominal = evaluate(target, carry, base, current, bearing, midpoints(p))
    ledger = shapley_ledger(target, carry, base, current, bearing, midpoints(p))
    raw_scenarios = request.get('weather_scenarios', [])
    if not isinstance(raw_scenarios, list) or len(raw_scenarios) > 24:
        raise InputError('at most 24 complete weather scenarios allowed')
    envs = [current] + [environment(e, now, max_age) for e in raw_scenarios]
    # Gust has same direction assumption; never silently invent directional variation.
    for env in list(envs):
        if env.get('wind_gust_mps') is not None and env['wind_gust_mps'] > env['wind_speed_mps']:
            gust_env = dict(env)
            gust_env['wind_speed_mps'] = env['wind_gust_mps']
            envs.append(gust_env)
    names = list(COEFFICIENTS)
    predictions = []
    for coefficients in itertools.product(*(p['coefficients'][key] for key in names)):
        c = dict(zip(names, coefficients))
        for env in envs:
            predictions.append(evaluate(target, carry, base, env, bearing, c))
    estimates = [r['equivalent']/scale for r in predictions]
    drift = [r['drift_left']/scale for r in predictions]
    reasons = []
    if p['coefficient_status'] == 'engineering_prior_not_field_calibrated':
        reasons.append('generic_engineering_priors_not_personal_measurements')
    if any(e['pressure_assumption'] for e in [base]+envs):
        reasons.append('standard_pressure_assumed_not_local_pressure')
    if any('outside' in e['density_method'] for e in [base]+envs):
        reasons.append('outside_CIPM_recommended_temperature_using_labeled_approximation')
    if not current['gust_available']:
        reasons.append('gust_not_available')
    reasons.append('elevation_unavailable_and_model_not_field_released')
    return {
        'engine_version': VERSION, 'model': 'carry_hybrid',
        'status': 'estimated_range_not_field_validated', 'recommendation_allowed': False,
        'raw_horizontal_distance': target/scale, 'distance_unit': unit,
        'target_bearing_deg': bearing, 'baseline_carry': carry/scale,
        'playing_distance_range': display_range(estimates),
        'model_range_unrounded': [min(estimates), max(estimates)],
        'range_kind': 'coefficient_envelope_and_finite_weather_scenarios_not_confidence_interval',
        'nominal_for_audit_not_exact_advice': nominal['equivalent']/scale,
        'lateral_drift_left_range': [min(drift), max(drift)],
        'lateral_definition': 'baseline_club_carry_drift_not_automatic_aim_offset',
        'nominal_club_carry': nominal['predicted_club_carry']/scale,
        'shapley_adjustments': {k: v/scale for k, v in ledger.items()},
        'attribution': 'symmetric_four_factor_full_model_Shapley_not_independent_extra_adjustments',
        'wind_components': {k: nominal[k] for k in ('wind_forward_mps', 'wind_left_mps')},
        'confidence': {'level': 'low' if len(reasons) > 1 else 'unvalidated',
                       'reasons': reasons, 'probability': None},
        'height_difference': 'unavailable_not_measured_zero', 'roll': 'excluded_carry_only',
        'evaluated_at': now.isoformat(), 'weather_scenario_count': len(envs),
        'provenance': {'weather': current, 'baseline': base, 'profile': p,
                       'weather_scenarios': envs, 'max_weather_age_seconds': max_age},
        'limitations': [
            'Pressure fallback does not bound unknown local pressure or altitude.',
            'Range excludes unprovided wind-direction/height variability and player dispersion.',
            'Carry baseline must have known reference conditions; GPS total cannot replace it.',
            'No hidden updates to coefficient profiles; calibration returns a proposal.',
        ],
    }


def propose_calibration(training, validation, raw_profile, baseline):
    """Constrained grid/least-squares + shrinkage + separate-round validation.

    Returns a proposal only. Synthetic self-tests are not a personal calibration.
    Samples are confirmed carry of the same stock club/ball/flight/lie group;
    callers must independently verify those labels and data authority.
    """
    p = profile(raw_profile)
    base = environment(baseline, historical=True)
    if p['baseline_id'] != base.get('reference_id'):
        raise InputError('calibration baseline identity mismatch')
    if base['pressure_assumption'] or base['wind_speed_mps'] != 0:
        raise InputError('calibration needs explicit local reference pressure and calm baseline')
    scale = YARD_M if p['distance_unit'] == 'yd' else 1.
    carry = p['baseline_carry'] * scale
    identifiers = set()

    def rows(samples):
        if not isinstance(samples, list):
            raise InputError('calibration samples must be lists')
        out = []
        for s in samples:
            if not isinstance(s, dict):
                raise InputError('sample must be an object')
            for field in ('sample_id', 'round_id', 'club_id', 'flight_group', 'ball_id'):
                if not isinstance(s.get(field), str) or not s[field]:
                    raise InputError(f'{field} required')
            if s['sample_id'] in identifiers:
                raise InputError('duplicate/leaking calibration sample')
            identifiers.add(s['sample_id'])
            if any(s[k] != p[k] for k in ('club_id', 'flight_group', 'ball_id')):
                raise InputError('mixed club/flight/ball group')
            if s.get('distance_type') != 'carry' or s.get('confirmed') is not True or s.get('comparable_lie') is not True:
                raise InputError('calibration requires confirmed comparable carry, not GPS total/candidates')
            if s.get('height_difference_m') != 0:
                raise InputError('calibration needs independently confirmed flat landing geometry')
            if s.get('distance_unit') not in ('m', 'yd'):
                raise InputError('sample distance_unit required')
            shot_time = stamp(s.get('shot_at'))
            env = environment(s.get('weather'), now=shot_time, max_age=1800)
            if env['pressure_assumption']:
                raise InputError('calibration cannot fit against assumed local pressure')
            forward, left = components(env['wind_speed_mps'], env.get('wind_from_deg'), s.get('target_bearing_deg'))
            distance = num(s.get('measured_carry'), 'measured_carry', 10, 400)*(YARD_M if s['distance_unit']=='yd' else 1.)
            out.append((s, env, forward, left, distance))
        return out

    train, valid = rows(training), rows(validation)
    if {r[0]['round_id'] for r in train} & {r[0]['round_id'] for r in valid}:
        raise InputError('validation rounds must be separate from training rounds')
    def coverage(rs, minimum, rounds):
        return (len(rs) >= minimum and len({r[0]['round_id'] for r in rs}) >= rounds
                and sum(r[2] <= -2 for r in rs) >= minimum//4
                and sum(r[2] >= 2 for r in rs) >= minimum//4
                and sum(r[1]['wind_speed_mps'] < .5 for r in rs) >= minimum//4)
    if not coverage(train, 24, 3) or not coverage(valid, 12, 2):
        return {'engine_version': VERSION, 'status': 'keep_prior_insufficient_comparable_coverage', 'profile': p}
    rho0 = base['density_kg_m3']
    if max(r[1]['density_kg_m3'] for r in train)/min(r[1]['density_kg_m3'] for r in train) < 1.02:
        return {'engine_version': VERSION, 'status': 'keep_prior_density_not_identifiable', 'profile': p}
    previous = midpoints(p)
    best = None
    for i in range(76):
        beta = i/50
        grouped = {'head': [], 'tail': []}
        for s, env, forward, left, measured in train:
            f = (rho0/env['density_kg_m3'])**beta
            y = measured/(carry*f)-1
            if forward <= -2:
                grouped['head'].append((-forward, -y))
            elif forward >= 2:
                grouped['tail'].append((forward, y))
        def slope(group):
            return sum(x*y for x,y in group)/sum(x*x for x,y in group)
        head, tail = slope(grouped['head']), slope(grouped['tail'])
        if not 0 <= tail <= .03 or not tail <= head <= .04:
            continue
        candidate = dict(previous, density_exponent=beta, headwind_per_mps=head, tailwind_per_mps=tail)
        try:
            error = sum((evaluate(carry,carry,base,e,s['target_bearing_deg'],candidate)['predicted_club_carry']-d)**2
                        for s,e,fw,l,d in train)
        except InputError:
            continue
        if best is None or error < best[0]:
            best = error, candidate
    if best is None:
        return {'engine_version': VERSION, 'status': 'keep_prior_fit_outside_constraints', 'profile': p}
    weight = len(train)/(len(train)+30)  # engineering shrinkage policy, not a statistical posterior
    center = {k: previous[k]*(1-weight)+best[1][k]*weight for k in previous}
    # Lateral drift is fitted only when separately observed; no drift => keep old prior.
    lateral = []
    for s,e,forward,left,d in train:
        if s.get('drift_left') is not None and s.get('drift_confirmed') is True and abs(left)>=2:
            measured = num(s['drift_left'], 'drift_left', -100, 100)*(YARD_M if s['distance_unit']=='yd' else 1.)
            x = carry*(rho0/e['density_kg_m3'])**center['density_exponent']*left
            lateral.append((x,measured))
    lateral_valid = []
    for s,e,forward,left,d in valid:
        if s.get('drift_left') is not None and s.get('drift_confirmed') is True and abs(left)>=2:
            measured = num(s['drift_left'], 'drift_left', -100, 100)*(YARD_M if s['distance_unit']=='yd' else 1.)
            x = carry*(rho0/e['density_kg_m3'])**center['density_exponent']*left
            lateral_valid.append((x,measured))
    lateral_accepted = False
    if len(lateral)>=12 and len(lateral_valid)>=6:
        fitted = sum(x*y for x,y in lateral)/sum(x*x for x,y in lateral)
        if 0 <= fitted <= .03:
            proposed = previous['crosswind_per_mps']*(1-weight)+fitted*weight
            old_error = statistics.mean(abs(x*previous['crosswind_per_mps']-y) for x,y in lateral_valid)
            new_error = statistics.mean(abs(x*proposed-y) for x,y in lateral_valid)
            if old_error > 1e-6 and new_error <= .9*old_error:
                center['crosswind_per_mps'] = proposed
                lateral_accepted = True
    def mae(c):
        return statistics.mean(abs(evaluate(carry,carry,base,e,s['target_bearing_deg'],c)['predicted_club_carry']-d)
                               for s,e,f,l,d in valid)
    before, after = mae(previous), mae(center)
    if before <= 1e-6 or after > .9*before:
        return {'engine_version': VERSION, 'status': 'keep_prior_no_holdout_improvement',
                'holdout_mae_before_m': before, 'holdout_mae_after_m': after, 'profile': p}
    candidate_profile = copy.deepcopy(p)
    intervals = {}
    for k in previous:
        half = max((p['coefficients'][k][1]-p['coefficients'][k][0])/2 * (1-.5*weight), 1e-5)
        low,high = COEFF_LIMITS[k]
        intervals[k] = [max(low,center[k]-half),min(high,center[k]+half)]
    # preserve the asymmetric-interval invariant by only narrowing overlap at the midpoint.
    if intervals['headwind_per_mps'][0] < intervals['tailwind_per_mps'][1]:
        split=(center['headwind_per_mps']+center['tailwind_per_mps'])/2
        intervals['headwind_per_mps'][0]=split
        intervals['tailwind_per_mps'][1]=split
    if not lateral_accepted:
        intervals['crosswind_per_mps'] = p['coefficients']['crosswind_per_mps'][:]
    candidate_profile.update(coefficients=intervals, coefficient_status='personal_candidate_pending_release',
                             coefficient_source='constrained fit + shrinkage + separate-round holdout',
                             calibration={'training_count':len(train),'validation_count':len(valid),
                                          'training_sample_ids':[r[0]['sample_id'] for r in train],
                                          'validation_sample_ids':[r[0]['sample_id'] for r in valid],
                                          'holdout_mae_before_m':before,'holdout_mae_after_m':after,
                                          'shrinkage_weight':weight,'lateral_holdout_accepted':lateral_accepted,'engine_version':VERSION})
    profile(candidate_profile)
    return {'engine_version':VERSION, 'status':'personal_candidate_pending_release',
            'auto_applied':False,'profile':candidate_profile}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',help='JSON input, or - for stdin')
    parser.add_argument('--as-of',help='explicit offline replay time, not live weather')
    args=parser.parse_args()
    try:
        if args.input=='-':
            request=json.load(sys.stdin)
        else:
            with open(args.input,encoding='utf-8') as stream:
                request=json.load(stream)
        if not isinstance(request, dict):
            raise InputError('JSON request must be an object')
        if request.get('action')=='calibrate':
            result=propose_calibration(request.get('training'),request.get('validation'),request.get('profile'),request.get('baseline'))
        else:
            result=calculate(request,stamp(args.as_of) if args.as_of else None)
        result['time_mode']='historical_replay' if args.as_of else 'current_utc_or_calibration_history'
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0
    except (InputError, ValueError, TypeError, KeyError, OSError) as exc:
        print(json.dumps({'engine_version':VERSION,'status':'unavailable','error':str(exc)},ensure_ascii=False))
        return 2


if __name__=='__main__':
    sys.exit(main())
