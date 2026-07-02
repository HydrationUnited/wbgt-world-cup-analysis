#!/usr/bin/env python
"""Append per-game WBGT columns to a copy of the Finalized World Cup sheet (all 1259 games).

For every game (men + women, 1950-2023) compute, from hourly ERA5 WBGT_lilj:
  day  WBGT: mean / min / max  over the full local calendar day of the match
  game WBGT: mean / min / max  over the game window  = kickoff-1h .. kickoff+3h (5 hourly samples;
             match 2h + 1h buffer each side, per config game_window)
  absolute-threshold exceedance hours in the game window:
             FIFA >=32C (cooling break), FIFPRO >=28C (postpone), FIFPRO >=26C (breaks)  [ADR 0001]
  climatology-relative exceedance hours in the game window (per LOCAL HOUR, stadium x day-of-year +-7d,
             1960-1990 diurnal climatology):  above p75 / p90 / p95 / above the record (max, "100%")

Venue match + UTC offset are reused from the validated pergame CSVs (scripts 40/48). Output is a copy
of the xlsx with the 9 original columns + 13 named WBGT columns.  Also writes a case-study verification
figure so the counts can be checked by eye against the diurnal climatology.
"""
import os
import re
import numpy as np
import pandas as pd

ROOT = "/glade/derecho/scratch/gavinmad/heathack"
SRC = "/glade/derecho/scratch/gavinmad/shared/Heathack/results/tables/Finalized_World_cup_Sheet.xlsx"
OUT_XLSX = os.path.join(ROOT, "results/tables/Finalized_World_cup_Sheet_WBGT.xlsx")
METRIC = "WBGT_lilj"
HIST = os.path.join(ROOT, "data/interim/hist")
CLIM = list(range(1960, 1991))
DOYW = 7           # +- days around the game day-of-year for the climatology sample
DUR = 2.0          # match hours; window = ko-1 .. ko+DUR+1  -> 5 hourly samples
NWIN = int(DUR + 2) + 1                 # 5 samples: k = 0..4 -> ko-1,ko,ko+1,ko+2,ko+3
FIFA, FPRO_POST, FPRO_BRK = 32.0, 28.0, 26.0
GEN = {"estadio", "stadio", "stadium", "stade", "arena", "stadion", "de", "la", "el", "du", "of",
       "ii", "now", "co", "the"}

# ---- final column names (order == user's list 1..13) ----
COLS = {
    "day_wbgt_mean_C": "day mean WBGT",
    "day_wbgt_min_C": "day min WBGT",
    "day_wbgt_max_C": "day max WBGT",
    "game_wbgt_mean_C": "game-window mean WBGT",
    "game_wbgt_min_C": "game-window min WBGT",
    "game_wbgt_max_C": "game-window max WBGT",
    "game_hrs_ge32_FIFA": "game hrs >=32C (FIFA)",
    "game_hrs_ge28_FIFPRO_postpone": "game hrs >=28C (FIFPRO postpone)",
    "game_hrs_ge26_FIFPRO_breaks": "game hrs >=26C (FIFPRO breaks)",
    "game_hrs_over_p75_clim": "game hrs > p75 clim",
    "game_hrs_over_p90_clim": "game hrs > p90 clim",
    "game_hrs_over_p95_clim": "game hrs > p95 clim",
    "game_hrs_over_max_clim": "game hrs > record (max) clim",
}


def toks(s):
    return set(re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split()) - GEN


def best(name, cands):
    mt = toks(name); b, bn = None, 0
    for c in cands:
        n = len(mt & toks(c))
        if n > bn:
            bn, b = n, c
    return b if bn >= 1 else None


# ---------- load sheet, reconstruct the real match date (xlsx 'date' has a placeholder year) ----------
sheet = pd.read_excel(SRC)
sheet = sheet[[c for c in sheet.columns if not str(c).startswith("Column ")]].copy()
d = pd.to_datetime(sheet["date"])
sheet["match_date"] = [pd.Timestamp(year=int(y), month=int(mo), day=int(dy)).strftime("%Y-%m-%d")
                       for y, mo, dy in zip(sheet.year, d.dt.month, d.dt.day)]
sheet["tstr"] = pd.to_datetime(sheet["time_local"].astype(str)).dt.strftime("%H:%M:%S")
sheet["gl"] = sheet.gender.str.lower()

