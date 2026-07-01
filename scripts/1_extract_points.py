#!/usr/bin/env python
"""Step 1: extract ERA5 at venue points and compute all heat-metric variants.

Opens each monthly ERA5 file ONCE and pulls all venue points. Analysis (t2m,d2m,sp,u10,v10)
+ forecast radiation (ssrd,fdir de-accumulated, full-read-once per file). Computes
WBGT_liljegren (primary), WBGT_shade, sWBGT, Tw_stull. Writes a long parquet.

Two modes:
  A) explicit:  --venues CSV --venue-years 2018,2022 --months 201806,201807 --out FILE
  B) per-year (for PBS array over historical years — climatology + trend):
       --year 1975 --out-dir data/interim/hist
     -> for each in-scope tournament, extract ITS venues for ITS months in that year,
        write <out-dir>/points_<year>.parquet
"""
import argparse
import os
import sys
import time
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from heathack import config, era5, era5_fc, thermo  # noqa: E402


def compute_metrics(an, ssrd, fdir, coords, t0):
    """Build a long DataFrame of metrics for the given venues from extracted fields."""
    rows = []
    for name, (lat, lon) in coords.items():
        d = pd.DataFrame({
            "t2m": an["t2m"][name], "d2m": an["d2m"][name], "sp": an["sp"][name],
            "u10": an["u10"][name], "v10": an["v10"][name],
        }).dropna()
        if d.empty:
            continue
        d["T_C"] = thermo.k2c(d.t2m)
        d["Td_C"] = thermo.k2c(d.d2m)
        d["RH"] = thermo.rh_from_t_td(d.T_C, d.Td_C)
        d["wind"] = thermo.wind_speed(d.u10, d.v10)
        d["Tw_stull"] = thermo.wet_bulb_stull(d.T_C, d.RH)
        d["WBGT_shade"] = thermo.wbgt_indoor_from_tw(d.Tw_stull, d.T_C)
        d["sWBGT"] = thermo.wbgt_shade_bom(d.T_C, thermo.vapor_pressure_hpa(d.Td_C))
        if ssrd is not None:
            s = ssrd[name].reindex(d.index)
            f = fdir[name].reindex(d.index)
            d["ssrd"] = s
            d["fdir_frac"] = (f / s.where(s > 1.0)).fillna(0.0).clip(0, 0.9)
            d["cossza"] = thermo.cos_solar_zenith(d.index, lat, lon)
            valid = d[["ssrd", "fdir_frac", "cossza"]].notna().all(axis=1)
            d["WBGT_lilj"] = np.nan
            if valid.any():
                dv = d[valid]
                d.loc[valid, "WBGT_lilj"] = thermo.wbgt_liljegren(
                    dv.t2m.values, dv.RH.values, (dv.sp / 100).values, dv.wind.values,
                    dv.ssrd.values, dv.fdir_frac.values, dv.cossza.values)
        d = d.reset_index()
        d.insert(0, "venue", name)
        rows.append(d)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def run_extract(vdf, months, out, radiation=True, t0=None):
    t0 = t0 or time.time()
    points = [(f"{r.year}|{r.stadium}", float(r.lat), float(r.lon)) for r in vdf.itertuples()]
    coords = {f"{r.year}|{r.stadium}": (float(r.lat), float(r.lon)) for r in vdf.itertuples()}
    print(f"[{time.time()-t0:.0f}s] {len(points)} venues x {len(months)} months -> {out}", flush=True)
    an = {}
    for v in ["t2m", "d2m", "sp", "u10", "v10"]:
        an[v] = era5.extract_points_range(v, months, points)
        print(f"[{time.time()-t0:.0f}s]   analysis {v} {an[v].shape}", flush=True)
    ssrd = fdir = None
    if radiation:
        ssrd = era5_fc.extract_flux_points("ssrd", months, points)
        fdir = era5_fc.extract_flux_points("fdir", months, points)
        print(f"[{time.time()-t0:.0f}s]   radiation ssrd{ssrd.shape} fdir{fdir.shape}", flush=True)
    out_df = compute_metrics(an, ssrd, fdir, coords, t0)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    out_df.to_parquet(out, index=False)
    print(f"[{time.time()-t0:.0f}s] wrote {len(out_df)} rows "
          f"({out_df.venue.nunique() if len(out_df) else 0} venues) -> {out}", flush=True)
    return out_df


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--venues", default=os.path.join(ROOT, "data/raw/fifa/venues_all.csv"))
    p.add_argument("--venue-years", default="")
    p.add_argument("--months", default="")
    p.add_argument("--out", default="")
    p.add_argument("--year", type=int, default=0, help="per-year mode (climatology/trend)")
    p.add_argument("--out-dir", default="")
    p.add_argument("--only-tournament", type=int, default=0,
                   help="in per-year mode, restrict to this tournament year's venues")
    p.add_argument("--no-radiation", action="store_true")
    a = p.parse_args()
    t0 = time.time()
    vdf_all = pd.read_csv(a.venues)
    rad = not a.no_radiation

    if a.year:                                    # Mode B: per-year, all in-scope tournaments
        cfg = config.load()
        tours = [t for t in cfg["world_cups"]["tournaments"] if t.get("in_scope")
                 and (not a.only_tournament or t["year"] == a.only_tournament)]
        # gather all venue points + each tournament's months (union across tournaments)
        points, coords, tour_of, tour_months = [], {}, {}, {}
        seen = set()
        for t in tours:
            tmonths = [a.year * 100 + m for m in t["months"]]
            tour_months[t["year"]] = set(tmonths)
            for r in vdf_all[vdf_all.year == t["year"]].itertuples():
                name = f"{t['year']}|{r.stadium}"
                if name in seen:
                    continue
                seen.add(name)
                points.append((name, float(r.lat), float(r.lon)))
                coords[name] = (float(r.lat), float(r.lon))
                tour_of[name] = t["year"]
        union_months = sorted({m for ms in tour_months.values() for m in ms})
        print(f"[{time.time()-t0:.0f}s] YEAR {a.year}: {len(points)} venues, "
              f"months {union_months} (read each ONCE)", flush=True)
        # extract each month ONCE for all venues, then compute metrics
        an = {}
        for v in ["t2m", "d2m", "sp", "u10", "v10"]:
            an[v] = era5.extract_points_range(v, union_months, points)
            print(f"[{time.time()-t0:.0f}s]   analysis {v} {an[v].shape}", flush=True)
        ssrd = fdir = None
        if rad:
            ssrd = era5_fc.extract_flux_points("ssrd", union_months, points)
            fdir = era5_fc.extract_flux_points("fdir", union_months, points)
            print(f"[{time.time()-t0:.0f}s]   radiation done", flush=True)
        full = compute_metrics(an, ssrd, fdir, coords, t0)
        full["ym"] = pd.to_datetime(full.time_utc).dt.year * 100 + pd.to_datetime(full.time_utc).dt.month
        # split per tournament (filter each to ITS months) and write
        os.makedirs(a.out_dir, exist_ok=True)
        for ty, months in tour_months.items():
            vnames = [n for n in tour_of if tour_of[n] == ty]
            sub = full[full.venue.isin(vnames) & full.ym.isin(months)].drop(columns=["ym"])
            out = os.path.join(a.out_dir, f"points_{ty}venues_{a.year}.parquet")
            sub.to_parquet(out, index=False)
        print(f"[{time.time()-t0:.0f}s] YEAR {a.year} DONE ({len(full)} rows, "
              f"{len(tour_months)} tournaments)", flush=True)
    else:                                         # Mode A: explicit
        if a.venue_years:
            yrs = [int(x) for x in a.venue_years.split(",")]
            vdf_all = vdf_all[vdf_all.year.isin(yrs)]
        months = [int(x) for x in a.months.split(",")]
        run_extract(vdf_all, months, a.out, rad, t0)


if __name__ == "__main__":
    main()
