#!/usr/bin/env python
"""Per-game WBGT metrics for men's World Cup games (from the Finalized sheet + hourly hist WBGT).

For each game: game-window WBGT (kickoff-1h .. kickoff+match+1h) mean/min/max, and full local-day
WBGT mean/min/max. Foundation for the climatology-anomaly analysis.  -> data/interim/pergame_wbgt_men.csv
"""
import os
import re
import numpy as np
import pandas as pd

ROOT = "/glade/derecho/scratch/gavinmad/heathack"
METRIC = "WBGT_lilj"
HIST = os.path.join(ROOT, "data/interim/hist")
DUR = 2.0   # regulation+HT hours (extra time not separated here; game window = ko-1 .. ko+DUR+1)
GEN = {"estadio", "stadio", "stadium", "stade", "arena", "stadion", "de", "la", "el", "du", "of",
       "ii", "now", "co", "the"}


def offh(s):
    m = re.match(r"UTC([+-]\d+)", str(s))
    return int(m.group(1)) if m else np.nan


def toks(s):
    return set(re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split()) - GEN


def best(name, cands):
    mt = toks(name); b, bn = None, 0
    for c in cands:
        n = len(mt & toks(c))
        if n > bn:
            bn, b = n, c
    return b if bn >= 1 else None


sheet = pd.read_csv(os.path.join(ROOT, "data/interim/all_games_locations.csv"))
men = sheet[sheet.gender == "Men"].copy()
ven = pd.read_csv(os.path.join(ROOT, "data/raw/fifa/venues_all.csv"))
voff = {(int(r.year), str(r.stadium)): offh(r.utc_offset_during_cup) for r in ven.itertuples()}

rows = []
for yr in sorted(men.year.unique()):
    hf = os.path.join(HIST, f"points_{yr}venues_{yr}.parquet")
    if not os.path.exists(hf):
        print(f"{yr}: no hist"); continue
    h = pd.read_parquet(hf, columns=["venue", "time_utc", METRIC])
    h["time_utc"] = pd.to_datetime(h["time_utc"])
    h["stad"] = h.venue.str.split("|").str[1]
    hstads = list(h.stad.unique())
    series = {s: g.set_index("time_utc")[METRIC].sort_index() for s, g in h.groupby("stad")}
    vy = ven[ven.year == yr]
    g_yr = men[men.year == yr]
    for gm in g_yr.itertuples():
        # match sheet game to the hist venue by NEAREST coordinates (robust to naming)
        stad = None
        if len(vy):
            dd = (vy.lat - gm.lat) ** 2 + (vy.lon - gm.lon) ** 2
            cand = vy.loc[dd.idxmin(), "stadium"]
            if cand in series:
                stad = cand
        if stad is None:
            stad = best(gm.stadium, hstads)
        if stad is None or stad not in series:
            rows.append(dict(year=yr, stadium=gm.stadium, matched=False)); continue
        off = voff.get((yr, stad))
        if off is None or np.isnan(off):
            off = round(gm.lon / 15.0)
        s = series[stad]
        ko_local = pd.Timestamp(f"{gm.match_date} {gm.time_local}")
        ko_utc = ko_local - pd.Timedelta(hours=off)
        win = s.loc[ko_utc - pd.Timedelta(hours=1): ko_utc + pd.Timedelta(hours=DUR + 1)]
        loc = s.index + pd.Timedelta(hours=off)
        day = s[loc.strftime("%Y-%m-%d") == str(gm.match_date)]
        rows.append(dict(
            year=yr, gender="men", match_date=str(gm.match_date), time_local=gm.time_local,
            stadium=gm.stadium, hist_stadium=stad, city=gm.city, lat=gm.lat, lon=gm.lon, utc_off=off,
            matched=True, n_window=int(win.notna().sum()),
            gw_wbgt_mean=round(win.mean(), 2), gw_wbgt_min=round(win.min(), 2), gw_wbgt_max=round(win.max(), 2),
            day_wbgt_mean=round(day.mean(), 2), day_wbgt_min=round(day.min(), 2), day_wbgt_max=round(day.max(), 2)))

df = pd.DataFrame(rows)
OUT = os.path.join(ROOT, "data/interim/pergame_wbgt_men.csv")
df.to_csv(OUT, index=False)
ok = df[df.matched == True]
print(f"wrote {OUT}: {len(df)} games, matched {len(ok)}, with game-window WBGT {ok.gw_wbgt_max.notna().sum()}")
print(f"game-window max WBGT: {ok.gw_wbgt_max.min():.1f}..{ok.gw_wbgt_max.max():.1f}C; "
      f"day max: {ok.day_wbgt_max.min():.1f}..{ok.day_wbgt_max.max():.1f}C")
print("\nheat 'avoided' by kickoff timing (day_max - game_window_max), by decade:")
ok = ok.copy(); ok["decade"] = (ok.year // 10) * 10
print(ok.groupby("decade").apply(lambda d: pd.Series({
    "n": len(d), "gw_max": round(d.gw_wbgt_max.mean(), 1), "day_max": round(d.day_wbgt_max.mean(), 1),
    "avoided": round((d.day_wbgt_max - d.gw_wbgt_max).mean(), 1)}), include_groups=False).to_string())
