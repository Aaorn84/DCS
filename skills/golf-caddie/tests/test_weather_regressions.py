"""Release regressions written before implementation fixes."""
from datetime import datetime
import unittest
from test_weather_hybrid import h, request, prof, env, samples, NOW


class WeatherReleaseRegressions(unittest.TestCase):
    def test_calm_yard_display_does_not_invent_one_yard_range(self):
        result=h.calculate(request(target_distance=29,distance_unit='yd',
                                   profile=prof(baseline_carry=29,distance_unit='yd')),NOW)
        self.assertEqual(result['playing_distance_range'],[29,29])

    def test_future_baseline_must_not_be_used_for_current_estimate(self):
        with self.assertRaises(h.InputError):
            h.calculate(request(baseline=env(reference_id='test-ref',observed_at='2026-11-07T00:00:00Z')),NOW)

    def test_crosswind_samples_do_not_satisfy_calm_training_coverage(self):
        train,validation=samples('train',3),samples('valid',2)
        for s in train:
            if s['weather']['wind_speed_mps']==0:
                s['weather'].update(wind_speed_mps=4,wind_from_deg=90,wind_gust_mps=4)
        result=h.propose_calibration(train,validation,prof(),env(reference_id='test-ref'))
        self.assertEqual(result['status'],'keep_prior_insufficient_comparable_coverage')

    def test_unknown_coefficient_keys_are_rejected_at_input_boundary(self):
        coeff={key:value[:] for key,value in h.COEFFICIENTS.items()}
        coeff['unexpected_adjustment']=5
        with self.assertRaises(h.InputError):
            h.calculate(request(profile=prof(coefficients=coeff,coefficient_source='synthetic',
                                              coefficient_status='personal_candidate')),NOW)

    def test_invalid_clock_type_is_input_error_not_internal_exception(self):
        for clock in ('2026-11-06',123,datetime(2026,11,6)):
            with self.subTest(clock=str(clock)):
                with self.assertRaises(h.InputError):h.calculate(request(),clock)


if __name__=='__main__':unittest.main()
