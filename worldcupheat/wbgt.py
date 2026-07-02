"""WBGT after Liljegren et al. (2008), plus humidity and solar-geometry helpers.

The Liljegren physics (property functions, energy-balance solvers, wind-profile
scaling, KNMI operational guards) is transcribed verbatim from thermofeel 2.2.0
(ECMWF, Apache-2.0), itself validated bit-for-bit against Liljegren's reference
C code (github.com/mdljts/wbgt). Here the solvers are compiled scalar functions
(numba @njit) exposed through a ufunc, so no thermofeel/pvlib dependency remains.

References:
  - Liljegren et al. (2008): https://doi.org/10.1080/15459620802310770
  - Kong & Huber (2022): https://doi.org/10.1029/2021EF002334
  - Buck, A.L. (1981/1996): saturation vapour pressure over water.
  - Spencer (1971): Fourier-series solar declination and equation of time.

Units: functions take EITHER Kelvin or Celsius as named; be explicit. Arrays OK
(ufunc-vectorised). Pressure in hPa unless stated otherwise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit, vectorize

ZERO_C = 273.15

# Physical constants (Liljegren et al. 2008; mdljts/wbgt header)
STEFANB = 5.6696e-8            # Stefan-Boltzmann constant [W m-2 K-4]
CP = 1003.5                    # specific heat of dry air [J kg-1 K-1]
M_AIR = 28.97                  # molar mass of dry air [g mol-1]
M_H2O = 18.015                 # molar mass of water [g mol-1]
R_GAS = 8314.34                # universal gas constant [J kmol-1 K-1]
R_AIR = R_GAS / M_AIR          # gas constant for air [J kg-1 K-1]
PR = CP / (CP + 1.25 * R_AIR)  # Prandtl number
RATIO = CP * M_AIR / M_H2O     # psychrometric grouping
EMIS_WICK = 0.95
ALB_WICK = 0.4
D_WICK = 0.007                 # wick diameter [m]
L_WICK = 0.0254                # wick length [m]
EMIS_GLOBE = 0.95
ALB_GLOBE = 0.05
D_GLOBE = 0.0508               # globe diameter [m]
EMIS_SFC = 0.999
ALB_SFC = 0.45
CZA_MIN = 0.00873              # cos(89.5 deg): below this the sun is treated as down
MIN_SPEED = 0.13               # floor on wind speed in the Reynolds number [m/s]
CONVERGENCE = 0.02             # iteration tolerance [K]
MAX_ITER = 500                 # iteration cap
MIN_WIND_10M = 0.62            # KNMI minimum 10 m wind (~0.5 m/s at 2 m) [m/s]

# Pasquill-Gifford stability lookup for the 10 m -> 2 m wind profile
# (Liljegren et al. 2008; Kong & Huber 2022). Rows are wind-speed bins, columns
# are solar-radiation / night bins; the value is the stability class.
LSRDT = np.array(
    [
        [1, 1, 2, 4, 0, 5, 6, 0],
        [1, 2, 3, 4, 0, 5, 6, 0],
        [2, 2, 3, 4, 0, 4, 4, 0],
        [3, 3, 4, 4, 0, 0, 0, 0],
        [3, 4, 4, 4, 0, 0, 0, 0],
        [0, 0, 0, 0, 0, 0, 0, 0],
    ]
)
# Wind-profile power-law exponent per stability class (urban terrain).
URBAN_EXP = np.array([0.15, 0.15, 0.20, 0.25, 0.30, 0.30])


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


def wind_speed(u, v):
    return np.hypot(np.asarray(u, float), np.asarray(v, float))


# ------------------------------------------------------------ solar zenith ---
@njit(cache=True)
def _cos_sza_core(doy, hour_utc, lat_deg, lon_deg):
    """Spencer (1971) low-precision solar position; ~0.5 deg accuracy."""
    lat = np.radians(lat_deg)
    out = np.empty(doy.shape[0])
    for i in range(doy.shape[0]):
        g = 2.0 * np.pi * (doy[i] - 1.0 + (hour_utc[i] - 12.0) / 24.0) / 365.0
        dec = (0.006918 - 0.399912 * np.cos(g) + 0.070257 * np.sin(g)
               - 0.006758 * np.cos(2.0 * g) + 0.000907 * np.sin(2.0 * g)
               - 0.002697 * np.cos(3.0 * g) + 0.00148 * np.sin(3.0 * g))
        eqt_min = 229.18 * (0.000075 + 0.001868 * np.cos(g) - 0.032077 * np.sin(g)
                            - 0.014615 * np.cos(2.0 * g) - 0.040849 * np.sin(2.0 * g))
        ha = np.radians(15.0 * (hour_utc[i] + eqt_min / 60.0 - 12.0) + lon_deg)
        out[i] = np.sin(lat) * np.sin(dec) + np.cos(lat) * np.cos(dec) * np.cos(ha)
    return out


def cos_solar_zenith(times_utc, lat, lon):
    """Cosine of solar zenith angle. times_utc: pandas DatetimeIndex (UTC).

    Returns array aligned to times_utc; negative at night (sun below horizon).
    Spencer (1971) declination + equation of time; accurate to ~0.5 deg.
    """
    idx = pd.DatetimeIndex(times_utc)
    if idx.tz is not None:
        idx = idx.tz_convert("UTC").tz_localize(None)
    doy = idx.dayofyear.to_numpy().astype(np.float64)
    hour = ((idx - idx.normalize()) / pd.Timedelta(hours=1)).to_numpy().astype(np.float64)
    return _cos_sza_core(doy, hour, float(lat), float(lon))


# ---------------------------------------- Liljegren property functions -------
@njit(cache=True)
def _esat(tk):
    """Saturation vapour pressure over liquid water [hPa], Buck (1981)."""
    y = (tk - 273.15) / (tk - 32.18)
    return 1.004 * 6.1121 * np.exp(17.502 * y)


@njit(cache=True)
def _dew_point(e):
    """Dew-point temperature [K] from vapour pressure [hPa] (inverse of _esat)."""
    z = np.log(e / (6.1121 * 1.004))
    return 273.15 + 240.97 * z / (17.502 - z)


@njit(cache=True)
def _viscosity(tk):
    """Dynamic viscosity of air [kg m-1 s-1] (Bird, Stewart & Lightfoot)."""
    sigma = 3.617
    eps_kappa = 97.0
    tr = tk / eps_kappa
    omega = (tr - 2.9) / 0.4 * (-0.034) + 1.048
    return 2.6693e-6 * np.sqrt(M_AIR * tk) / (sigma * sigma * omega)


@njit(cache=True)
def _thermal_cond(tk):
    """Thermal conductivity of air [W m-1 K-1] (Eucken relation)."""
    return (CP + 1.25 * R_AIR) * _viscosity(tk)


@njit(cache=True)
def _diffusivity(tk, pair):
    """Diffusivity of water vapour in air [m2 s-1]; pair in hPa (BSL p.505)."""
    pcrit_air = 36.4
    pcrit_h2o = 218.0
    tcrit_air = 132.0
    tcrit_h2o = 647.3
    a = 3.640e-4
    b = 2.334
    pcrit13 = (pcrit_air * pcrit_h2o) ** (1.0 / 3.0)
    tcrit512 = (tcrit_air * tcrit_h2o) ** (5.0 / 12.0)
    tcrit12 = np.sqrt(tcrit_air * tcrit_h2o)
    mmix = np.sqrt(1.0 / M_AIR + 1.0 / M_H2O)
    patm = pair / 1013.25
    return a * (tk / tcrit12) ** b * pcrit13 * tcrit512 * mmix / patm * 1e-4


@njit(cache=True)
def _evap(tk):
    """Latent heat of vaporisation [J kg-1], valid 283-313 K."""
    return (313.15 - tk) / 30.0 * (-71100.0) + 2.4073e6


@njit(cache=True)
def _emis_atm(tk, rh):
    """Clear-sky atmospheric emissivity; rh as fraction (Oke 2nd ed.)."""
    e = rh * _esat(tk)
    return 0.575 * e**0.143


@njit(cache=True)
def _h_sphere_in_air(tk, pair, speed):
    """Convective heat-transfer coefficient for the globe (sphere) [W m-2 K-1]."""
    density = pair * 100.0 / (R_AIR * tk)
    re = max(speed, MIN_SPEED) * density * D_GLOBE / _viscosity(tk)
    nu = 2.0 + 0.6 * np.sqrt(re) * PR**0.3333
    return nu * _thermal_cond(tk) / D_GLOBE


@njit(cache=True)
def _h_cylinder_in_air(tk, pair, speed):
    """Convective heat-transfer coefficient for the wick (cylinder) [W m-2 K-1]."""
    a = 0.56
    b = 0.281
    c = 0.4
    density = pair * 100.0 / (R_AIR * tk)
    re = max(speed, MIN_SPEED) * density * D_WICK / _viscosity(tk)
    nu = b * re ** (1.0 - c) * PR ** (1.0 - a)
    return nu * _thermal_cond(tk) / D_WICK


# ------------------------------------------- Liljegren energy balances -------
@njit(cache=True)
def _solve_globe(ta, rh, pair, speed, solar, fdir, cza):
    """Globe temperature [degC] by fixed-point iteration of the energy balance.

    ``rh`` is a fraction. NaN where the iteration does not converge.
    """
    tsfc = ta
    emis = _emis_atm(ta, rh)
    # Direct-beam geometry term; guarded so fdir == 0 contributes 0 even when the
    # sun is at/below the horizon (cza -> 0), avoiding 0 * inf. The max() is a
    # no-op (cza_safe > CZA_MIN always) that keeps the compiler from speculating
    # a divide-by-zero when it evaluates both arms of the select at night.
    cza_safe = cza if cza > CZA_MIN else 1.0
    denom = max(2.0 * cza_safe, 2.0 * CZA_MIN)
    beam = fdir * (1.0 / denom - 1.0) if fdir > 0.0 else 0.0

    tg_prev = ta
    for _ in range(MAX_ITER):
        tref = 0.5 * (tg_prev + ta)
        h = _h_sphere_in_air(tref, pair, speed)
        tg_new = (
            0.5 * (emis * ta**4 + EMIS_SFC * tsfc**4)
            - h / (STEFANB * EMIS_GLOBE) * (tg_prev - ta)
            + solar / (2.0 * STEFANB * EMIS_GLOBE) * (1.0 - ALB_GLOBE)
            * (beam + 1.0 + ALB_SFC)
        ) ** 0.25
        if abs(tg_new - tg_prev) < CONVERGENCE:
            return tg_new - 273.15
        tg_prev = 0.9 * tg_prev + 0.1 * tg_new
    return np.nan


@njit(cache=True)
def _solve_wetbulb(ta, rh, pair, speed, solar, fdir, cza, rad):
    """Wet-bulb temperature [degC] by fixed-point iteration of the energy balance.

    ``rh`` is a fraction. With ``rad=1`` this is the natural wet-bulb temperature
    (the term entering WBGT); ``rad=0`` gives the psychrometric wet bulb. NaN
    where not converged.
    """
    tsfc = ta
    # Solar-zenith angle, guarded so tan(sza) stays finite when the sun is at or
    # below the horizon (fdir is already 0 there, so the term contributes 0).
    cza_safe = cza if cza > CZA_MIN else 1.0
    sza = np.arccos(min(max(cza_safe, -1.0), 1.0))
    emis = _emis_atm(ta, rh)
    eair = rh * _esat(ta)

    tw_prev = _dew_point(eair)
    for _ in range(MAX_ITER):
        tref = 0.5 * (tw_prev + ta)
        h = _h_cylinder_in_air(tref, pair, speed)
        fatm = STEFANB * EMIS_WICK * (
            0.5 * (emis * ta**4 + EMIS_SFC * tsfc**4) - tw_prev**4
        ) + (1.0 - ALB_WICK) * solar * (
            (1.0 - fdir) * (1.0 + 0.25 * D_WICK / L_WICK)
            + fdir * ((np.tan(sza) / np.pi) + 0.25 * D_WICK / L_WICK)
            + ALB_SFC
        )
        ewick = _esat(tw_prev)
        density = pair * 100.0 / (R_AIR * tref)
        sc = _viscosity(tref) / (density * _diffusivity(tref, pair))
        tw_new = (
            ta
            - _evap(tref) / RATIO * (ewick - eair) / (pair - ewick) * (PR / sc) ** 0.56
            + (fatm / h) * rad
        )
        if abs(tw_new - tw_prev) < CONVERGENCE:
            return tw_new - 273.15
        tw_prev = 0.9 * tw_prev + 0.1 * tw_new
    return np.nan


@njit(cache=True)
def _wind_speed_2m(va, cossza, ssrd):
    """10 m -> 2 m wind speed via the Liljegren stability-dependent profile.

    ``va * (2/10)**p``, with the power-law exponent from a Pasquill-Gifford
    stability class (solar elevation, radiation, wind). Floored at MIN_SPEED.
    """
    daytime = cossza > 0.0
    if daytime:
        if ssrd >= 925.0:
            col = 0
        elif ssrd >= 675.0:
            col = 1
        elif ssrd >= 175.0:
            col = 2
        else:
            col = 3
        if va >= 6.0:
            row = 4
        elif va >= 5.0:
            row = 3
        elif va >= 3.0:
            row = 2
        elif va >= 2.0:
            row = 1
        else:
            row = 0
    else:
        col = 5
        if va >= 2.5:
            row = 2
        elif va >= 2.0:
            row = 1
        else:
            row = 0
    stability_class = LSRDT[row, col]
    exponent = URBAN_EXP[stability_class - 1]
    return max(va * (2.0 / 10.0) ** exponent, MIN_SPEED)


@njit(cache=True)
def _wbgt_scalar(t2m_K, rh_pct, sp_hPa, wind_ms, ssrd_Wm2, fdir_frac, cossza):
    """Sunlit Liljegren WBGT [degC] for one point; see wbgt_liljegren."""
    if not (t2m_K == t2m_K and rh_pct == rh_pct and sp_hPa == sp_hPa
            and wind_ms == wind_ms and ssrd_Wm2 == ssrd_Wm2
            and fdir_frac == fdir_frac and cossza == cossza):
        return np.nan  # NaN in -> NaN out without burning the iteration cap

    cza = min(max(cossza, 0.0), 1.0)  # night -> 0
    # Wind floor, then the KNMI 10 m floor, then scale to the 2 m sensor height.
    va = max(max(wind_ms, MIN_SPEED), MIN_WIND_10M)
    speed = _wind_speed_2m(va, cza, ssrd_Wm2)

    rh_frac = rh_pct / 100.0
    # KNMI direct-beam guards: clamp to [0, 0.9] and zero below the horizon.
    fdir = min(max(fdir_frac, 0.0), 0.9)
    if cza < CZA_MIN:
        fdir = 0.0

    tg_c = _solve_globe(t2m_K, rh_frac, sp_hPa, speed, ssrd_Wm2, fdir, cza)
    tnwb_c = _solve_wetbulb(t2m_K, rh_frac, sp_hPa, speed, ssrd_Wm2, fdir, cza, 1.0)
    return 0.1 * (t2m_K - ZERO_C) + 0.2 * tg_c + 0.7 * tnwb_c


@vectorize(
    ["float64(float64, float64, float64, float64, float64, float64, float64)"],
    nopython=True, cache=True,
)
def _wbgt_ufunc(t2m_K, rh_pct, sp_hPa, wind_ms, ssrd_Wm2, fdir_frac, cossza):
    return _wbgt_scalar(t2m_K, rh_pct, sp_hPa, wind_ms, ssrd_Wm2, fdir_frac, cossza)


def wbgt_liljegren(t2m_K, rh_pct, sp_hPa, wind_ms, ssrd_Wm2, fdir_frac, cossza):
    """Physical sunlit Liljegren WBGT [deg C] (numba port of thermofeel 2.2.0).

    WBGT = 0.7*Tnwb + 0.2*Tg + 0.1*Ta with globe & natural-wet-bulb solved from
    steady-state energy balance (Liljegren et al. 2008). fdir_frac is the
    direct-beam FRACTION (0-1); cossza is clipped to [0, 1] (night -> 0) and
    wind is floored at 0.13 m/s inside. Scalars or broadcastable arrays; usable
    via xr.apply_ufunc. Returns deg C (NaN where the iteration fails).
    """
    return _wbgt_ufunc(t2m_K, rh_pct, sp_hPa, wind_ms, ssrd_Wm2, fdir_frac, cossza)
