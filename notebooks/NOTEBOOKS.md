# Clean-figure notebooks

Each notebook loads only the small CSVs in `data/` (no ERA5 access needed) and writes a figure.
Set `ROOT` in the first code cell if you move this folder.

## `diurnal_case_study.ipynb`  -> `figures/03_climatology/diurnal_case_study.png`
Four World Cup games vs their stadium x day-of-year (+-7 d) 1960-1990 diurnal WBGT climatology
(mean, p75/p90/p95, record) with the 26/28/32 C reference lines and the game window.
Data: `data/processed/case_study_diurnal_{clim,actual,meta}.csv`.

## `pergame_anomaly_summary.ipynb`  -> `figures/03_climatology/pergame_anomaly_summary_*`
Per game, whether the game-window mean WBGT is above the p75/p90/p95 (or record) of the stadium x
day-of-year 1960-1990 climatology. Men: two panels (composition per tournament + absolute in-play
peak WBGT with trend). Women: composition panel only. Data:
`data/processed/pergame_anomaly_summary_{men,women}.csv` (flags above_p75/p90/p95, above_record).

## `outcomes_boxwhisker.ipynb`  -> `figures/08_discipline/{fouls_*,yellow}_boxwhisker.png`
Distribution of match fouls / yellow cards grouped by the share of the game window hotter than the
local 1960-1990 climatology at each percentile level; dual box-and-whisker for men vs women.
Data: `data/interim/outcomes_vs_climpct.csv`. Sample: complete men (2018/2022) + women (2019/2023).
