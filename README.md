# worldcupheat — sunlit WBGT at FIFA World Cup stadiums from ERA5

Computes the hourly sunlit (Liljegren) wet-bulb globe temperature at every FIFA World Cup
stadium (1950–2023) from ERA5, then derives per-stadium heat statistics and the WBGT during
each match.

## Layout
```
run.py                          workflow driver — ALL paths and parameters live here
worldcupheat/                   importable package
  era5.py                       xarray ERA5 readers (analysis vars + forecast-radiation de-accumulation)
  wbgt.py                       numba physics: Liljegren WBGT, humidity, solar zenith
  stats.py                      matches CSV handling, timezones, percentiles, per-match WBGT
data/cleaned/world_cup_matches_1950-2023.csv    the ONLY input (1,258 matches, 216 stadiums)
tests/test_wbgt.py              physics pinned to thermofeel 2.2.0 reference values
```

## Workflow (linear)
1. **Extract + compute** (`run.py step1`): for each unique stadium grid cell, read ERA5 hourly
   analysis (2t, 2d, sp, 10u, 10v) and de-accumulated forecast radiation (ssrd, fdir) with
   xarray, compute sunlit WBGT (Liljegren 2008; numba-vectorised), and write one intermediate
   CSV per stadium: `output/stadium_wbgt/{city}_{stadium}.csv` (columns
   `stadium, city, time_utc, wbgt_c, grid_lat, grid_lon`). Re-runs skip existing files.
2. **Statistics** (`run.py step2`): from the intermediates,
   - `output/results/stadium_percentiles.csv` — 75th/90th/95th WBGT percentiles per stadium;
   - `output/results/match_wbgt.csv` — WBGT at each match's kickoff hour (local kickoff
     converted to UTC via timezone derived from stadium lat/lon).

## Install & run
Python 3.11 (numba compatibility). On NSF NCAR systems (Casper/Derecho):
```bash
module load conda && conda activate npl
pip install --user -e .
python run.py          # edit the CONFIG block in run.py first (ERA5 root, YEARS, MONTHS)
```
Locally (tests only — ERA5 lives on GLADE): `uv sync --group dev` or `pip install -e .`.

Run step 1 on a compute node, not a login node: each ERA5 forecast-radiation file is
decompressed whole (~2 GB peak).

## Data
- ERA5 hourly surface analysis + forecast radiation: NSF NCAR/RDA ds633.0,
  `/glade/campaign/collections/gdex/data/d633000` (DOI 10.5065/BH6N-5N20). Nothing downloaded.
- Match schedule/venues: `data/cleaned/world_cup_matches_1950-2023.csv`
  (`gender, country, city, stadium, year, date, time_local, lat, lon`). Matches before 1950
  are out of scope by data design.

## Methods & caveats
- Sunlit WBGT = 0.7·Tnwb + 0.2·Tg + 0.1·Ta with globe and natural-wet-bulb temperatures solved
  from the Liljegren et al. (2008) energy balance — a pure-numba port validated against
  thermofeel 2.2.0 (max |Δ| < 0.1 K over a 2,000-point sweep; pinned in `tests/test_wbgt.py`).
- Solar zenith from a low-precision Spencer (1971) solar-position formula (≲0.5°, ample here).
- Kickoff timezones come from present-day IANA polygons (timezonefinder); pre-1970 local rules
  can be off by up to ~1 h — acceptable at hourly resolution.
- Percentiles cover exactly the `YEARS` × `MONTHS` scope configured in `run.py`.

## Tests
```bash
uv run pytest       # physics reference values; no ERA5/GLADE access needed (runs in CI)
uv run ruff check .
```
