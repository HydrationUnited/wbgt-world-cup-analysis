#!/usr/bin/env python
"""Pre-compute & SAVE the data behind the diurnal case-study figure (so the notebook just loads+plots).

For 4 representative men's games, saves: the stadium x day-of-year (+-7d) 1960-1990 diurnal climatology
per local hour (mean/p75/p90/p95/min/max), the actual game-day hourly WBGT (in continuous plot-hour so
late windows stay contiguous past midnight), and the per-game summary metrics.
-> data/processed/case_study_diurnal_clim.csv / _actual.csv / _meta.csv
"""
import os
import numpy as np
import pandas as pd

ROOT = "/glade/derecho/scratch/gavinmad/heathack"
METRIC = "WBGT_lilj"
HIST = os.path.join(ROOT, "data/interim/hist")
CLIM, DOYW, DUR = list(range(1960, 1991)), 7, 2.0
OUT = os.path.join(ROOT, "data/processed")
os.makedirs(OUT, exist_ok=True)

CASES = [   # (gender, year, match_date, time_local, label)
    ("Men", 1994, "1994-06-19", "16:00:00", "Washington 1994 — USA'94 (hottest window)"),
    ("Men", 2022, "2022-11-26", "13:00:00", "Al Wakrah 2022 — TUN–AUS (hot afternoon)"),
    ("Men", 2018, "2018-06-30", "21:00:00", "Sochi 2018 — mild but record-breaking"),
    ("Men", 2006, "2006-06-23", "21:00:00", "Cologne 2006 — quiet baseline game"),
]

tbl = pd.read_csv(os.path.join(ROOT, "results/tables/Finalized_World_cup_Sheet_WBGT.csv"))
tbl["tstr"] = pd.to_datetime(tbl.time_local.astype(str)).dt.strftime("%H:%M:%S")
pg = pd.concat([pd.read_csv(os.path.join(ROOT, "data/interim/pergame_wbgt_men.csv")),
                pd.read_csv(os.path.join(ROOT, "data/interim/pergame_wbgt_women.csv"))], ignore_index=True)
pg = pg[pg.matched == True].copy()
pg["tstr"] = pd.to_datetime(pg.time_local.astype(str)).dt.strftime("%H:%M:%S")
pg["md"] = pd.to_datetime(pg.match_date).dt.strftime("%Y-%m-%d")
lu = {(r.gender, int(r.year), str(r.stadium), r.md, r.tstr): (r.hist_stadium, int(round(r.utc_off)))
      for r in pg.itertuples()}

clim_rows, act_rows, meta_rows = [], [], []
for ci, (gender, yr, md, tstr, label) in enumerate(CASES):
    row = tbl[(tbl.gender == gender) & (tbl.year == yr) & (tbl.match_date == md) & (tbl.tstr == tstr)].iloc[0]
    stad, off = lu[(gender.lower(), yr, str(row.stadium), md, tstr)]
    # per-local-hour climatology
    cfs = [os.path.join(HIST, f"points_{yr}venues_{c}.parquet") for c in CLIM]
    c = pd.concat([pd.read_parquet(f, columns=["venue", "time_utc", METRIC]) for f in cfs if os.path.exists(f)],
                  ignore_index=True)
    c["stad"] = c.venue.str.split("|").str[1]; c = c[c.stad == stad].copy()
    cl = pd.to_datetime(c.time_utc) + pd.Timedelta(hours=off)
    doy = int(pd.Timestamp(md).dayofyear)
    dd = (cl.dt.dayofyear - doy).abs(); dd = np.minimum(dd, 365 - dd)
    c = c[dd <= DOYW].copy(); c["lh"] = (pd.to_datetime(c.time_utc) + pd.Timedelta(hours=off)).dt.hour
    g = c.groupby("lh")[METRIC]
    cl_df = pd.DataFrame({"clim_mean": g.mean(), "clim_p75": g.quantile(.75), "clim_p90": g.quantile(.90),
                          "clim_p95": g.quantile(.95), "clim_min": g.min(), "clim_max": g.max()}).reindex(range(24))
    ko_h = int(pd.Timestamp(tstr).hour); lo, hi = ko_h - 1, ko_h + int(DUR + 1)
    maxph = max(23, hi)
    for ph in range(maxph + 1):
        r = cl_df.iloc[ph % 24]
        clim_rows.append(dict(case=ci, label=label, ph=ph, **{k: round(float(r[k]), 3) for k in cl_df.columns}))
    # actual game-day series in continuous plot-hour
    a = pd.read_parquet(os.path.join(HIST, f"points_{yr}venues_{yr}.parquet"),
                        columns=["venue", "time_utc", METRIC])
    a["stad"] = a.venue.str.split("|").str[1]; a = a[a.stad == stad].copy()
    a["tutc"] = pd.to_datetime(a.time_utc); aloc = a.tutc + pd.Timedelta(hours=off)
    a["lh"] = aloc.dt.hour; a["dayoff"] = (aloc.dt.normalize() - pd.Timestamp(md)).dt.days
    a["ph"] = a.lh + 24 * a.dayoff
    aplot = a[(a.dayoff == 0) | ((a.dayoff == 1) & (a.ph <= hi))].sort_values("ph")
    for r in aplot.itertuples():
        act_rows.append(dict(case=ci, label=label, ph=int(r.ph), wbgt_actual=round(float(getattr(r, METRIC)), 3)))
    meta_rows.append(dict(
        case=ci, label=label, gender=gender, year=yr, city=row.city, stadium=row.stadium,
        match_date=md, time_local=tstr, ko_h=ko_h, win_lo=lo, win_hi=hi, maxph=maxph, utc_off=off,
        game_mean=row.game_wbgt_mean_C, game_min=row.game_wbgt_min_C, game_max=row.game_wbgt_max_C,
        day_mean=row.day_wbgt_mean_C, day_min=row.day_wbgt_min_C, day_max=row.day_wbgt_max_C,
        hrs_ge26=int(row.game_hrs_ge26_FIFPRO_breaks), hrs_ge28=int(row.game_hrs_ge28_FIFPRO_postpone),
        hrs_ge32=int(row.game_hrs_ge32_FIFA), hrs_p75=int(row.game_hrs_over_p75_clim),
        hrs_p90=int(row.game_hrs_over_p90_clim), hrs_p95=int(row.game_hrs_over_p95_clim),
        hrs_max=int(row.game_hrs_over_max_clim)))
    print(f"case {ci}: {label}  stad={stad} off={off} maxph={maxph}")

pd.DataFrame(clim_rows).to_csv(os.path.join(OUT, "case_study_diurnal_clim.csv"), index=False)
pd.DataFrame(act_rows).to_csv(os.path.join(OUT, "case_study_diurnal_actual.csv"), index=False)
pd.DataFrame(meta_rows).to_csv(os.path.join(OUT, "case_study_diurnal_meta.csv"), index=False)
print("wrote data/processed/case_study_diurnal_{clim,actual,meta}.csv")
