#!/usr/bin/env python
"""Build (and execute) the three clean-figure notebooks from the pre-computed data files.

Notebooks (in notebooks/), each loads only saved CSVs and draws a clean figure:
  1. diurnal_case_study.ipynb          -> figures/03_climatology/diurnal_case_study.png
  2. pergame_anomaly_summary.ipynb     -> figures/03_climatology/pergame_anomaly_summary_men_p{75,90,95}.png
  3. outcomes_boxwhisker.ipynb         -> figures/08_discipline/{fouls,yellow}_boxwhisker.png
"""
import os
import nbformat as nbf
from nbclient import NotebookClient

ROOT = "/glade/derecho/scratch/gavinmad/heathack"
NBDIR = os.path.join(ROOT, "notebooks")
os.makedirs(NBDIR, exist_ok=True)
PYK = {"display_name": "npl", "language": "python", "name": "python3"}


def md(s):
    return nbf.v4.new_markdown_cell(s)


def co(s):
    return nbf.v4.new_code_cell(s)


HDR = f'''import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
# set ROOT to the bundle path if you move this notebook
ROOT = "{ROOT}"
PROC = os.path.join(ROOT, "data", "processed")
plt.rcParams.update({{"font.size": 13, "figure.dpi": 120}})'''

# ---------------- Notebook 1: diurnal case study ----------------
nb1 = nbf.v4.new_notebook(metadata={"kernelspec": PYK})
nb1.cells = [
    md("# Diurnal case-study figure\n"
       "Four World Cup games shown against their stadium × day-of-year (±7 d) **1960–1990 diurnal WBGT "
       "climatology**. Each panel shows the climatological mean and the 75th/90th/95th percentiles and "
       "the record (max) per local hour, the actual game-day hourly WBGT, the game window (kickoff−1 h … "
       "kickoff+3 h), and the 26/28/32 °C reference lines. Data are pre-computed in `data/processed/`."),
    co(HDR),
    co('clim = pd.read_csv(os.path.join(PROC, "case_study_diurnal_clim.csv"))\n'
       'act  = pd.read_csv(os.path.join(PROC, "case_study_diurnal_actual.csv"))\n'
       'meta = pd.read_csv(os.path.join(PROC, "case_study_diurnal_meta.csv"))\n'
       'meta'),
    co('''fig, axes = plt.subplots(2, 2, figsize=(16, 10.5))
for ax, m in zip(axes.ravel(), meta.itertuples()):
    c = clim[clim.case == m.case].sort_values("ph"); a = act[act.case == m.case].sort_values("ph")
    ax.fill_between(c.ph, c.clim_min, c.clim_max, color="#2166ac", alpha=0.08, label="1960–1990 full range")
    ax.plot(c.ph, c.clim_mean, color="#2166ac", lw=2.2, label="clim mean")
    ax.plot(c.ph, c.clim_p75, color="#4a90d9", lw=1.2, ls="--", label="clim p75")
    ax.plot(c.ph, c.clim_p90, color="#8e44ad", lw=1.2, ls="--", label="clim p90")
    ax.plot(c.ph, c.clim_p95, color="#e67e22", lw=1.5, ls="--", label="clim p95")
    ax.plot(c.ph, c.clim_max, color="#7f0000", lw=1.2, ls=":", label="clim record (max)")
    for thr, cc in [(26, "#f6c85f"), (28, "#e8853a"), (32, "red")]:
        ax.axhline(thr, color=cc, lw=1.0, alpha=0.85); ax.text(0.2, thr + 0.2, f"{thr}°C", color=cc, fontsize=8, va="bottom")
    ax.axvspan(m.win_lo, m.win_hi, color="gold", alpha=0.18)
    ax.plot(a.ph, a.wbgt_actual, "o-", color="black", ms=5, lw=1.6, zorder=6, label="actual game day")
    box = (f"game mean/max = {m.game_mean:.1f}/{m.game_max:.1f}°C\\n"
           f"hrs ≥26/≥28/≥32 = {m.hrs_ge26}/{m.hrs_ge28}/{m.hrs_ge32}\\n"
           f"hrs >p75/p90/p95/max = {m.hrs_p75}/{m.hrs_p90}/{m.hrs_p95}/{m.hrs_max}")
    ax.text(0.98, 0.03, box, transform=ax.transAxes, ha="right", va="bottom", fontsize=10.5,
            family="monospace", bbox=dict(boxstyle="round", fc="white", ec="0.6", alpha=0.92))
    ax.set_title(m.label, fontsize=12.5)
    ax.set_xticks(range(0, int(m.maxph) + 1, 3)); ax.grid(alpha=0.2)
    ax.set_xlabel("local hour of day (24 = next-day midnight)"); ax.set_ylabel("WBGT (°C)")
handles = [Line2D([], [], color="black", marker="o", lw=1.6, label="actual game day"),
           Patch(facecolor="gold", alpha=0.18, label="game window (ko−1h … ko+3h)"),
           Line2D([], [], color="#2166ac", lw=2.2, label="clim mean"),
           Line2D([], [], color="#4a90d9", ls="--", label="p75"), Line2D([], [], color="#8e44ad", ls="--", label="p90"),
           Line2D([], [], color="#e67e22", ls="--", label="p95"), Line2D([], [], color="#7f0000", ls=":", label="record"),
           Line2D([], [], color="red", label="32°C FIFA"), Line2D([], [], color="#e8853a", label="28°C FIFPRO"),
           Line2D([], [], color="#f6c85f", label="26°C FIFPRO")]
fig.legend(handles=handles, loc="upper center", ncol=10, fontsize=10, frameon=False, bbox_to_anchor=(0.5, 1.005))
fig.suptitle("World Cup games vs their stadium × day-of-year 1960–1990 diurnal WBGT climatology", fontsize=14, y=1.03)
fig.tight_layout(rect=[0, 0, 1, 0.96])
out = os.path.join(ROOT, "figures/03_climatology/diurnal_case_study.png")
fig.savefig(out, dpi=160, bbox_inches="tight"); print("wrote", out)'''),
]

