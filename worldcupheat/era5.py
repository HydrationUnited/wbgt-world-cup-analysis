"""ERA5 (RDA ds633.0) readers: analysis point extraction + forecast-flux de-accumulation.

Grid: 0.25 deg, latitude 90N -> 90S (721), longitude 0 .. 359.75 (1440), hourly, UTC.
Analysis files:  {root}/e5.oper.an.sfc/{YYYYMM}/e5.oper.an.sfc.{code}.ll025sc.{YYYYMM}*.nc
                 (exactly one file per variable per month).
Forecast files:  {root}/e5.oper.fc.sfc.accumu/{YYYYMM}/e5.oper.fc.sfc.accumu.{code}.ll025sc.*.nc
                 (usually two per month, VAR(forecast_initial_time, forecast_hour, lat, lon)).

RDA d633.0 forecast-accumu files store the PER-STEP hourly accumulation [J/m^2],
NOT cumulative-since-init (verified: raw values already trace the smooth solar
diurnal curve; differencing gives negative radiation). So hourly-mean flux is
simply value/3600 -- no ``.diff`` anywhere. Inits 06/18 UTC x steps 1..12 h tile
all 24 hours of the day; valid time = init + forecast_hour.
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd
import xarray as xr

# short name -> (ERA5 file code, variable name inside the netCDF file)
VARDEF = {
    "t2m":  ("128_167_2t", "VAR_2T"),
    "d2m":  ("128_168_2d", "VAR_2D"),
    "sp":   ("128_134_sp", "SP"),
    "u10":  ("128_165_10u", "VAR_10U"),
    "v10":  ("128_166_10v", "VAR_10V"),
    "ssrd": ("128_169_ssrd", "SSRD"),   # forecast
    "fdir": ("228_021_fdir", "FDIR"),   # forecast
}
ANALYSIS_VARS = ["t2m", "d2m", "sp", "u10", "v10"]


def to_era5_lon(lon):
    """ERA5 longitudes are 0..360. Map a possibly-negative longitude into [0, 360)."""
    return lon % 360.0


def months_in_scope(years, months) -> list[int]:
    """All YYYYMM ints for the cartesian product of ``years`` x ``months``, sorted."""
    return sorted(int(y) * 100 + int(m) for y in years for m in months)


def prev_month(yyyymm) -> int:
    """The YYYYMM immediately before ``yyyymm``."""
    y, m = divmod(int(yyyymm), 100)
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return y * 100 + m


def _analysis_file(root: str, var: str, yyyymm) -> str:
    """Path to the single monthly analysis file for a variable (fail loud)."""
    code, yyyymm = VARDEF[var][0], str(yyyymm)
    pat = os.path.join(root, "e5.oper.an.sfc", yyyymm,
                       f"e5.oper.an.sfc.{code}.ll025sc.{yyyymm}*.nc")
    hits = sorted(glob.glob(pat))
    if not hits:
        raise FileNotFoundError(f"No ERA5 analysis file for {var} {yyyymm}: {pat}")
    if len(hits) > 1:
        raise RuntimeError(f"Ambiguous ERA5 match ({len(hits)}) for {pat}: {hits}")
    return hits[0]


def _fc_files(root: str, var: str, yyyymm) -> list[str]:
    """Sorted forecast-accumulation files for a month (usually 2 spanning ~15 days each)."""
    code, yyyymm = VARDEF[var][0], str(yyyymm)
    pat = os.path.join(root, "e5.oper.fc.sfc.accumu", yyyymm,
                       f"e5.oper.fc.sfc.accumu.{code}.ll025sc.*.nc")
    hits = sorted(glob.glob(pat))
    if not hits:
        raise FileNotFoundError(f"No ERA5 fc file for {var} {yyyymm}: {pat}")
    return hits


def _cell_selectors(cells: pd.DataFrame) -> tuple[xr.DataArray, xr.DataArray]:
    """Vectorised nearest-neighbour selectors (dim 'cell') from a lat/lon cells frame."""
    lat = xr.DataArray(np.asarray(cells.lat.values, dtype=float), dims="cell")
    lon = xr.DataArray(to_era5_lon(np.asarray(cells.lon.values, dtype=float)), dims="cell")
    return lat, lon


def extract_analysis_month(root: str, yyyymm, cells: pd.DataFrame) -> xr.Dataset:
    """All ANALYSIS_VARS at the given cells for one month -> Dataset dims (time, cell).

    ``cells``: DataFrame with columns lat, lon and cell-id strings as index.
    Raw units (K, Pa, m/s). The grid latitude/longitude actually used come along
    from the nearest-neighbour ``.sel`` and are kept as coords on the cell dim.
    """
    lat_sel, lon_sel = _cell_selectors(cells)
    parts = []
    for var in ANALYSIS_VARS:
        path = _analysis_file(root, var, yyyymm)
        with xr.open_dataset(path) as ds:
            da = ds[VARDEF[var][1]].sel(latitude=lat_sel, longitude=lon_sel,
                                        method="nearest").load()
        parts.append(da.rename(var))
    out = xr.merge(parts, compat="override", join="exact")
    return out.assign_coords(cell=("cell", np.asarray(cells.index.values)))


def _extract_fc_file(path: str, ncvar: str, lat_sel: xr.DataArray,
                     lon_sel: xr.DataArray) -> xr.DataArray:
    """De-accumulate one forecast file at the cells -> DataArray (time, cell) [W/m^2].

    The HDF5 chunking is the WHOLE variable (~[1, 12, 721, 1440]), so any lazy
    pointwise read decompresses everything repeatedly: load the full array ONCE
    (~1.6 GB peak, acceptable) and select the cells in memory.
    """
    with xr.open_dataset(path) as ds:
        da = ds[ncvar].load()
    da = da.sel(latitude=lat_sel, longitude=lon_sel, method="nearest")

    init = np.asarray(da["forecast_initial_time"].values)
    fhr = np.asarray(da["forecast_hour"].values)
    if not np.issubdtype(fhr.dtype, np.timedelta64):     # may decode as int hours
        fhr = fhr.astype("timedelta64[h]")
    valid = (init[:, None] + fhr[None, :]).reshape(-1)   # C order, matches .stack below

    flux = (da / 3600.0).clip(min=0.0)                   # per-step J/m^2 -> W/m^2
    out = (flux.stack(step=("forecast_initial_time", "forecast_hour"))
               .reset_index("step", drop=True)
               .assign_coords(step=("step", valid))
               .rename(step="time"))
    return out.transpose("time", "cell").sortby("time")


def extract_flux_month(root: str, var: str, yyyymm, cells: pd.DataFrame,
                       include_prev_tail: bool = True) -> xr.DataArray:
    """Hourly-mean flux [W/m^2] at the cells for one month -> DataArray (time, cell).

    include_prev_tail: also load the previous month's fc files so the first hours
    of day 1 (00-06 UTC, produced by the prior 18Z init) are present; a missing
    tail month is skipped silently (the requested month itself must exist).
    """
    yyyymm = int(yyyymm)
    ncvar = VARDEF[var][1]
    lat_sel, lon_sel = _cell_selectors(cells)
    months = ([prev_month(yyyymm)] if include_prev_tail else []) + [yyyymm]
    parts = []
    for m in months:
        try:
            paths = _fc_files(root, var, m)
        except FileNotFoundError:
            if m == yyyymm:
                raise
            continue
        parts.extend(_extract_fc_file(p, ncvar, lat_sel, lon_sel) for p in paths)
    da = xr.concat(parts, dim="time").sortby("time")
    tt = pd.DatetimeIndex(da["time"].values)
    da = da.isel(time=~tt.duplicated(keep="first"))
    tt = pd.DatetimeIndex(da["time"].values)
    da = da.isel(time=(tt.year * 100 + tt.month) == yyyymm)
    return da.rename(var).assign_coords(cell=("cell", np.asarray(cells.index.values)))


def extract_month(root: str, yyyymm, cells: pd.DataFrame) -> xr.Dataset:
    """Analysis variables + de-accumulated ssrd/fdir on the analysis time axis.

    Radiation hours missing from the forecast files become 0.0 (night-safe).
    """
    ds = extract_analysis_month(root, yyyymm, cells)
    for var in ("ssrd", "fdir"):
        flux = extract_flux_month(root, var, yyyymm, cells)
        flux = flux.drop_vars(["latitude", "longitude"], errors="ignore")
        ds[var] = flux.reindex(time=ds.indexes["time"]).fillna(0.0)
    return ds
