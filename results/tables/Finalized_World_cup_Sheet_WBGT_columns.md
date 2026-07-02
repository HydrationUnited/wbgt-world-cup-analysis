# Finalized_World_cup_Sheet_WBGT — column definitions

Per-game WBGT columns appended to the World Cup match sheet (1259 games, men + women, 1950–2023).
All WBGT values are **WBGT_lilj** — the sunlit outdoor Liljegren WBGT (ISO 7243 weights
0.7/0.2/0.1) computed from **hourly ERA5** (ds633.0: 2 m temperature, 2 m dewpoint, surface
pressure, 10 m wind, shortwave + direct radiation, solar zenith), at the ERA5 0.25° grid cell of
each stadium. Units °C.

## Identifier columns (unchanged from the source sheet)
`gender, country, city, stadium, year, date, time_local, lat, lon`
- `match_date` (added): the authoritative match date `YYYY-MM-DD`. The original `date` column
  carries a placeholder year — use `match_date`.

## Whole-day WBGT (full local calendar day of the match)
| column | meaning |
|---|---|
| `day_wbgt_mean_C` | mean hourly WBGT over the local calendar day |
| `day_wbgt_min_C`  | minimum hourly WBGT over the local calendar day |
| `day_wbgt_max_C`  | maximum hourly WBGT over the local calendar day |

## Game-window WBGT
Game window = **kickoff − 1 h … kickoff + 3 h** (2 h match + 1 h buffer each side); ~5 hourly
samples (4 when kickoff is on the half-hour).
| column | meaning |
|---|---|
| `game_wbgt_mean_C` | mean hourly WBGT in the game window |
| `game_wbgt_min_C`  | minimum hourly WBGT in the game window |
| `game_wbgt_max_C`  | maximum hourly WBGT in the game window |

## Absolute-threshold exceedance (count of game-window hours ≥ threshold)
| column | threshold | basis |
|---|---|---|
| `game_hrs_ge32_FIFA`            | ≥ 32 °C | FIFA cooling-break trigger |
| `game_hrs_ge28_FIFPRO_postpone` | ≥ 28 °C | FIFPRO-proposed postponement level |
| `game_hrs_ge26_FIFPRO_breaks`   | ≥ 26 °C | FIFPRO-proposed cooling-break level |

## Climatology-relative exceedance (count of game-window hours above the local diurnal climatology)
For each game-window hour, the actual WBGT at that **local hour of day** is compared to the
distribution of WBGT at the same stadium, same local hour, over **1960–1990** on the game's
**day-of-year ± 7 days**. A hour is counted if it strictly exceeds the stated level.
| column | level |
|---|---|
| `game_hrs_over_p75_clim` | above the 75th percentile |
| `game_hrs_over_p90_clim` | above the 90th percentile |
| `game_hrs_over_p95_clim` | above the 95th percentile |
| `game_hrs_over_max_clim` | above the 1960–1990 record (maximum) — an unprecedented hour |

Percentiles are computed per local hour (each hour typically has ~450 climatological samples;
hours with < 30 are not counted). The "75/90/95%" levels are **direct percentiles** (p75, p90, p95)
of the climatological distribution, so that the "100 %" column is exactly the historical maximum.

## Notes
- Pre-1979 ERA5 relies on the back-extension; early-tournament values carry correspondingly larger
  reanalysis uncertainty.
- Venue → grid-cell matching is by nearest coordinate; local-time offsets are the tournament-period
  civil offsets (or longitude/15 where a civil offset is unavailable).
- Timestamps are handled in UTC internally and converted to venue-local time for the day and
  game-window definitions.
