#!/usr/bin/env python
"""Build the women's-venue extraction job list for a PBS array.

Women's WC venues (from the Finalized sheet) + each tournament's months -> one job per
(tournament_year, extract_year) with extract_year in 1960-1990 (climatology) plus the tournament year
itself (game-day WBGT). Mirrors the men's hist layout so the per-game scripts work unchanged for women.
-> data/interim/women_venues.csv, data/interim/women_jobs.csv
"""
import os
import pandas as pd

ROOT = "/glade/derecho/scratch/gavinmad/heathack"
sheet = pd.read_csv(os.path.join(ROOT, "data/interim/all_games_locations.csv"))
w = sheet[sheet.gender == "Women"].copy()
w["month"] = pd.to_datetime(w.match_date).dt.month

ven = w.groupby(["year", "stadium"]).agg(city=("city", "first"), country=("country", "first"),
      lat=("lat", "first"), lon=("lon", "first")).reset_index()
ven.to_csv(os.path.join(ROOT, "data/interim/women_venues.csv"), index=False)
print(f"women venues: {len(ven)} across {ven.year.nunique()} tournaments")

months = {y: sorted(g.month.unique().tolist()) for y, g in w.groupby("year")}
rows = []
for T, ms in months.items():
    for Y in list(range(1960, 1991)) + [T]:
        rows.append(dict(tournament=T, extract_year=Y, months="|".join(map(str, ms))))
jobs = pd.DataFrame(rows)
jobs.to_csv(os.path.join(ROOT, "data/interim/women_jobs.csv"), index=False)
print(f"tournament months: { {k: v for k, v in months.items()} }")
print(f"jobs (PBS array size): {len(jobs)}  (9 tournaments x 32 years)")
