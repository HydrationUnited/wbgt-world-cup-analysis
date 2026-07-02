#!/usr/bin/env python
"""Per-match discipline (fouls, cards) from StatsBomb open event data for the men's World Cup.

StatsBomb open-data (github.com/statsbomb/open-data, CC-BY-NC) has full event data for men's WC
seasons: 1958,1962,1970,1974,1986,1990 (scattered famous matches) and 2018,2022 (complete, 64 each).
Foul-committed events are counted per team; cards come from foul_committed.card or bad_behaviour.card.
Output: data/interim/statsbomb_wc_discipline.csv (one row per match, home/away/total fouls & cards).
"""
import os
import sys
import time
import requests
import pandas as pd

ROOT = "/glade/derecho/scratch/gavinmad/heathack"
BASE = "https://raw.githubusercontent.com/statsbomb/open-data/master/data"
UA = {"User-Agent": "Mozilla/5.0 (HEATHACK research; contact gavinmad)"}
# (gender, competition_id, {year: season_id}) — men's WC comp 43, women's WC comp 72
COMPS = [("men", 43, {1958: 269, 1962: 270, 1970: 272, 1974: 51, 1986: 54, 1990: 55,
                      2018: 3, 2022: 106}),
         ("women", 72, {2019: 30, 2023: 107})]
OUT = os.path.join(ROOT, "data/interim/statsbomb_wc_discipline.csv")

sess = requests.Session()
sess.headers.update(UA)


def get_json(url, tries=4):
    for k in range(tries):
        try:
            r = sess.get(url, timeout=45)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                return None
        except Exception as e:
            print(f"  retry {k} {url}: {e}", flush=True)
        time.sleep(2 * (k + 1))
    raise RuntimeError(f"failed {url}")


def card_name(ev):
    """Return the card name on a foul_committed or bad_behaviour event, else None."""
    for key in ("foul_committed", "bad_behaviour"):
        c = ev.get(key)
        if isinstance(c, dict) and isinstance(c.get("card"), dict):
            return c["card"]["name"]
    return None


rows = []
for gender, COMP, SEASONS in COMPS:
  for yr, sid in SEASONS.items():
    matches = get_json(f"{BASE}/matches/{COMP}/{sid}.json")
    print(f"{gender} {yr}: {len(matches)} matches", flush=True)
    for m in matches:
        mid = m["match_id"]
        home = m["home_team"]["home_team_name"]
        away = m["away_team"]["away_team_name"]
        ev = get_json(f"{BASE}/events/{mid}.json")
        if ev is None:
            print(f"  {yr} {mid} {home}-{away}: NO events", flush=True)
            continue
        # per-team tallies keyed by team name
        agg = {home: dict(fouls=0, yc=0, y2=0, rc=0), away: dict(fouls=0, yc=0, y2=0, rc=0)}
        for e in ev:
            tm = e.get("team", {}).get("name")
            if tm not in agg:
                continue
            if e["type"]["name"] == "Foul Committed":
                agg[tm]["fouls"] += 1
            cn = card_name(e)
            if cn == "Yellow Card":
                agg[tm]["yc"] += 1
            elif cn == "Second Yellow":
                agg[tm]["y2"] += 1
            elif cn == "Red Card":
                agg[tm]["rc"] += 1
        # sendings-off = direct red + second yellow; yellows shown = yc + y2
        h, a = agg[home], agg[away]
        rows.append(dict(
            gender=gender, year=yr, match_id=mid, match_date=m.get("match_date"),
            kick_off=m.get("kick_off"),
            stage=m.get("competition_stage", {}).get("name"),
            stadium=(m.get("stadium") or {}).get("name"),
            home_team=home, away_team=away,
            home_score=m.get("home_score"), away_score=m.get("away_score"),
            fouls_home=h["fouls"], fouls_away=a["fouls"], fouls_total=h["fouls"] + a["fouls"],
            yellow_home=h["yc"] + h["y2"], yellow_away=a["yc"] + a["y2"],
            yellow_total=h["yc"] + h["y2"] + a["yc"] + a["y2"],
            red_home=h["rc"] + h["y2"], red_away=a["rc"] + a["y2"],
            red_total=h["rc"] + h["y2"] + a["rc"] + a["y2"],
            n_events=len(ev)))
        time.sleep(0.3)

df = pd.DataFrame(rows).sort_values(["gender", "year", "match_date", "match_id"]).reset_index(drop=True)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
df.to_csv(OUT, index=False)
print(f"\nwrote {OUT}  ({len(df)} matches)")
print("\nper-tournament totals:")
g = df.groupby(["gender", "year"]).agg(matches=("match_id", "count"), fouls=("fouls_total", "sum"),
                                       yellow=("yellow_total", "sum"), red=("red_total", "sum"))
print(g.to_string())
