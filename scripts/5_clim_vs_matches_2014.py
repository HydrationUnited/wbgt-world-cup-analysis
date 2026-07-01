#!/usr/bin/env python
"""Step 5: per-venue 1960-1990 diurnal WBGT climatology with the 2014 match hours overlaid."""
import glob
import os
import re
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.lines import Line2D

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from heathack import config  # noqa: E402

cfg = config.load()
CLIM = cfg["climatology"]["period"]
THR = cfg["heat_metric"]["threshold_c"]
METRIC = "WBGT_lilj"
PRE, POST, DUR = cfg["game_window"]["pre_buffer_hours"], cfg["game_window"]["post_buffer_hours"], \
    cfg["game_window"]["default_match_duration_hours"]
HIST = os.path.join(ROOT, "data/interim/hist")
FIG = os.path.join(ROOT, "figures", "03_climatology"); os.makedirs(FIG, exist_ok=True)
YEAR = 2014


def offset_hours(s):
    m = re.match(r"UTC([+-]\d+)", str(s)); return int(m.group(1)) if m else 0


def diurnal_clim(v, off):
    v = v.dropna(subset=[METRIC]).copy()
    v["lh"] = (v.time_utc + pd.to_timedelta(off, "h")).dt.hour
    g = v.groupby("lh")[METRIC]
    return pd.DataFrame({"mean": g.mean(), "p2.5": g.quantile(.025), "p97.5": g.quantile(.975),
                         "min": g.min(), "max": g.max()}).reindex(range(24))


def match_hours(s, matches, off):
    pts = []
    for m in matches.itertuples():
        ko = pd.Timestamp(f"{m.date_local} {m.kickoff_local}") - pd.Timedelta(hours=off)
        dur = DUR + (0.5 if getattr(m, "went_to_extra_time", False) else 0)
        for t, val in s.loc[ko - pd.Timedelta(hours=PRE): ko + pd.Timedelta(hours=dur + POST)].items():
            loc = t + pd.Timedelta(hours=off)
            pts.append((loc.hour + loc.minute / 60, val))
    return pd.DataFrame(pts, columns=["lh", "val"])


# load only the 2014-venue fields we need (climatology years + the tournament year)
clim_files = [os.path.join(HIST, f"points_{YEAR}venues_{y}.parquet") for y in range(CLIM[0], CLIM[1] + 1)]
hist = pd.concat([pd.read_parquet(f, columns=["venue", "time_utc", METRIC])
                  for f in clim_files if os.path.exists(f)], ignore_index=True)
hist["time_utc"] = pd.to_datetime(hist["time_utc"])
tourn = pd.read_parquet(os.path.join(HIST, f"points_{YEAR}venues_{YEAR}.parquet"))
tourn["time_utc"] = pd.to_datetime(tourn["time_utc"])
venues = pd.read_csv(os.path.join(ROOT, "data/raw/fifa/venues_all.csv"))
voff = {f"{r.year}|{r.stadium}": offset_hours(r.utc_offset_during_cup) for r in venues.itertuples()}
mdf = pd.read_csv(os.path.join(ROOT, f"data/raw/fifa/matches_{YEAR}.csv"))
vlist = sorted(tourn.venue.unique())

ncol, C = 4, "#2166ac"
nrow = (len(vlist) + ncol - 1) // ncol
fig, axes = plt.subplots(nrow, ncol, figsize=(5.0 * ncol, 3.8 * nrow), sharex=True, sharey=True,
                         squeeze=False)
axes = axes.ravel()
for ax, vkey in zip(axes, vlist):
    off = voff.get(vkey, 3)
    clim = diurnal_clim(hist[hist.venue == vkey], off)
    s = tourn[tourn.venue == vkey].set_index("time_utc")[METRIC].sort_index()
    mh = match_hours(s, mdf[mdf.venue_stadium == vkey.split("|")[1]], off)
    h = clim.index.values
    ax.fill_between(h, clim["min"], clim["max"], color=C, alpha=0.12)
    ax.fill_between(h, clim["p2.5"], clim["p97.5"], color=C, alpha=0.30)
    ax.plot(h, clim["mean"], color=C, lw=2.6)
    ax.axhline(THR, color="red", ls="--", lw=1.6)
    if len(mh):
        over = mh.val > clim["p97.5"].reindex(mh.lh.round().clip(0, 23).values).values
        ax.scatter(mh.lh[~over], mh.val[~over], s=34, c="black", zorder=6)
        ax.scatter(mh.lh[over], mh.val[over], s=52, c="red", edgecolor="k", lw=0.5, zorder=7)
    ax.set_title(vkey.split("|")[1].split("(")[0].strip(), fontsize=17)
    ax.set_xlim(0, 23); ax.set_xticks([0, 6, 12, 18])
    ax.tick_params(labelsize=14)
    ax.grid(alpha=0.25)
for ax in axes[len(vlist):]:
    ax.axis("off")

handles = [Line2D([], [], color=C, lw=2.6, label="1960–1990 mean"),
           Patch(facecolor=C, alpha=0.30, label="95% range"),
           Patch(facecolor=C, alpha=0.12, label="full range"),
           Line2D([], [], color="black", marker="o", ls="", ms=8, label="match hours"),
           Line2D([], [], color="red", marker="o", ls="", ms=9, mec="k", label="above 95%"),
           Line2D([], [], color="red", ls="--", lw=1.6, label="32 °C (FIFA)")]
fig.suptitle("2014 World Cup: match-hour WBGT vs 1960–1990 climatology", fontsize=20, y=0.995)
fig.legend(handles=handles, loc="upper center", ncol=6, fontsize=15, frameon=False,
           bbox_to_anchor=(0.5, 0.95))
fig.supxlabel("local hour of day", fontsize=17)
fig.supylabel("WBGT (°C)", fontsize=17)
fig.tight_layout(rect=[0.015, 0.02, 1, 0.90])
out = os.path.join(FIG, f"diurnal_clim_vs_matches_{YEAR}.png")
fig.savefig(out, dpi=150, bbox_inches="tight")
print("wrote", out)
