#!/usr/bin/env python
"""Step 3: One year's global annual-mean WBGT from HOURLY ERA5 (d633000), computed with dask.

WBGT here is the shaded form 0.7*Tw(Stull)+0.3*Ta from hourly 2t/2d/sp -- the exact quantity
validated against Li et al. (2020) WBGT-ERA5-v2.0 (bias -0.06 C). Everything is from the hourly
analysis stream (no monthly-mean products). Writes data/processed/annual_wbgt/wbgt_<year>.nc
(global 2D). A PBS array over years builds the record; scripts/54 combines periods.

Usage:  3_annual_global_wbgt.py --year 1975
"""
import argparse
import glob
import os
import sys
import numpy as np
import xarray as xr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from heathack import thermo  # noqa: E402

D000 = "/glade/campaign/collections/gdex/data/d633000/e5.oper.an.sfc"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, required=True)
    a = ap.parse_args()
    y = a.year

    def load(code, var):
        fs = sorted(f for m in range(1, 13) for f in glob.glob(f"{D000}/{y}{m:02d}/*{code}*.nc"))
        return xr.open_mfdataset(fs, combine="by_coords", chunks={"time": 24})[var]

    t2 = load("128_167_2t", "VAR_2T")
    d2 = load("128_168_2d", "VAR_2D")

    def shaded(tk, tdk):
        ta = tk - 273.15
        rh = thermo.rh_from_t_td(ta, tdk - 273.15)
        return 0.7 * thermo.wet_bulb_stull(ta, rh) + 0.3 * ta

    wb = xr.apply_ufunc(shaded, t2, d2, dask="parallelized", output_dtypes=[float])
    ann = wb.mean("time").compute()
    ann.name = "wbgt_shade"
    ann.attrs.update(year=y, units="degC", source="ERA5 hourly d633000; 0.7*Tw(Stull)+0.3*Ta")
    out = os.path.join(ROOT, "data/processed/annual_wbgt", f"wbgt_{y}.nc")
    ann.to_netcdf(out)
    print(f"wrote {out}  global mean {float(ann.mean()):.1f} C  "
          f"range {float(ann.min()):.1f}..{float(ann.max()):.1f}", flush=True)


if __name__ == "__main__":
    main()
