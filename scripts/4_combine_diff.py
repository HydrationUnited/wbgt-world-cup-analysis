#!/usr/bin/env python
"""Step 4: Combine per-year global WBGT fields into the change map: mean(1996-2025) - mean(1961-1990).

Reads data/processed/annual_wbgt/wbgt_<year>.nc (from scripts/53, all hourly-derived), averages the
two periods, differences them, masks ocean. -> data/processed/global_wbgt_diff.nc
"""
import glob
import os
import sys
import numpy as np
import xarray as xr

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AW = os.path.join(ROOT, "data/processed/annual_wbgt")


def period_mean(y0, y1):
    fs = [os.path.join(AW, f"wbgt_{y}.nc") for y in range(y0, y1 + 1)]
    fs = [f for f in fs if os.path.exists(f)]
    das = [xr.open_dataarray(f) for f in fs]
    print(f"  {y0}-{y1}: {len(das)} years", flush=True)
    return xr.concat(das, dim="y").mean("y"), len(das)


early, ne = period_mean(1961, 1990)
recent, nr = period_mean(1996, 2025)
diff = (recent - early).values

lat = early["latitude"].values
lon = early["longitude"].values
lsm_f = glob.glob("/glade/campaign/collections/gdex/data/d633000/e5.oper.invariant/*/*172_lsm*.nc")[0]
lsm = xr.open_dataset(lsm_f)
lsm = lsm[[v for v in lsm.data_vars if v != "utc_date"][0]].squeeze().values
diff = np.where(lsm >= 0.5, diff, np.nan)

out = xr.DataArray(diff, coords={"latitude": lat, "longitude": lon},
                   dims=["latitude", "longitude"], name="wbgt_change")
out.attrs.update(units="degC",
                 note=f"WBGT change mean(1996-2025,{nr}yr) - mean(1961-1990,{ne}yr), land only, ERA5 hourly")
p = os.path.join(ROOT, "data/processed/global_wbgt_diff.nc")
out.to_netcdf(p)
print(f"wrote {p}  land change {np.nanmin(diff):.2f}..{np.nanmax(diff):.2f} C, mean {np.nanmean(diff):.2f}",
      flush=True)