# ---------------- Notebook 2: pergame anomaly summary (3 levels) ----------------
nb2 = nbf.v4.new_notebook(metadata={"kernelspec": PYK})
nb2.cells = [
    md("# Per-game anomaly summary — men's World Cups\n"
       "For every men's World Cup game, whether the **game-window mean WBGT** sits above the 75th / 90th / "
       "95th percentile (or the record) of the stadium × day-of-year (±7 d) **1960–1990** climatology. "
       "**Left:** composition per tournament (within band / above the percentile / a new record). "
       "**Right:** absolute in-play peak WBGT (game-window max) by year, with trend. Three versions are "
       "produced (75 %, 90 %, 95 %)."),
    co(HDR + '\nfrom scipy import stats\n'
       'DF = {g: pd.read_csv(os.path.join(PROC, f"pergame_anomaly_summary_{g}.csv")) for g in ["men", "women"]}\n'
       '{g: len(v) for g, v in DF.items()}'),
    co('''def make_summary(gender, level, panels="both", save=True):
    d = DF[gender]; yrs = sorted(d.year.unique())
    flag = f"above_p{level}"
    within = [100*((d.year==y)&(~d[flag])).sum()/(d.year==y).sum() for y in yrs]
    above  = [100*((d.year==y)&d[flag]&(~d.above_record)).sum()/(d.year==y).sum() for y in yrs]
    rec    = [100*((d.year==y)&d.above_record).sum()/(d.year==y).sum() for y in yrs]
    x = np.arange(len(yrs))
    if panels == "left":
        fig, axA = plt.subplots(figsize=(9.5, 6.3))
    else:
        fig = plt.figure(figsize=(17, 6.3)); gs = fig.add_gridspec(1, 3, width_ratios=[2, 0, 1], wspace=0.22)
        axA = fig.add_subplot(gs[0, 0]); axB = fig.add_subplot(gs[0, 2])
    axA.bar(x, within, color="#7fb3d5", label=f"within p{level}")
    axA.bar(x, above, bottom=within, color="#f39c12", label=f"above p{level}")
    axA.bar(x, rec, bottom=np.array(within)+np.array(above), color="#c0392b", label="record")
    axA.set_xticks(x); axA.set_xticklabels(yrs, rotation=90, fontsize=12)
    axA.set_ylim(min(within)-3, 100.5); axA.set_ylabel("% of games")
    axA.set_title(f"{gender.title()}'s WC — games vs stadium × date 1960–1990 climatology (p{level})", fontsize=14)
    axA.legend(loc="lower left", fontsize=13, framealpha=0.9); axA.grid(alpha=0.2, axis="y")
    if panels == "both":
        axB.scatter(d.year, d.gw_wbgt_max, s=14, alpha=0.22, color="grey")
        tm = d.groupby("year").gw_wbgt_max.mean(); axB.scatter(tm.index, tm.values, s=70, color="#c0392b", zorder=6)
        sl, ic, r, p, _ = stats.linregress(d.year, d.gw_wbgt_max)
        axB.plot([d.year.min(), d.year.max()], ic+sl*np.array([d.year.min(), d.year.max()]), "b--", lw=2.4,
                 label=f"{sl*10:+.2f} °C/decade"); axB.axhline(32, color="red", ls=":", lw=1.5)
        axB.set_ylabel("in-play peak WBGT (°C)"); axB.set_xlabel("year"); axB.set_title("Absolute in-play heat")
        axB.legend(fontsize=13, loc="upper left"); axB.grid(alpha=0.2)
    fig.tight_layout()
    suffix = "_left" if panels == "left" else ""
    if save:
        out = os.path.join(ROOT, f"figures/03_climatology/pergame_anomaly_summary_{gender}{suffix}_p{level}.png")
        fig.savefig(out, dpi=200, bbox_inches="tight"); print("wrote", out)
    return fig

for lv in [75, 90, 95]:
    make_summary("men", lv, panels="both")       # men: full two-panel
    make_summary("women", lv, panels="left")     # women: climatology-relative LEFT panel only'''),
]

