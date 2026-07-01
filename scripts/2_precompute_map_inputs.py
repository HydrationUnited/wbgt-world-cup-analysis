#!/usr/bin/env python
"""Step 2: Precompute inputs for the global-map figure in the notebook.

(1) Global climatological-mean SHADED WBGT (1991-2020) from ERA5 monthly means (d633001),
    computed with dask -> data/processed/global_wbgt_clim.nc  (global 0.25 deg field).
(2) Per-venue annual sunlit WBGT (annual mean of daily-max WBGT_liljegren, 1960-2024) from the
    historical extraction -> results/tables/venue_annual_wbgt.csv (with city/lat/lon).
Heavy step is (1); use dask (local threads here; a PBSCluster is shown in the notebook).
"""
import glob
import os
import sys
import numpy as np
import pandas as pd
import xarray as xr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from heathack import config, thermo  # noqa: E402

cfg = config.load()
TMONTHS = {t["year"]: set(t["months"]) for t in cfg["world_cups"]["tournaments"]}
MODA = "/glade/campaign/collections/gdex/data/d633001/e5.moda.an.sfc"
os.makedirs(os.path.join(ROOT, "data/processed"), exist_ok=True)


def global_wbgt_clim(years=range(1991, 2021)):
    def load(code, var):
        fs = sorted(f for y in years for f in glob.glob(f"{MODA}/{y}/*{code}*.nc"))
        return xr.open_mfdataset(fs, combine="by_coords", chunks={"latitude": 240})[var]
    t2m = load("128_167_2t", "VAR_2T")
    d2m = load("128_168_2d", "VAR_2D")

    def shaded(tk, tdk):                       # K,K -> shaded WBGT [C]
        ta = tk - 273.15
        td = tdk - 273.15
        rh = thermo.rh_from_t_td(ta, td)
        tw = thermo.wet_bulb_stull(ta, rh)
        return 0.7 * tw + 0.3 * ta
    wb = xr.apply_ufunc(shaded, t2m, d2m, dask="parallelized", output_dtypes=[float])
    clim = wb.mean("time").compute()
    clim.name = "wbgt_shade_clim"
    clim.attrs.update(period="1991-2020 annual mean", units="degC",
                      note="shaded WBGT = 0.7*Tw(Stull)+0.3*Ta from ERA5 monthly means")
    out = os.path.join(ROOT, "data/processed/global_wbgt_clim.nc")
    clim.to_netcdf(out)
    print(f"[1] wrote {out}  range {float(clim.min()):.1f}..{float(clim.max()):.1f} C")


def venue_annual():
    files = sorted(glob.glob(os.path.join(ROOT, "data/interim/hist/points_*venues_*.parquet")))
    hist = pd.concat([pd.read_parquet(f, columns=["venue", "time_utc", "WBGT_lilj"]) for f in files],
                     ignore_index=True)
    hist["time_utc"] = pd.to_datetime(hist["time_utc"])
    ven = pd.read_csv(os.path.join(ROOT, "data/raw/fifa/venues_all.csv"))
    meta = {f"{r.year}|{r.stadium}": (r.city, r.country, r.lat, r.lon) for r in ven.itertuples()}
    rows = []
    for vkey, g in hist.groupby("venue"):
        ty = int(vkey.split("|")[0])
        months = TMONTHS.get(ty, {6, 7})
        d = g[g.time_utc.dt.month.isin(months)].dropna(subset=["WBGT_lilj"]).copy()
        d["date"] = d.time_utc.dt.date
        dm = d.groupby("date")["WBGT_lilj"].max()
        dm.index = pd.to_datetime(dm.index)
        ann = dm.groupby(dm.index.year).mean()
        city, country, lat, lon = meta.get(vkey, ("", "", np.nan, np.nan))
        for y, v in ann.items():
            rows.append({"venue": vkey, "tour": ty, "city": city, "country": country,
                         "lat": lat, "lon": lon, "year": int(y), "wbgt_sun": round(float(v), 2)})
    df = pd.DataFrame(rows)
    out = os.path.join(ROOT, "results/tables/venue_annual_wbgt.csv")
    df.to_csv(out, index=False)
    print(f"[2] wrote {out}  {df.venue.nunique()} venues, {df.year.min()}-{df.year.max()}")


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("both", "map"):
        global_wbgt_clim()
    if which in ("both", "venue"):
        venue_annual()
