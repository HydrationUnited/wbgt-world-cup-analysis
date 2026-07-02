#!/usr/bin/env python
"""Goals / yellow cards / fouls vs % of game-window hours over the local diurnal-climatology levels.

For each match (StatsBomb complete tournaments: men 2018/2022 + women 2019/2023) compute the % of
game-window hours (kickoff-1h..kickoff+3h) whose WBGT_lilj exceeds the stadium x day-of-year (+-7d)
1960-1990 climatology at p75 / p90 / p95 / record(max), per LOCAL HOUR (identical definition to the
appended sheet columns).  Then scatter each outcome vs each %-level, FIT WITHIN GENDER (pooling men+
women manufactures a Simpson's-paradox correlation), and report the naive-pooled r as a caveat.
-> figures/08_discipline/{goals,yellow,fouls}_vs_climpct.png  + data/interim/outcomes_vs_climpct.csv
"""
import os
import re
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "/glade/derecho/scratch/gavinmad/heathack"
METRIC = "WBGT_lilj"
HIST = os.path.join(ROOT, "data/interim/hist")
CLIM, DOYW, DUR = list(range(1960, 1991)), 7, 2.0
GEN = {"estadio", "stadio", "stadium", "stade", "arena", "stadion", "de", "la", "el", "du", "of",
       "ii", "now", "co", "the", "riviera", "regional"}
ALIAS = {"Allianz Riviera": "Stade de Nice", "Wellington Regional Stadium": "Sky Stadium"}
MATCH_VENUE = {22936: "Stade de Nice"}
TOURN = [("men", 2018), ("men", 2022), ("women", 2019), ("women", 2023)]
LEVELS = [("p75", 75), ("p90", 90), ("p95", 95), ("p98", 98), ("p99", 99), ("max", None)]  # None -> record
SCATTER_LEVELS = [("p75", 75), ("p90", 90), ("p95", 95), ("max", None)]   # the 4 shown in the scatter grids


def offh(s):
    m = re.match(r"UTC([+-]\d+)", str(s)); return int(m.group(1)) if m else np.nan


def toks(s):
    return set(re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split()) - GEN


def best(name, cands):
    mt = toks(name); b, bn = None, 0
    for c in cands:
        n = len(mt & toks(c))
        if n > bn:
            bn, b = n, c
    return b if bn >= 1 else None


ven = pd.read_csv(os.path.join(ROOT, "data/raw/fifa/venues_all.csv"))
voff = {(int(r.year), str(r.stadium)): offh(r.utc_offset_during_cup) for r in ven.itertuples()}
vlon = {(int(r.year), str(r.stadium)): float(r.lon) for r in ven.itertuples()}
wv = pd.read_csv(os.path.join(ROOT, "data/interim/women_venues.csv"))
wlon = {(int(r.year), str(r.stadium)): float(r.lon) for r in wv.itertuples()}
sb = pd.read_csv(os.path.join(ROOT, "data/interim/statsbomb_wc_discipline.csv"))

rows = []
for gender, yr in TOURN:
    g = sb[(sb.gender == gender) & (sb.year == yr)].copy()
    act = pd.read_parquet(os.path.join(HIST, f"points_{yr}venues_{yr}.parquet"),
                          columns=["venue", "time_utc", METRIC])
    act["time_utc"] = pd.to_datetime(act.time_utc); act["stad"] = act.venue.str.split("|").str[1]
    ser = {s: gg.set_index("time_utc")[METRIC].sort_index() for s, gg in act.groupby("stad")}
    clim = pd.concat([pd.read_parquet(os.path.join(HIST, f"points_{yr}venues_{c}.parquet"),
                                      columns=["venue", "time_utc", METRIC])
                      for c in CLIM if os.path.exists(os.path.join(HIST, f"points_{yr}venues_{c}.parquet"))],
                     ignore_index=True)
    clim["time_utc"] = pd.to_datetime(clim.time_utc); clim["stad"] = clim.venue.str.split("|").str[1]
    cby = {s: gg for s, gg in clim.groupby("stad")}
    hstads = list(act.stad.unique())
    for m in g.itertuples():
        sbs = str(m.stadium).strip()
        stad = MATCH_VENUE.get(m.match_id) or ALIAS.get(sbs) or (sbs if sbs in hstads else best(sbs, hstads))
        if stad not in hstads or pd.isna(m.kick_off):
            continue
        off = voff.get((yr, stad)) if gender == "men" else round(wlon.get((yr, stad), 0) / 15.0)
        if off is None or (isinstance(off, float) and np.isnan(off)):
            off = round(vlon.get((yr, stad), 0) / 15.0)
        off = int(off)
        ko_utc = pd.Timestamp(f"{m.match_date} {m.kick_off}") - pd.Timedelta(hours=off)
        doy = int(pd.Timestamp(m.match_date).dayofyear)
        s = ser[stad]
        win = s.loc[ko_utc - pd.Timedelta(hours=1): ko_utc + pd.Timedelta(hours=DUR + 1)].dropna()
        if len(win) < 3:
            continue
        winlh = (win.index + pd.Timedelta(hours=off)).hour.values
        c = cby.get(stad); cl = c.time_utc + pd.Timedelta(hours=off)
        cdoy = cl.dt.dayofyear.values; chour = cl.dt.hour.values; cval = c[METRIC].values
        dd = np.abs(cdoy - doy); dd = np.minimum(dd, 365 - dd); inwin = dd <= DOYW
        cnt = {lv: 0 for lv, _ in LEVELS}; tot = 0
        for av, lh in zip(win.values, winlh):
            samp = cval[inwin & (chour == lh)]; samp = samp[~np.isnan(samp)]
            if len(samp) < 30:
                continue
            tot += 1
            for lv, q in LEVELS:
                thr = samp.max() if q is None else np.percentile(samp, q)
                cnt[lv] += int(av > thr)
        if tot < 3:
            continue
        rows.append(dict(gender=gender, year=yr, stadium=stad,
                         goals=int(m.home_score + m.away_score), yellow=int(m.yellow_total),
                         fouls=int(m.fouls_total), gw_wbgt_mean=round(float(win.mean()), 2),
                         **{f"pct_{lv}": 100.0 * cnt[lv] / tot for lv, _ in LEVELS}))