# ---------- validated venue match + offset from pergame CSVs (keyed robustly) ----------
pg = pd.concat([pd.read_csv(os.path.join(ROOT, "data/interim/pergame_wbgt_men.csv")),
                pd.read_csv(os.path.join(ROOT, "data/interim/pergame_wbgt_women.csv"))],
               ignore_index=True)
pg = pg[pg.matched == True].copy()
pg["tstr"] = pd.to_datetime(pg.time_local.astype(str)).dt.strftime("%H:%M:%S")
pg["md"] = pd.to_datetime(pg.match_date).dt.strftime("%Y-%m-%d")


def gkey(gl, yr, stad, md, tstr):
    return (gl, int(yr), str(stad), str(md), str(tstr))


lu = {}                      # game -> (hist_stadium, utc_off)
stored = {}                  # game -> stored gw_wbgt_max (sanity cross-check)
for r in pg.itertuples():
    k = gkey(r.gender, r.year, r.stadium, r.md, r.tstr)
    lu[k] = (r.hist_stadium, int(round(r.utc_off)))
    stored[k] = r.gw_wbgt_max

ven = pd.read_csv(os.path.join(ROOT, "data/raw/fifa/venues_all.csv"))


def match_inline(gl, yr, stadium, lat, lon, series_keys, vy):
    """Fallback venue match if a game is missing from the lookup: nearest-coord (men) / token (any)."""
    if len(vy):
        dd = (vy.lat - lat) ** 2 + (vy.lon - lon) ** 2
        cand = vy.loc[dd.idxmin(), "stadium"]
        if cand in series_keys:
            return cand, int(round(lon / 15.0))
    if stadium in series_keys:
        return stadium, int(round(lon / 15.0))
    b = best(stadium, list(series_keys))
    return (b, int(round(lon / 15.0))) if b else (None, None)


