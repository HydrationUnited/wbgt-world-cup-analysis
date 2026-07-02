#!/usr/bin/env python
"""Pre-compute & SAVE per-game climatology-position flags at p75 / p90 / p95 / record (men's WC).

For each game, build the stadium x day-of-year (+-7d) 1960-1990 climatology over
the game-window local hours, then flag whether the game-window MEAN WBGT sits above the 75th / 90th /
95th percentile of that climatology (direct percentiles), and above its full-range record (max).
-> data/processed/pergame_anomaly_summary_men.csv   (feeds the anomaly-summary notebook & its 3 versions)
"""
import os
import numpy as np
import pandas as pd

ROOT = "/glade/derecho/scratch/gavinmad/heathack"
METRIC = "WBGT_lilj"
HIST = os.path.join(ROOT, "data/interim/hist")
CLIM, DOYW = list(range(1960, 1991)), 7
OUT = os.path.join(ROOT, "data/processed")
os.makedirs(OUT, exist_ok=True)

def build(pergame_csv, out_csv):
    pg = pd.read_csv(os.path.join(ROOT, "data/interim", pergame_csv))
    pg = pg[pg.matched == True].copy()
    pg["mdate"] = pd.to_datetime(pg.match_date); pg["doy"] = pg.mdate.dt.dayofyear
    pg["ko_h"] = pd.to_datetime(pg.time_local, format="%H:%M:%S", errors="coerce").dt.hour
    voff = {(int(r.year), r.hist_stadium): int(round(r.utc_off)) for r in pg.itertuples()}
    rows = []
    for yr in sorted(pg.year.unique()):
        files = [os.path.join(HIST, f"points_{yr}venues_{c}.parquet") for c in CLIM]
        files = [f for f in files if os.path.exists(f)]
        if not files:
            continue
        clim = pd.concat([pd.read_parquet(f, columns=["venue", "time_utc", METRIC]) for f in files], ignore_index=True)
        clim["time_utc"] = pd.to_datetime(clim.time_utc); clim["stad"] = clim.venue.str.split("|").str[1]
        clim["off"] = clim.stad.map(lambda s: voff.get((yr, s), 0))
        loc = clim.time_utc + pd.to_timedelta(clim.off, "h")
        clim["ldoy"] = loc.dt.dayofyear; clim["lhour"] = loc.dt.hour
        by_stad = {s: g for s, g in clim.groupby("stad")}
        for gm in pg[pg.year == yr].itertuples():
            c = by_stad.get(gm.hist_stadium)
            if c is None or np.isnan(gm.ko_h):
                continue
            H = [int((gm.ko_h - 1 + k) % 24) for k in range(5)]
            dd = (c.ldoy - gm.doy).abs(); dd = np.minimum(dd, 365 - dd)
            samp = c[(dd <= DOYW) & (c.lhour.isin(H))][METRIC].dropna().values
            if len(samp) < 30:
                continue
            p75, p90, p95, mx = np.percentile(samp, [75, 90, 95]).tolist() + [samp.max()]
            gval = gm.gw_wbgt_mean
            rows.append(dict(
                year=yr, match_date=gm.match_date, stadium=gm.stadium, city=gm.city, ok=True,
                gw_wbgt_mean=gval, gw_wbgt_max=gm.gw_wbgt_max, clim_mean=round(float(samp.mean()), 2),
                clim_p75=round(p75, 2), clim_p90=round(p90, 2), clim_p95=round(p95, 2), clim_max=round(float(mx), 2),
                above_p75=bool(gval > p75), above_p90=bool(gval > p90), above_p95=bool(gval > p95),
                above_record=bool(gm.gw_wbgt_max > mx)))
    df = pd.DataFrame(rows)
    df.to_csv(os.path.join(OUT, out_csv), index=False)
    print(f"wrote {out_csv}: {len(df)} games")
    for lv in ["above_p75", "above_p90", "above_p95", "above_record"]:
        print(f"  {lv}: {df[lv].sum()} ({100*df[lv].mean():.0f}%)")


build("pergame_wbgt_men.csv", "pergame_anomaly_summary_men.csv")
build("pergame_wbgt_women.csv", "pergame_anomaly_summary_women.csv")
