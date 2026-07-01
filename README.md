# Heathack — WBGT at FIFA World Cup venues (shareable bundle)

Code and data to reproduce the notebook `wbgt_vs_li2020_1979.ipynb`, which:
1. computes wet-bulb temperature and WBGT (shaded, simplified, and sunlit/Liljegren) from ERA5;
2. compares the shaded WBGT against the published WBGT-ERA5-v2.0 product (Li, Yuan & Kopp 2020);
3. maps the change in WBGT over land, mean(1996–2025) − mean(1961–1990), with per-city timeseries.

## Layout
```
wbgt_vs_li2020_1979.ipynb   notebook (set ROOT in the first code cell if you move this folder)
src/heathack/               importable package: thermo, era5, era5_fc, config
scripts/                    the pipeline that produced the data files (+ the diurnal figure)
config/project.yaml         paths and parameters (ERA5 lives on the GLADE campaign collection)
data/raw/fifa/venues_all.csv          venue coordinates / cities / timezones
data/raw/fifa/matches_2014.csv        2014 match schedule (kickoff times, venues)
data/staging/li2020/wbgt_1979-*.nc    Li et al. 2020 WBGT-ERA5-v2.0, 1979 months
data/processed/global_wbgt_diff.nc    global WBGT change field (from scripts/3 + scripts/4)
data/interim/hist/points_2014venues_*.parquet   per-venue hourly WBGT at the 2014 venues,
                                      climatology years 1960–1990 plus 2014 (venue, time, WBGT)
results/tables/venue_annual_wbgt.csv  per-venue annual WBGT timeseries
```

## Requirements
- Python 3.11+ with: xarray, numpy, pandas, netCDF4, dask, metpy, thermofeel, pvlib, cartopy,
  statsmodels, matplotlib. (On NSF NCAR systems: the `npl` conda environment, plus
  `pip install --user thermofeel pvlib`.)
- Read access to ERA5 on GLADE: `/glade/campaign/collections/gdex/data/d633000` (ds633.0,
  DOI 10.5065/BH6N-5N20). The notebook reads the hourly surface analysis and forecast radiation
  from there; nothing needs to be downloaded.

## Run
1. Open `wbgt_vs_li2020_1979.ipynb`; if you moved this folder, set `ROOT` in the first code cell to
   its path.
2. Run all cells. The notebook extracts ERA5 at the venue grid points for 1979, computes the WBGT
   variants, and reproduces the comparison and maps. First run takes a few minutes (ERA5 point reads).

## Diurnal-cycle figure (standalone)
`python scripts/5_clim_vs_matches_2014.py` writes
`figures/03_climatology/diurnal_clim_vs_matches_2014.png`: for each 2014 venue, the 1960–1990 diurnal
WBGT climatology (mean, 95% interval, full range) with the actual match hours overlaid (red where a
match hour exceeded the local 95th percentile). It reads only the parquet/CSV files in this bundle,
so it needs no ERA5 access.

## Data sources
- ERA5 hourly surface analysis + forecast radiation: NSF NCAR/RDA ds633.0 (ECMWF ERA5),
  0.25°, 1940–present.
- WBGT-ERA5-v2.0: Li, D., Yuan, J. & Kopp, R. E. (2020), *Environ. Res. Lett.* 15 064003,
  doi:10.1088/1748-9326/ab7d04.
- Venue coordinates and schedules: Wikipedia (per-venue source URLs are recorded during collection).

## Methods, in brief
WBGT is computed from ERA5 2 m temperature, 2 m dewpoint and surface pressure (wet-bulb via Stull
2011; shaded WBGT = 0.7·Tw + 0.3·Ta), with an outdoor Liljegren variant that adds the solar/wind
load using shortwave radiation and 10 m wind. The shaded form matches the external WBGT-ERA5-v2.0
product to a mean bias near zero. All fields here are derived from the hourly ERA5 stream.