# ---------------- Notebook 3: outcomes box-whiskers (no line) ----------------
nb3 = nbf.v4.new_notebook(metadata={"kernelspec": PYK})
nb3.cells = [
    md("# Fouls & yellow cards vs game-time heat unusualness — box-and-whisker\n"
       "Distribution of match fouls / yellow cards by how much of the game window exceeded the local "
       "diurnal **1960–1990** climatology (p75 / p90 / p95 / record). Games are grouped into **none (0 %)**, "
       "**partial (1–99 %)**, **all (100 %)** of window hours over the level; at each group a **dual box-"
       "and-whisker** shows men vs women (no regression line). Sample: StatsBomb complete tournaments — "
       "men 2018/22 + women 2019/23."),
    co(HDR + '\n'
       'd = pd.read_csv(os.path.join(ROOT, "data/interim/outcomes_vs_climpct.csv"))\n'
       'COL = {"men": "#1f77b4", "women": "#e377c2"}\n'
       'CATS = ["none (0%)", "partial (1–99%)", "all (100%)"]\n'
       'def cat(v):\n'
       '    return np.where(v < 0.5, CATS[0], np.where(v > 99.5, CATS[2], CATS[1]))\n'
       '# each level = a "how unusual" bar: exceeding pXX = hotter than XX% of the 1960-1990 hours at that stadium/hour/day\n'
       'LEVELS = [("pct_p75", "p75", "hotter than 75% of 1960–1990"),\n'
       '          ("pct_p90", "p90", "hotter than 90% of 1960–1990"),\n'
       '          ("pct_p95", "p95", "hotter than 95% of 1960–1990"),\n'
       '          ("pct_max", "record", "hotter than the 1960–1990 record")]'),
    co('''def boxwhisker(ycol, ylab, title, save, levels=LEVELS, suptitle=True):
    if len(levels) == 1:
        fig, ax0 = plt.subplots(figsize=(8.2, 6.6)); axlist = [ax0]
    else:
        fig, axes = plt.subplots(2, 2, figsize=(15, 11)); axlist = list(axes.ravel())
    for ax, (xcol, lab, desc) in zip(axlist, levels):
        dd = d.assign(cat=cat(d[xcol].values))
        handles = []
        for gi, g in enumerate(["men", "women"]):
            data, pos, ns = [], [], []
            for ci, cc in enumerate(CATS):
                v = dd[(dd.gender == g) & (dd.cat == cc)][ycol].values
                if len(v):
                    data.append(v); pos.append(ci + (gi - 0.5) * 0.34); ns.append((ci + (gi - 0.5) * 0.34, len(v)))
            bp = ax.boxplot(data, positions=pos, widths=0.3, patch_artist=True, showfliers=False,
                            medianprops=dict(color="black", lw=1.6))
            for b in bp["boxes"]:
                b.set(facecolor=COL[g], alpha=0.55)
            for xp, n in ns:
                ax.text(xp, ax.get_ylim()[0], f"n={n}", ha="center", va="bottom", fontsize=8, color=COL[g])
            handles.append(Patch(facecolor=COL[g], alpha=0.55, label=g))
        ax.set_xticks(range(len(CATS))); ax.set_xticklabels(CATS)
        ax.set_xlabel("share of game-window hours this hot"); ax.set_ylabel(ylab)
        ax.set_title(f"{desc}  ({lab})", fontsize=12); ax.legend(handles=handles, fontsize=11)
        ax.grid(alpha=0.2, axis="y")
    if suptitle:
        fig.suptitle(f"{title}\\n"
                     f"each panel = a heat-unusualness bar; x = share of the game window above that level; "
                     f"dual box = men/women (box=IQR, whiskers 1.5·IQR).  men 2018/22 + women 2019/23 (n={len(d)})",
                     fontsize=12.5)
    fig.tight_layout(rect=[0, 0, 1, 0.95] if suptitle else [0, 0, 1, 1])
    out = os.path.join(ROOT, f"figures/08_discipline/{save}_boxwhisker.png")
    fig.savefig(out, dpi=160, bbox_inches="tight"); print("wrote", out)

# fouls: single-panel versions at the extreme tail (99th / record), no long title
for tag, lv, q in [("fouls_p99", "p99", 99), ("fouls_max", "max", None)]:
    desc = "hotter than the 1960–1990 record" if q is None else f"hotter than {q}% of 1960–1990"
    boxwhisker("fouls", "fouls per match", "Fouls vs game-time heat unusualness", tag,
               levels=[(f"pct_{lv}", lv, desc)], suptitle=False)
# yellow: full four-panel
boxwhisker("yellow", "yellow cards per match", "Yellow cards vs game-time heat unusualness", "yellow")'''),
]

for name, nb in [("diurnal_case_study", nb1), ("pergame_anomaly_summary", nb2), ("outcomes_boxwhisker", nb3)]:
    path = os.path.join(NBDIR, f"{name}.ipynb")
    print(f"executing {name} ...")
    NotebookClient(nb, timeout=600, kernel_name="python3").execute()
    nbf.write(nb, path)
    print("wrote", path)
