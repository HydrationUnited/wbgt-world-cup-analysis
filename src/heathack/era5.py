"""Point extraction from ERA5 surface-analysis monthly netCDF files.

ERA5 grid: 0.25 deg, latitude 90N->90S (721), longitude 0..359.75 (1440), hourly, UTC.
Variable inside file is uppercase (VAR_2T, VAR_2D, SP, MSL).

Design goal: open each monthly file ONCE and pull all requested venue points
(vectorised nearest-neighbour). Returns tz-aware-UTC-indexed pandas frames.
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
import pandas as pd
import xarray as xr

from . import config


@dataclass
class GridPoint:
    name: str
    req_lat: float
    req_lon: float          # as given (may be negative)
    grid_lat: float         # nearest ERA5 cell centre actually used
    grid_lon: float         # 0..360
    dist_km: float          # great-circle distance request -> grid centre


def _haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(((lon2 - lon1 + 180) % 360) - 180)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def open_month(var_key: str, yyyymm) -> xr.DataArray:
    """Open one monthly ERA5 file, return the DataArray (dims: time, latitude, longitude).

    No dask chunking: we read single grid columns via scalar isel, which the netCDF4
    backend does with an efficient strided read (much faster than loading the array).
    """
    path = config.era5_sfc_file(var_key, yyyymm)
    ds = xr.open_dataset(path)
    return ds[config.ncvar(var_key)]


def resolve_points(var_key: str, yyyymm, points: list[tuple[str, float, float]]) -> list[GridPoint]:
    """Resolve requested (name,lat,lon) to the nearest ERA5 grid cell (metadata only)."""
    da = open_month(var_key, yyyymm)
    lats = da["latitude"].values
    lons = da["longitude"].values      # 0..360
    out = []
    for name, lat, lon in points:
        elon = config.to_era5_lon(lon)
        gi = int(np.abs(lats - lat).argmin())
        gj = int(np.abs(lons - elon).argmin())
        glat, glon = float(lats[gi]), float(lons[gj])
        out.append(GridPoint(name, lat, lon, glat, glon,
                             _haversine_km(lat, elon, glat, glon)))
    da.close()
    return out


def extract_points_month(var_key: str, yyyymm,
                         points: list[tuple[str, float, float]]) -> pd.DataFrame:
    """Extract all venue points from ONE monthly file.

    Returns a DataFrame indexed by UTC time, columns = point names, raw units
    (K for 2t/2d, Pa for sp/msl). Uses xarray vectorised nearest selection.
    """
    from netCDF4 import Dataset
    path = config.era5_sfc_file(var_key, yyyymm)
    ds = Dataset(path)
    v = ds.variables[config.ncvar(var_key)]         # (time, lat, lon)
    lats = ds.variables["latitude"][:]
    lons = ds.variables["longitude"][:]             # 0..360
    base = np.datetime64("1900-01-01T00:00:00")
    tindex = pd.DatetimeIndex(base + np.asarray(ds.variables["time"][:], "timedelta64[h]"))
    idx = [(name, int(np.abs(lats - lat).argmin()),
            int(np.abs(lons - config.to_era5_lon(lon)).argmin())) for name, lat, lon in points]
    cols = {}
    if len(points) > 24:
        # many points: read the full array ONCE (~60s) and index in memory (scales flat).
        full = v[:]
        for name, li, lj in idx:
            cols[name] = np.asarray(full[:, li, lj], dtype=float)
        del full
    else:
        # few points: strided per-column reads are cheaper than a full decompress.
        for name, li, lj in idx:
            cols[name] = np.asarray(v[:, li, lj], dtype=float)
    ds.close()
    df = pd.DataFrame(cols, index=tindex)
    df.index.name = "time_utc"
    return df


def extract_points_range(var_key: str, months: list,
                         points: list[tuple[str, float, float]]) -> pd.DataFrame:
    """Extract venue points across several months; concatenate in time order."""
    frames = [extract_points_month(var_key, m, points) for m in months]
    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    return out


def months_between(start_yyyymm: int, end_yyyymm: int) -> list[int]:
    """Inclusive list of YYYYMM between two YYYYMM ints."""
    y0, m0 = divmod(start_yyyymm, 100)
    y1, m1 = divmod(end_yyyymm, 100)
    out = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.append(y * 100 + m)
        m += 1
        if m == 13:
            m = 1
            y += 1
    return out