# ---------- main pass, per tournament-year ----------
res = {c: np.full(len(sheet), np.nan) for c in COLS}
matched = np.zeros(len(sheet), dtype=bool)
sanity = []                                   # (recomputed_gwmax, stored_gwmax)
years = sorted(sheet.year.unique())
for yr in years:
    hf = os.path.join(HIST, f"points_{yr}venues_{yr}.parquet")
    cfs = [os.path.join(HIST, f"points_{yr}venues_{c}.parquet") for c in CLIM]
    cfs = [f for f in cfs if os.path.exists(f)]
    if not (os.path.exists(hf) and cfs):
        print(f"{yr}: missing hist/clim -> skip ({os.path.exists(hf)}, {len(cfs)} clim)")
        continue
    act = pd.read_parquet(hf, columns=["venue", "time_utc", METRIC])
    act["time_utc"] = pd.to_datetime(act.time_utc); act["stad"] = act.venue.str.split("|").str[1]
    ser = {s: g.set_index("time_utc")[METRIC].sort_index() for s, g in act.groupby("stad")}
    clim = pd.concat([pd.read_parquet(f, columns=["venue", "time_utc", METRIC]) for f in cfs],
                     ignore_index=True)
    clim["time_utc"] = pd.to_datetime(clim.time_utc); clim["stad"] = clim.venue.str.split("|").str[1]
    cby = {s: g for s, g in clim.groupby("stad")}
    vy = ven[ven.year == yr]
    idxs = sheet.index[sheet.year == yr]
    for i in idxs:
        row = sheet.loc[i]
        k = gkey(row.gl, yr, row.stadium, row.match_date, row.tstr)
        if k in lu:
            stad, off = lu[k]
        else:
            stad, off = match_inline(row.gl, yr, row.stadium, row.lat, row.lon, ser.keys(), vy)
        if stad is None or stad not in ser or off is None:
            continue
        s = ser[stad]
        try:
            ko_utc = pd.Timestamp(f"{row.match_date} {row.tstr}") - pd.Timedelta(hours=off)
        except Exception:
            continue
        ko_h = int(pd.Timestamp(row.tstr).hour)
        doy = int(pd.Timestamp(row.match_date).dayofyear)

        # ---- day metrics (full local calendar day) ----
        loc = s.index + pd.Timedelta(hours=off)
        day = s[loc.strftime("%Y-%m-%d") == row.match_date].dropna()

        # ---- game-window samples: SLICE ko-1h .. ko+(DUR+1)h (handles :30 kickoffs, matches script 40) ----
        win = s.loc[ko_utc - pd.Timedelta(hours=1): ko_utc + pd.Timedelta(hours=DUR + 1)].dropna()
        if len(win) < 3 or len(day) < 3:
            continue
        gwv = win.values
        winlh = (win.index + pd.Timedelta(hours=off)).hour.values     # local hour of each sample

        # ---- climatology per LOCAL HOUR for this stadium (doy +-7) ----
        c = cby.get(stad)
        cl = c.time_utc + pd.Timedelta(hours=off)
        cdoy = cl.dt.dayofyear.values; chour = cl.dt.hour.values; cval = c[METRIC].values
        dd = np.abs(cdoy - doy); dd = np.minimum(dd, 365 - dd)
        inwin = dd <= DOYW
        p75c = p90c = p95c = maxc = 0
        for av, lh in zip(gwv, winlh):
            samp = cval[inwin & (chour == lh)]
            samp = samp[~np.isnan(samp)]
            if len(samp) < 30:
                continue
            p75c += int(av > np.percentile(samp, 75))
            p90c += int(av > np.percentile(samp, 90))
            p95c += int(av > np.percentile(samp, 95))
            maxc += int(av > samp.max())

        res["day_wbgt_mean_C"][i] = round(float(day.mean()), 2)
        res["day_wbgt_min_C"][i] = round(float(day.min()), 2)
        res["day_wbgt_max_C"][i] = round(float(day.max()), 2)
        res["game_wbgt_mean_C"][i] = round(float(gwv.mean()), 2)
        res["game_wbgt_min_C"][i] = round(float(gwv.min()), 2)
        res["game_wbgt_max_C"][i] = round(float(gwv.max()), 2)
        res["game_hrs_ge32_FIFA"][i] = int((gwv >= FIFA).sum())
        res["game_hrs_ge28_FIFPRO_postpone"][i] = int((gwv >= FPRO_POST).sum())
        res["game_hrs_ge26_FIFPRO_breaks"][i] = int((gwv >= FPRO_BRK).sum())
        res["game_hrs_over_p75_clim"][i] = p75c
        res["game_hrs_over_p90_clim"][i] = p90c
        res["game_hrs_over_p95_clim"][i] = p95c
        res["game_hrs_over_max_clim"][i] = maxc
        matched[i] = True
        if k in stored and not np.isnan(stored[k]):
            sanity.append((res["game_wbgt_max_C"][i], stored[k]))
    print(f"{yr}: {int(matched[idxs].sum())}/{len(idxs)} games with WBGT columns")

# ---------- assemble output (original 9 cols + 13 WBGT cols, in sheet row order) ----------
out = sheet[["gender", "country", "city", "stadium", "year", "date", "time_local", "lat", "lon"]].copy()
out["match_date"] = sheet["match_date"]
for c in COLS:
    out[c] = res[c]
os.makedirs(os.path.dirname(OUT_XLSX), exist_ok=True)
out.to_excel(OUT_XLSX, index=False)
out.to_csv(OUT_XLSX.replace(".xlsx", ".csv"), index=False)

# ---------- report + sanity ----------
print(f"\nwrote {OUT_XLSX}  ({len(out)} games, {matched.sum()} with WBGT)")
if sanity:
    a = np.array(sanity); dif = np.abs(a[:, 0] - a[:, 1])
    print(f"sanity vs stored gw_wbgt_max: n={len(a)}, max|diff|={dif.max():.3f}C, mean|diff|={dif.mean():.4f}C")
mm = matched
print(f"game-window max WBGT range: {np.nanmin(res['game_wbgt_max_C']):.1f}..{np.nanmax(res['game_wbgt_max_C']):.1f}C")
for c in ["game_hrs_ge32_FIFA", "game_hrs_ge28_FIFPRO_postpone", "game_hrs_ge26_FIFPRO_breaks",
          "game_hrs_over_p75_clim", "game_hrs_over_p90_clim", "game_hrs_over_p95_clim",
          "game_hrs_over_max_clim"]:
    v = res[c][mm]
    print(f"  {c:32s}: games with >=1 hr = {(v >= 1).sum():4d}   total hrs = {int(np.nansum(v))}")
