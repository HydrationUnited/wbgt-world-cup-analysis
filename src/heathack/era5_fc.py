"""ERA5 FORECAST accumulated-radiation extraction (ssrd, fdir) with de-accumulation.

Forecast files: VAR(forecast_initial_time, forecast_hour, lat, lon), accumulated J/m^2.
Inits twice daily (06/18 UTC), steps 1..12h → valid times tile all 24 h/day (no overlap).
De-accumulate to hourly-mean flux [W/m^2]:  flux[fhr] = (accum[fhr]-accum[fhr-1])/3600,
flux[1]=accum[1]/3600. Valid time = init + fhr.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import xarray as xr

from . import config


def _extract_file(path: str, ncvar: str,
                  points: list[tuple[str, float, float]]) -> pd.DataFrame:
    """De-accumulate one forecast file at venue points → DataFrame(index=valid_time UTC, cols=names)."""
    from netCDF4 import Dataset
    # Chunking is [1, 12, 721, 1440] -> ANY read decompresses the whole variable (~20s).
    # So read the full array ONCE (via netCDF4, fast) and index all venue points in memory.
    ds = Dataset(path)
    v = ds.variables[ncvar]
    lats = ds.variables["latitude"][:]
    lons = ds.variables["longitude"][:]
    init = pd.to_datetime(_hours_since_1900(ds.variables["forecast_initial_time"][:]))
    fhr = np.asarray(ds.variables["forecast_hour"][:], dtype="timedelta64[h]")
    vt = (init.values[:, None] + fhr[None, :]).reshape(-1)
    accum_full = v[:]                                 # (n_init, n_fhr, lat, lon) — single decompress
    cols = {}
    for name, lat, lon in points:
        elon = config.to_era5_lon(lon)
        li = int(np.abs(lats - lat).argmin())
        lj = int(np.abs(lons - elon).argmin())
        # RDA d633.0 forecast-accumu stores the PER-STEP (hourly) accumulation already,
        # NOT cumulative-since-init. So the hour-ending-at valid_time flux is value/3600.
        # (Verified: raw values form the smooth solar diurnal curve; differencing gives
        #  negative radiation.)
        hourly = np.asarray(accum_full[:, :, li, lj], dtype=float) / 3600.0   # (n_init, n_fhr) W/m^2
        cols[name] = np.clip(hourly.reshape(-1), 0.0, None)
    ds.close()
    df = pd.DataFrame(cols, index=pd.DatetimeIndex(vt))
    df.index.name = "time_utc"
    return df.sort_index()


def _hours_since_1900(vals):
    """Decode 'hours since 1900-01-01' integers to datetime64[ns]."""
    base = np.datetime64("1900-01-01T00:00:00")
    return base + np.asarray(vals, dtype="timedelta64[h]")


def extract_flux_points(var_key: str, months: list,
                        points: list[tuple[str, float, float]],
                        include_prev_month_tail: bool = True) -> pd.DataFrame:
    """Hourly-mean flux [W/m^2] at venue points across months (valid-time UTC index).

    include_prev_month_tail: also load the previous month's fc files so the first
    hours (00-06 UTC of day 1, produced by the prior day's 18Z init) are present.
    """
    months = list(months)
    load_months = list(months)
    if include_prev_month_tail:
        for m in months:
            load_months.append(config_prev_month(m))
    load_months = sorted(set(load_months))
    ncv = config.ncvar(var_key)
    frames = []
    for m in load_months:
        try:
            for path in config.era5_fc_files(var_key, m):
                frames.append(_extract_file(path, ncv, points))
        except FileNotFoundError:
            continue
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    # keep only valid times whose month is in the requested set
    mask = out.index.to_series().dt.strftime("%Y%m").astype(int).isin([int(m) for m in months])
    return out[mask.values]


def config_prev_month(yyyymm) -> int:
    y, m = divmod(int(yyyymm), 100)
    m -= 1
    if m == 0:
        m = 12
        y -= 1
    return y * 100 + m


def direct_fraction(ssrd_flux: pd.DataFrame, fdir_flux: pd.DataFrame) -> pd.DataFrame:
    """Direct-beam fraction (0-1) = fdir/ssrd, aligned; 0 where ssrd≈0. For thermofeel Liljegren."""
    s = ssrd_flux.reindex_like(fdir_flux)
    frac = fdir_flux / s.where(s > 1.0)               # avoid div by ~0 at night
    return frac.fillna(0.0).clip(0.0, 0.9)
