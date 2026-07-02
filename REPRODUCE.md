# How to reproduce the figures

The three notebooks in `notebooks/` make the figures. Each notebook only reads small CSV files, so the
quickest path is to open a notebook and run all cells. The sections below say, for each notebook, which
data file it reads and which script builds that file.

## Quick start (figures only, no ERA5 or internet)
Open a notebook in `notebooks/`, set `ROOT` in the first code cell to this folder, and run all cells.
It reads the CSVs already in `data/` and writes its figure to `figures/`.

## Notebook 1 — `diurnal_case_study.ipynb`
| | |
|---|---|
| Figure | `figures/03_climatology/diurnal_case_study.png` |
| Reads | `data/processed/case_study_diurnal_clim.csv`, `_actual.csv`, `_meta.csv` |
| Script that builds the data | `scripts/wc_10_diurnal_case_study.py` |

## Notebook 2 — `pergame_anomaly_summary.ipynb`
| | |
|---|---|
| Figures | `figures/03_climatology/pergame_anomaly_bands_{men,women}.png`, `pergame_absolute_bands_{men,women}.png` |
| Reads | `data/processed/pergame_anomaly_summary_men.csv`, `pergame_anomaly_summary_women.csv` |
| Script that builds the data | `scripts/wc_09_anomaly_summary.py` |

## Notebook 3 — `outcomes_boxwhisker.ipynb`
| | |
|---|---|
| Figures | `figures/08_discipline/fouls_p99_boxwhisker.png`, `fouls_max_boxwhisker.png`, `yellow_boxwhisker.png` |
| Reads | `data/interim/outcomes_vs_climpct.csv` |
| Script that builds the data | `scripts/wc_08_outcomes_vs_climpct.py` |

## Full pipeline (only if you want to rebuild the data from scratch)
Run the scripts in this order. The per-venue WBGT parquets (steps 1–3) are already in
`data/interim/hist/`, so you can skip straight to step 4.

| Step | Script | Produces | Needs |
|---|---|---|---|
| 1 | `wc_01_extract_men.py` | `data/interim/hist/points_*.parquet` (men venues) | ERA5 (GLADE ds633.0) |
| 2 | `wc_02_extract_women_jobs.py` | `data/interim/women_venues.csv`, `women_jobs.csv` | — |
| 3 | `wc_03_extract_women_pbs.py` | `data/interim/hist/points_*.parquet` (women venues) | ERA5 (GLADE ds633.0) |
| 4 | `wc_04_statsbomb_discipline.py` | `data/interim/statsbomb_wc_discipline.csv` | internet (StatsBomb) |
| 5 | `wc_05_pergame_men.py` | `data/interim/pergame_wbgt_men.csv` | steps 1 output |
| 6 | `wc_06_pergame_women.py` | `data/interim/pergame_wbgt_women.csv` | steps 3 output |
| 7 | `wc_07_finalize_wbgt_columns.py` | `results/tables/Finalized_World_cup_Sheet_WBGT.{xlsx,csv}` | steps 5,6 |
| 8 | `wc_08_outcomes_vs_climpct.py` | `data/interim/outcomes_vs_climpct.csv` **(Notebook 3)** | steps 4, parquets |
| 9 | `wc_09_anomaly_summary.py` | `data/processed/pergame_anomaly_summary_{men,women}.csv` **(Notebook 2)** | steps 5,6, parquets |
| 10 | `wc_10_diurnal_case_study.py` | `data/processed/case_study_diurnal_*.csv` **(Notebook 1)** | steps 5,6,7, parquets |
| 11 | `wc_11_build_notebooks.py` | rebuilds the three notebooks (optional) | steps 8,9,10 |

`src/heathack/` holds the WBGT/thermodynamics code used by the extraction steps. The `1_`–`5_` scripts
belong to the separate Li-2020 comparison notebook (`wbgt_vs_li2020_1979.ipynb`).

## Environment
Python 3.11 with numpy, pandas, xarray, matplotlib, scipy, thermofeel, pvlib, netCDF4, pyarrow,
nbformat, nbclient. On NSF NCAR systems the `npl` conda environment plus `pip install --user
thermofeel pvlib` covers it.
