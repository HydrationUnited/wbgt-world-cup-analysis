#!/usr/bin/env python
"""Per-game WBGT metrics + climatology anomaly for WOMEN's WC games (mirrors the men's per-game scripts).

Women's hist venues came from the same sheet, so game stadium == hist stadium (exact match). Offsets
via timezonefinder (DST-aware) with a lon-based fallback. Outputs pergame_wbgt_women.csv and
pergame_anomaly_women.csv in the same schema as the men's files.
"""
import os
import numpy as np
import pandas as pd

ROOT = "/glade/derecho/scratch/gavinmad/heathack"
METRIC = "WBGT_lilj"
HIST = os.path.join(ROOT, "data/interim/hist")
DUR, CLIM, DOYW = 2.0, list(range(1960, 1991)), 7
try:
    from timezonefinder import TimezoneFinder
    import pytz
    TF = TimezoneFinder()
    HAVE_TZ = True
except Exception:
    HAVE_TZ = False


def offset(lat, lon, date):
    if HAVE_TZ:
        try:
            tz = pytz.timezone(TF.timezone_at(lat=lat, lng=lon))
            return tz.utcoffset(pd.Timestamp(date).to_pydatetime()).total_seconds() / 3600.0
        except Exception:
            pass
    return round(lon / 15.0)


sheet = pd.read_csv(os.path.join(ROOT, "data/interim/all_games_locations.csv"))
w = sheet[sheet.gender == "Women"].copy()
w["mdate"] = pd.to_datetime(w.match_date)

rows = []
for yr in sorted(w.year.unique()):
    hf = os.path.join(HIST, f"points_{yr}venues_{yr}.parquet")
    cfs = [os.path.join(HIST, f"points_{yr}venues_{c}.parquet") for c in CLIM]
    cfs = [f for f in cfs if os.path.exists(f)]
    if not (os.path.exists(hf) and cfs):
        print(f"{yr}: missing hist/clim ({os.path.exists(hf)}, {len(cfs)})"); continue
    act = pd.read_parquet(hf, columns=["venue", "time_utc", METRIC])
    act["time_utc"] = pd.to_datetime(act.time_utc); act["stad"] = act.venue.str.split("|").str[1]
    clim = pd.concat([pd.read_parquet(f, columns=["venue", "time_utc", METRIC]) for f in cfs], ignore_index=True)
    clim["time_utc"] = pd.to_datetime(clim.time_utc); clim["stad"] = clim.venue.str.split("|").str[1]
    aser = {s: g.set_index("time_utc")[METRIC].sort_index() for s, g in act.groupby("stad")}
    cby = {s: g for s, g in clim.groupby("stad")}
    for gm in w[w.year == yr].itertuples():
        s = aser.get(gm.stadium)
        if s is None:
            rows.append(dict(year=yr, stadium=gm.stadium, matched=False, ok=False)); continue
        off = offset(gm.lat, gm.lon, gm.mdate)
        ko_local = pd.Timestamp(f"{gm.match_date} {gm.time_local}")
        ko_utc = ko_local - pd.Timedelta(hours=off)
        win = s.loc[ko_utc - pd.Timedelta(hours=1): ko_utc + pd.Timedelta(hours=DUR + 1)]
        lo = s.index + pd.Timedelta(hours=off)
        day = s[lo.strftime("%Y-%m-%d") == str(gm.match_date)]
        gw_mean, gw_max = win.mean(), win.max()
        # climatology at the window local hours, DOY +-7
        c = cby.get(gm.stadium)
        cl = c.time_utc + pd.Timedelta(hours=off)
        doy = int(pd.Timestamp(gm.match_date).dayofyear)
        ko_h = int(pd.Timestamp(gm.time_local).hour)
        H = [int((ko_h - 1 + k) % 24) for k in range(5)]
        dd = (cl.dt.dayofyear - doy).abs(); dd = np.minimum(dd, 365 - dd)
        samp = c[(dd <= DOYW) & (cl.dt.hour.isin(H))][METRIC].dropna().values
        ok = len(samp) >= 30
        cm = float(samp.mean()) if ok else np.nan
        p975 = float(np.percentile(samp, 97.5)) if ok else np.nan
        rows.append(dict(
            year=yr, gender="women", match_date=str(gm.match_date), time_local=gm.time_local,
            stadium=gm.stadium, hist_stadium=gm.stadium, city=gm.city, lat=gm.lat, lon=gm.lon,
            utc_off=round(off, 1), matched=True, ok=ok, doy=doy, ko_h=ko_h,
            gw_wbgt_mean=round(gw_mean, 2), gw_wbgt_min=round(win.min(), 2), gw_wbgt_max=round(gw_max, 2),
            day_wbgt_mean=round(day.mean(), 2), day_wbgt_min=round(day.min(), 2), day_wbgt_max=round(day.max(), 2),
            clim_mean=round(cm, 2) if ok else np.nan, clim_p975=round(p975, 2) if ok else np.nan,
            anomaly=round(gw_mean - cm, 2) if ok else np.nan,
            percentile=round((samp < gw_mean).mean() * 100, 1) if ok else np.nan,
            above_95=bool(gw_mean > p975) if ok else False,
            above_record=bool(gw_max > samp.max()) if len(samp) else False))

df = pd.DataFrame(rows)
df[df.matched == True].to_csv(os.path.join(ROOT, "data/interim/pergame_wbgt_women.csv"), index=False)
df[df.ok == True].to_csv(os.path.join(ROOT, "data/interim/pergame_anomaly_women.csv"), index=False)
o = df[df.ok == True]
print(f"women: {len(df)} games, matched {int(df.matched.sum())}, anomaly-ok {len(o)} (tz={HAVE_TZ})")
if len(o):
    print(f"anomaly mean {o.anomaly.mean():+.2f}C; above 95% band {o.above_95.sum()} ({100*o.above_95.mean():.0f}%)")
    o = o.copy(); o["decade"] = (o.year // 10) * 10
    print(o.groupby("year").agg(n=("anomaly", "size"), anomaly=("anomaly", "mean"),
          gw_max=("gw_wbgt_max", "mean")).round(2).to_string())
