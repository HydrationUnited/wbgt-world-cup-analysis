#!/usr/bin/env python
"""One PBS-array subjob: extract ERA5 WBGT for one (women's tournament, year) at its months.

Writes data/interim/hist/points_<tournament>venues_<year>.parquet (venue = '<tournament>|<stadium>'),
matching the men's hist layout so the per-game scripts work for women unchanged. Idempotent (skips if exists).
"""
import os
import sys
import argparse
import numpy as np
import pandas as pd

ROOT = "/glade/derecho/scratch/gavinmad/heathack"
sys.path.insert(0, os.path.join(ROOT, "src"))
from heathack import era5, era5_fc, thermo  # noqa: E402
HIST = os.path.join(ROOT, "data/interim/hist")


def compute_metrics(an, ssrd, fdir, coords):
    rows = []
    for name, (lat, lon) in coords.items():
        d = pd.DataFrame({"t2m": an["t2m"][name], "d2m": an["d2m"][name], "sp": an["sp"][name],
                          "u10": an["u10"][name], "v10": an["v10"][name]}).dropna()
        if d.empty:
            continue
        d["T_C"] = thermo.k2c(d.t2m); d["RH"] = thermo.rh_from_t_td(d.T_C, thermo.k2c(d.d2m))
        d["wind"] = thermo.wind_speed(d.u10, d.v10)
        d["ssrd"] = ssrd[name].reindex(d.index)
        d["fdir_frac"] = (fdir[name].reindex(d.index) / d.ssrd.where(d.ssrd > 1.0)).fillna(0.0).clip(0, 0.9)
        d["cossza"] = thermo.cos_solar_zenith(d.index, lat, lon)
        valid = d[["ssrd", "cossza"]].notna().all(axis=1)
        d["WBGT_lilj"] = np.nan
        if valid.any():
            dv = d[valid]
            d.loc[valid, "WBGT_lilj"] = thermo.wbgt_liljegren(
                dv.t2m.values, dv.RH.values, (dv.sp / 100).values, dv.wind.values,
                dv.ssrd.values, dv.fdir_frac.values, dv.cossza.values)
        d = d.reset_index(); d.insert(0, "venue", name)
        rows.append(d[["venue", "time_utc", "WBGT_lilj"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--index", type=int, default=int(os.environ.get("PBS_ARRAY_INDEX", "1")))
    a = ap.parse_args()
    jobs = pd.read_csv(os.path.join(ROOT, "data/interim/women_jobs.csv"))
    j = jobs.iloc[a.index - 1]
    T, Y = int(j.tournament), int(j.extract_year)
    out = os.path.join(HIST, f"points_{T}venues_{Y}.parquet")
    if os.path.exists(out):
        print(f"T{T} Y{Y}: exists", flush=True); return
    ven = pd.read_csv(os.path.join(ROOT, "data/interim/women_venues.csv"))
    ven = ven[ven.year == T]
    coords = {f"{T}|{r.stadium}": (float(r.lat), float(r.lon)) for r in ven.itertuples()}
    points = [(k, v[0], v[1]) for k, v in coords.items()]
    months = [Y * 100 + int(m) for m in str(j.months).split("|")]
    print(f"T{T} Y{Y}: {len(points)} venues, months {months}", flush=True)
    an = {v: era5.extract_points_range(v, months, points) for v in ["t2m", "d2m", "sp", "u10", "v10"]}
    ssrd = era5_fc.extract_flux_points("ssrd", months, points)
    fdir = era5_fc.extract_flux_points("fdir", months, points)
    df = compute_metrics(an, ssrd, fdir, coords)
    os.makedirs(HIST, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"T{T} Y{Y}: wrote {out} ({len(df)} rows)", flush=True)


if __name__ == "__main__":
    main()
