#!/usr/bin/env python
"""Sunlit WBGT at every World Cup stadium from ERA5: edit CONFIG, then ``python run.py``.

Step 1 extracts ERA5 month by month at each stadium's grid cell and writes one
hourly-WBGT CSV per stadium (resumable: existing files are skipped). Step 2
turns those series into per-stadium percentiles and a nearest-hour WBGT for
every match. NOTE: each forecast-radiation file is loaded whole (~2 GB peak),
so run this on Casper / a compute node, not a login node.
"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from worldcupheat import era5, stats, wbgt

# ================================ CONFIG =====================================
ERA5_ROOT = "/glade/campaign/collections/gdex/data/d633000"
MATCHES_CSV = Path(__file__).parent / "data/cleaned/world_cup_matches_1950-2023.csv"
OUT_DIR = Path(__file__).parent / "output"
INTERMEDIATE_DIR = OUT_DIR / "stadium_wbgt"        # one hourly CSV per stadium
RESULTS_DIR = OUT_DIR / "results"
YEARS = range(1950, 2024)
# Tournament months (May-Jul + Nov-Dec); the union is applied to ALL years, and
# the stadium percentiles cover exactly this year x month scope.
MONTHS = (5, 6, 7, 11, 12)
# =============================================================================


def step1_stadium_series():
    """Extract ERA5 + compute hourly WBGT per stadium grid cell; write intermediate CSVs."""
    matches = stats.load_matches(MATCHES_CSV)
    stadiums = stats.unique_stadiums(matches)
    done = [k for k in stadiums.index if (INTERMEDIATE_DIR / f"{k}.csv").is_file()]
    if done:
        print(f"step1: skipping {len(done)} stadiums with existing series (resume)")
    todo = stadiums.drop(index=done)
    if todo.empty:
        print("step1: all stadium series already exist")
        return

    # ERA5 is a 0.25-deg grid; extract_month snaps each stadium to its nearest cell.
    cells = todo[["lat", "lon"]]
    print(f"step1: extracting {len(cells)} stadiums")

    def extract(yyyymm):                                    # I/O-bound: reads whole ERA5 files
        try:
            ds = era5.extract_month(ERA5_ROOT, yyyymm, cells)
        except FileNotFoundError as e:
            print(f"step1: {yyyymm} not in archive, skipping ({e})")
            return None
        print(f"step1: extracted {yyyymm}")
        return ds

    with ThreadPoolExecutor(max_workers=16) as pool:        # threads: work drops the GIL, no pickling
        monthly = [ds for ds in pool.map(extract, era5.months_in_scope(YEARS, MONTHS))
                   if ds is not None]
    if not monthly:
        raise RuntimeError("step1: no ERA5 months could be extracted")
    ds = xr.concat(monthly, dim="time").sortby("time")
    ds = ds.isel(time=~pd.DatetimeIndex(ds["time"].values).duplicated(keep="first"))
    times = pd.DatetimeIndex(ds["time"].values)

    for key, srow in todo.iterrows():
        sub = ds.sel(cell=key)
        glat = float(sub["latitude"].values)               # grid cell actually used
        glon = float(sub["longitude"].values)
        t2m, d2m, sp = sub["t2m"].values, sub["d2m"].values, sub["sp"].values
        ssrd, fdir = sub["ssrd"].values, sub["fdir"].values
        rh = wbgt.rh_from_t_td(wbgt.k2c(t2m), wbgt.k2c(d2m))
        wind = wbgt.wind_speed(sub["u10"].values, sub["v10"].values)
        with np.errstate(divide="ignore", invalid="ignore"):
            fdir_frac = np.clip(np.where(ssrd > 1.0, fdir / ssrd, 0.0), 0.0, 0.9)
        cza = wbgt.cos_solar_zenith(times, glat, glon)
        w = wbgt.wbgt_liljegren(t2m, rh, sp / 100.0, wind, ssrd, fdir_frac, cza)

        out = pd.DataFrame({"stadium": srow["stadium"], "city": srow["city"],
                            "time_utc": times, "wbgt_c": np.round(w, 2),
                            "grid_lat": glat, "grid_lon": glon})
        path = INTERMEDIATE_DIR / f"{key}.csv"
        out.to_csv(path, index=False, encoding="utf-8")
        print(f"step1: wrote {path}")


def step2_results():
    """Per-stadium percentiles + nearest-hour WBGT for every match."""
    pct_path = RESULTS_DIR / "stadium_percentiles.csv"
    stats.stadium_percentiles(INTERMEDIATE_DIR).to_csv(pct_path, index=False, encoding="utf-8")
    print(f"step2: wrote {pct_path}")

    matches = stats.nearest_hour_wbgt(stats.local_to_utc(stats.load_matches(MATCHES_CSV)),
                                      INTERMEDIATE_DIR)
    cols = ["gender", "country", "city", "stadium", "year", "date", "time_local",
            "lat", "lon", "timezone", "datetime_utc", "wbgt_c"]
    match_path = RESULTS_DIR / "match_wbgt.csv"
    matches[cols].to_csv(match_path, index=False, encoding="utf-8")
    print(f"step2: wrote {match_path}")


def main():
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    step1_stadium_series()
    step2_results()


if __name__ == "__main__":
    main()
