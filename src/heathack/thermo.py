"""Thermodynamics: humidity, thermodynamic wet-bulb temperature (T_w), and WBGT.

References:
  - Buck, A.L. (1981/1996): saturation vapour pressure over water.
  - Stull, R. (2011, J.Appl.Meteor.Climatol.): empirical T_w from T & RH (~sea level).
  - Davies-Jones (2008): accurate adiabatic wet-bulb (via metpy).
  - Australian BoM: simplified shade WBGT ~ 0.567 Ta + 0.393 e + 3.94 (e in hPa).
  - ACSM/indoor: WBGT ~ 0.7 Tnwb + 0.3 Ta (no-solar approximation).

Units: functions take EITHER Kelvin or Celsius as named; be explicit. Arrays OK
(numpy-vectorised). Pressure in Pa unless _hpa suffix.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

ZERO_C = 273.15


# ---------------------------------------------------------------- humidity ---
def sat_vapor_pressure_hpa(T_C):
    """Saturation vapour pressure over water [hPa], Buck (1996). T in deg C."""
    T_C = np.asarray(T_C, dtype=float)
    return 6.1121 * np.exp((18.678 - T_C / 234.5) * (T_C / (257.14 + T_C)))


def vapor_pressure_hpa(Td_C):
    """Actual vapour pressure e [hPa] from dewpoint (= es evaluated at Td)."""
    return sat_vapor_pressure_hpa(Td_C)


def rh_from_t_td(T_C, Td_C):
    """Relative humidity [%] from temperature and dewpoint (deg C)."""
    rh = 100.0 * sat_vapor_pressure_hpa(Td_C) / sat_vapor_pressure_hpa(T_C)
    return np.clip(rh, 0.0, 100.0)


def k2c(T_K):
    return np.asarray(T_K, dtype=float) - ZERO_C


# ------------------------------------------- thermodynamic wet-bulb (T_w) ---
def wet_bulb_stull(T_C, RH_pct):
    """Stull (2011) empirical thermodynamic wet-bulb temperature [deg C].

    T_w = T*atan(0.151977*(RH+8.313659)^0.5) + atan(T+RH) - atan(RH-1.676331)
          + 0.00391838*RH^1.5 * atan(0.023101*RH) - 4.686035
    Valid ~1013.25 hPa (sea level), T in [-20,50] C, RH in [5,99] %.
    Accuracy ~<1 C over that range; degrades at high altitude / low pressure.
    """
    T = np.asarray(T_C, dtype=float)
    RH = np.asarray(RH_pct, dtype=float)
    return (T * np.arctan(0.151977 * np.sqrt(RH + 8.313659))
            + np.arctan(T + RH)
            - np.arctan(RH - 1.676331)
            + 0.00391838 * RH ** 1.5 * np.arctan(0.023101 * RH)
            - 4.686035)


def wet_bulb_metpy(T_K, Td_K, p_Pa):
    """Accurate thermodynamic wet-bulb [deg C] via metpy (Normand/Davies-Jones).

    Handles arbitrary pressure (correct at altitude). Iterative -> slow for big
    arrays; use for validation or modest sets. Input arrays broadcast together.
    """
    import metpy.calc as mpcalc
    from metpy.units import units
    p = np.asarray(p_Pa, dtype=float) * units.Pa
    T = np.asarray(T_K, dtype=float) * units.K
    Td = np.asarray(Td_K, dtype=float) * units.K
    tw = mpcalc.wet_bulb_temperature(p, T, Td)
    return tw.to("degC").magnitude


# ------------------------------------------------------------------- WBGT ---
def wbgt_shade_bom(T_C, e_hPa):
    """Simplified SHADE WBGT [deg C], Australian BoM approximation.

    WBGT ~ 0.567*Ta + 0.393*e + 3.94 ;  e = actual vapour pressure [hPa].
    No solar/wind term -> underestimates full outdoor (in-sun) WBGT. Good, fast,
    and reproducible baseline when solar radiation is unavailable.
    """
    T = np.asarray(T_C, dtype=float)
    e = np.asarray(e_hPa, dtype=float)
    return 0.567 * T + 0.393 * e + 3.94


def wbgt_indoor_from_tw(Tw_C, T_C):
    """No-solar (indoor) WBGT [deg C] = 0.7*Tw + 0.3*Ta (natural wet-bulb ~ Tw)."""
    return 0.7 * np.asarray(Tw_C, float) + 0.3 * np.asarray(T_C, float)


# -------------------------------------------- physical (Liljegren) WBGT ------
def wind_speed(u, v):
    return np.hypot(np.asarray(u, float), np.asarray(v, float))


def cos_solar_zenith(times_utc, lat, lon):
    """Cosine of solar zenith angle via pvlib. times_utc: pandas DatetimeIndex (UTC).

    Returns array aligned to times_utc; negative at night (sun below horizon).
    """
    import pvlib
    idx = pd.DatetimeIndex(times_utc)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    sp = pvlib.solarposition.get_solarposition(idx, lat, lon)
    return np.cos(np.radians(sp["zenith"].values))


def wbgt_liljegren(t2m_K, rh_pct, sp_hPa, wind_ms, ssrd_Wm2, fdir_frac, cossza):
    """Physical sunlit Liljegren WBGT [deg C] via thermofeel.

    WBGT = 0.7*Tnwb + 0.2*Tg + 0.1*Ta with globe & natural-wet-bulb solved from
    steady-state energy balance (Liljegren et al. 2008). fdir_frac is the direct-beam
    FRACTION (0-1). Returns deg C.
    """
    import thermofeel as tf
    cz = np.clip(np.asarray(cossza, float), 0.0, 1.0)          # night -> 0
    wbgt_K = tf.calculate_wbgt_liljegren(
        np.asarray(t2m_K, float), np.asarray(rh_pct, float),
        np.asarray(sp_hPa, float), np.maximum(np.asarray(wind_ms, float), 0.13),
        np.asarray(ssrd_Wm2, float), np.asarray(fdir_frac, float), cz)
    return wbgt_K - ZERO_C


# ------------------------------------------------------ convenience wrapper ---
def compute_from_era5(t2m_K, d2m_K, sp_Pa, kind="wet_bulb", method="stull"):
    """Compute a heat metric [deg C] from ERA5 raw fields.

    kind: 'wet_bulb' (thermodynamic T_w) or 'wbgt_shade' (BoM shade WBGT) or
          'wbgt_indoor' (0.7 Tw + 0.3 Ta).
    method (for wet_bulb): 'stull' (fast, ~sea level) or 'metpy' (accurate, slow).
    """
    Tc = k2c(t2m_K)
    Tdc = k2c(d2m_K)
    if kind == "wet_bulb":
        if method == "metpy":
            return wet_bulb_metpy(t2m_K, d2m_K, sp_Pa)
        return wet_bulb_stull(Tc, rh_from_t_td(Tc, Tdc))
    if kind == "wbgt_shade":
        return wbgt_shade_bom(Tc, vapor_pressure_hpa(Tdc))
    if kind == "wbgt_indoor":
        tw = wet_bulb_stull(Tc, rh_from_t_td(Tc, Tdc))
        return wbgt_indoor_from_tw(tw, Tc)
    raise ValueError(f"unknown kind={kind!r}")
