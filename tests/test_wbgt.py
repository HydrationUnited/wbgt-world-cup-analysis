"""Unit tests for worldcupheat.wbgt — humidity, solar geometry, and Liljegren WBGT.

The Liljegren pins are reference values computed with thermofeel 2.2.0
(calculate_wbgt_liljegren), which this module ports to numba; the port matches
the reference to <1e-6 K, so the tolerances below are dominated by pin rounding.
"""
import numpy as np
import pandas as pd
import pytest

from worldcupheat import wbgt


class TestHumidity:
    def test_sat_vapor_pressure_at_freezing(self):
        # Buck (1996): es(0 C) = 6.1121 hPa by construction
        assert wbgt.sat_vapor_pressure_hpa(0.0) == pytest.approx(6.1121, abs=1e-3)

    def test_sat_vapor_pressure_at_20c(self):
        # standard tables: es(20 C) ~ 23.4 hPa
        assert wbgt.sat_vapor_pressure_hpa(20.0) == pytest.approx(23.4, abs=0.2)

    def test_vapor_pressure_is_es_at_dewpoint(self):
        assert wbgt.vapor_pressure_hpa(15.0) == wbgt.sat_vapor_pressure_hpa(15.0)

    def test_rh_saturated_when_td_equals_t(self):
        assert wbgt.rh_from_t_td(25.0, 25.0) == pytest.approx(100.0)

    def test_rh_clipped_to_100(self):
        # Td > T is unphysical but must not exceed 100 %
        assert wbgt.rh_from_t_td(20.0, 25.0) == 100.0

    def test_rh_decreases_with_dewpoint_depression(self):
        rh = wbgt.rh_from_t_td(30.0, np.array([30.0, 20.0, 10.0, 0.0]))
        assert np.all(np.diff(rh) < 0)

    def test_k2c(self):
        assert wbgt.k2c(273.15) == pytest.approx(0.0)
        np.testing.assert_allclose(wbgt.k2c(np.array([273.15, 300.0])), [0.0, 26.85])

    def test_wind_speed(self):
        assert wbgt.wind_speed(3.0, 4.0) == pytest.approx(5.0)
        assert wbgt.wind_speed(0.0, 0.0) == 0.0


class TestCosSolarZenith:
    def test_equinox_noon_overhead_at_origin(self):
        # 2000-03-20 (equinox) 12:00 UTC at (0, 0): sun ~overhead
        idx = pd.DatetimeIndex(["2000-03-20 12:00"])
        cza = wbgt.cos_solar_zenith(idx, 0.0, 0.0)
        assert cza[0] == pytest.approx(1.0, abs=0.02)

    def test_negative_at_midnight(self):
        idx = pd.DatetimeIndex(["2000-03-20 00:00"])
        assert wbgt.cos_solar_zenith(idx, 0.0, 0.0)[0] < 0.0

    def test_array_over_a_day_has_one_day_night_cycle(self):
        idx = pd.date_range("2014-06-12", periods=24, freq="1h")
        cza = wbgt.cos_solar_zenith(idx, -22.9, -43.2)  # Rio de Janeiro
        assert cza.shape == (24,)
        assert cza.max() > 0.5 and cza.min() < -0.5  # day and night both occur

    def test_tz_aware_index_accepted(self):
        naive = pd.DatetimeIndex(["2000-03-20 12:00"])
        aware = naive.tz_localize("UTC")
        np.testing.assert_allclose(wbgt.cos_solar_zenith(aware, 0.0, 0.0),
                                   wbgt.cos_solar_zenith(naive, 0.0, 0.0))


class TestWbgtLiljegren:
    # ((t2m_K, rh_pct, sp_hPa, wind_ms, ssrd_Wm2, fdir_frac, cossza), WBGT degC)
    # reference values from thermofeel 2.2.0 calculate_wbgt_liljegren
    PINS = [
        ((303.15, 50.0, 1013.25, 2.0, 800.0, 0.8, 0.9), 28.862457),
        ((303.15, 50.0, 1013.25, 2.0, 0.0, 0.0, 0.0), 24.153805),
        ((313.15, 20.0, 1013.25, 0.5, 1000.0, 0.9, 0.95), 35.343408),
        ((298.15, 80.0, 1013.25, 3.0, 400.0, 0.5, 0.5), 25.864782),
        ((288.15, 60.0, 900.0, 5.0, 600.0, 0.7, 0.7), 15.206385),
        ((308.15, 65.0, 1000.0, 1.0, 950.0, 0.85, 0.99), 36.892609),
    ]

    @pytest.mark.parametrize("args,expected", PINS)
    def test_thermofeel_reference_pins(self, args, expected):
        assert float(wbgt.wbgt_liljegren(*args)) == pytest.approx(expected, abs=0.05)

    def test_daytime_solar_load_exceeds_night(self):
        t2m, rh, sp, wind = 303.15, 50.0, 1013.25, 2.0
        day = wbgt.wbgt_liljegren(t2m, rh, sp, wind, 800.0, 0.8, 0.9)
        night = wbgt.wbgt_liljegren(t2m, rh, sp, wind, 0.0, 0.0, -0.3)
        assert np.isfinite(day) and np.isfinite(night)
        assert day > night
        # plausible WBGT range for 30 C / 50 % RH
        assert 15.0 < night < day < 45.0

    def test_vectorized_matches_scalar_loop(self):
        args = np.array([a for a, _ in self.PINS], dtype=float).T  # (7, n)
        vec = wbgt.wbgt_liljegren(*args)
        loop = np.array([float(wbgt.wbgt_liljegren(*a)) for a, _ in self.PINS])
        assert vec.shape == (len(self.PINS),)
        np.testing.assert_allclose(vec, loop, rtol=0, atol=0)

    def test_zero_wind_is_finite(self):
        # wind is floored internally (0.13 m/s, then the KNMI 10 m minimum)
        out = wbgt.wbgt_liljegren(303.15, 50.0, 1013.25, 0.0, 800.0, 0.8, 0.9)
        assert np.isfinite(out)

    def test_negative_cossza_treated_as_night(self):
        a = wbgt.wbgt_liljegren(303.15, 50.0, 1013.25, 2.0, 0.0, 0.0, -0.5)
        b = wbgt.wbgt_liljegren(303.15, 50.0, 1013.25, 2.0, 0.0, 0.0, 0.0)
        assert float(a) == pytest.approx(float(b), abs=1e-9)

    def test_nan_input_gives_nan(self):
        assert np.isnan(wbgt.wbgt_liljegren(np.nan, 50.0, 1013.25, 2.0, 800.0, 0.8, 0.9))