df = pd.DataFrame(rows)
df.to_csv(os.path.join(ROOT, "data/interim/outcomes_vs_climpct.csv"), index=False)
print(f"n matches with outcome + clim-% metric: {len(df)}  ({df.gender.value_counts().to_dict()})")

COL = {"men": "#1f77b4", "women": "#e377c2"}
rng = np.random.default_rng(0)
OUTCOMES = [("goals", "goals per match", "Goals"),
            ("yellow", "yellow cards per match", "Yellow cards"),
            ("fouls", "fouls per match", "Fouls")]
for ycol, ylab, title in OUTCOMES:
    fig, axes = plt.subplots(2, 2, figsize=(14, 11))
    for ax, (lv, q) in zip(axes.ravel(), SCATTER_LEVELS):
        xcol = f"pct_{lv}"
        lvlab = "record (max)" if q is None else f"p{q}"
        for gg, dd in df.groupby("gender"):
            jx = rng.uniform(-1.5, 1.5, len(dd)); jy = rng.uniform(-0.18, 0.18, len(dd))
            ax.scatter(dd[xcol] + jx, dd[ycol] + jy, s=26, alpha=0.4, color=COL[gg])
            if dd[xcol].nunique() > 1:
                r, p = stats.pearsonr(dd[xcol], dd[ycol])
                lr = stats.linregress(dd[xcol], dd[ycol]); sl, ic = lr.slope, lr.intercept
                xs = np.array([dd[xcol].min(), dd[xcol].max()])
                ax.plot(xs, ic + sl * xs, "--", color=COL[gg], lw=2.4,
                        label=f"{gg}: r={r:+.2f} (p={p:.2f}, n={len(dd)})")
        rn, pn = stats.pearsonr(df[xcol], df[ycol])
        ax.set_xlabel(f"% of game hours over {lvlab} climatology", fontsize=13)
        ax.set_ylabel(ylab, fontsize=13)
        ax.set_title(f"vs {lvlab}   (naive-pooled r={rn:+.2f} — Simpson)", fontsize=12.5)
        ax.legend(fontsize=11, title="within-gender fit"); ax.grid(alpha=0.2)
    fig.suptitle(f"{title} vs game-time heat unusualness (climatology-relative), within gender\n"
                 f"StatsBomb complete tournaments: men 2018/22 + women 2019/23 (n={len(df)})", fontsize=14)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    out = os.path.join(ROOT, f"figures/08_discipline/{ycol}_vs_climpct.png")
    fig.savefig(out, dpi=160, bbox_inches="tight")
    print("wrote", out)
    # concise numeric summary
    for lv, q in LEVELS:
        xs = f"pct_{lv}"; parts = []
        for gg, dd in df.groupby("gender"):
            if dd[xs].nunique() > 1:
                r, p = stats.pearsonr(dd[xs], dd[ycol]); parts.append(f"{gg} r={r:+.2f}(p={p:.2f})")
        print(f"  {title:12s} vs {lv:4s}: " + "  ".join(parts))
