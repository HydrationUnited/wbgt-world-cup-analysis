"""Match-table utilities: load/slug the World Cup CSV, local->UTC times, WBGT lookups.

Input CSV columns (first 9; the file carries empty trailing 'Column 1..17'):
gender, country, city, stadium, year, date (MM-DD), time_local (HH:MM:SS), lat, lon.

Stadiums are identified everywhere by ``stadium_key(city, stadium)`` -- an
ascii slug pair like ``rio-de-janeiro_maracana-estadio-jornalista-mario-filho``,
which is also the intermediate per-stadium CSV filename stem.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd


def load_matches(csv_path) -> pd.DataFrame:
    """Read the cleaned match CSV (first 9 columns) and add naive ``datetime_local``."""
    df = pd.read_csv(csv_path, usecols=range(9))
    df["datetime_local"] = pd.to_datetime(
        df["year"].astype(str) + "-" + df["date"] + " " + df["time_local"])
    return df


def slugify(name: str) -> str:
    """Lowercase ascii slug: NFKD-fold accents, non-alphanumerics -> single hyphens."""
    ascii_name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")


def stadium_key(city: str, stadium: str) -> str:
    """Stable per-stadium identifier (intermediate filename stem)."""
    return f"{slugify(city)}_{slugify(stadium)}"


def unique_stadiums(matches: pd.DataFrame) -> pd.DataFrame:
    """One row per stadium key (first occurrence): stadium, city, country, lat, lon."""
    df = matches.copy()
    df["key"] = [stadium_key(c, s) for c, s in zip(df["city"], df["stadium"])]
    df = df.drop_duplicates("key").set_index("key")
    return df[["stadium", "city", "country", "lat", "lon"]]


def local_to_utc(matches: pd.DataFrame) -> pd.DataFrame:
    """Add ``timezone`` (IANA name) and naive-UTC ``datetime_utc`` columns.

    Timezone per unique (lat, lon) via timezonefinder (imported here, not at module
    top, so the rest of the module works without it); ocean/edge fallbacks go to
    the nautical ``Etc/GMT±N`` zone (note the Etc sign inversion). DST ambiguity
    resolves to standard time; nonexistent local times shift forward.
    """
    from zoneinfo import ZoneInfo

    from timezonefinder import TimezoneFinder

    tf = TimezoneFinder()
    df = matches.copy()

    tz_of = {}
    for la, lo in {(round(float(a), 4), round(float(o), 4))
                   for a, o in zip(df["lat"], df["lon"])}:
        tz = tf.timezone_at(lng=lo, lat=la)
        if tz is None and hasattr(tf, "closest_timezone_at"):
            tz = tf.closest_timezone_at(lng=lo, lat=la)
        if tz is None:
            tz = "Etc/GMT%+d" % round(-lo / 15.0)          # Etc zones invert the sign
        tz_of[(la, lo)] = tz
    df["timezone"] = [tz_of[(round(float(a), 4), round(float(o), 4))]
                      for a, o in zip(df["lat"], df["lon"])]

    utc_parts = []
    for tz, grp in df.groupby("timezone"):
        loc = grp["datetime_local"].dt.tz_localize(
            ZoneInfo(tz), ambiguous=False, nonexistent="shift_forward")
        utc_parts.append(loc.dt.tz_convert("UTC").dt.tz_localize(None))
    df["datetime_utc"] = pd.concat(utc_parts).reindex(df.index)
    return df


def _load_series(path: Path) -> pd.Series:
    """One intermediate stadium CSV -> WBGT series on a sorted, unique UTC index."""
    df = pd.read_csv(path, parse_dates=["time_utc"])
    s = pd.Series(df["wbgt_c"].values, index=pd.DatetimeIndex(df["time_utc"])).sort_index()
    return s[~s.index.duplicated(keep="first")]


def nearest_hour_wbgt(matches: pd.DataFrame, intermediate_dir) -> pd.DataFrame:
    """Add ``wbgt_c`` = the intermediate hourly WBGT nearest each match's datetime_utc.

    ``matches`` must already carry datetime_utc (see :func:`local_to_utc`). Each
    stadium CSV is read once; matches beyond 1 h of any sample, or whose stadium
    has no intermediate file (warned once), get NaN.
    """
    intermediate_dir = Path(intermediate_dir)
    df = matches.copy()
    df["wbgt_c"] = np.nan
    df["_key"] = [stadium_key(c, s) for c, s in zip(df["city"], df["stadium"])]
    cache: dict[str, pd.Series | None] = {}
    for key, grp in df.groupby("_key"):
        if key not in cache:
            path = intermediate_dir / f"{key}.csv"
            if path.is_file():
                cache[key] = _load_series(path)
            else:
                cache[key] = None
                print(f"warning: no intermediate series for {key}; wbgt_c set to NaN")
        ser = cache[key]
        if ser is None:
            continue
        idx = ser.index.get_indexer(pd.DatetimeIndex(grp["datetime_utc"]),
                                    method="nearest", tolerance=pd.Timedelta("1h"))
        vals = ser.values[np.where(idx >= 0, idx, 0)]
        df.loc[grp.index, "wbgt_c"] = np.where(idx >= 0, vals, np.nan)
    return df.drop(columns="_key")


def stadium_percentiles(intermediate_dir, q=(75, 90, 95)) -> pd.DataFrame:
    """Climatological WBGT percentiles per stadium, one row per intermediate CSV.

    Columns: key, stadium, city, n_hours, year_min, year_max, grid_lat, grid_lon,
    wbgt_p{q}. Percentiles cover exactly the hours present in the intermediate
    series (i.e. the year x month scope run.py extracted).
    """
    rows = []
    for path in sorted(Path(intermediate_dir).glob("*.csv")):
        df = pd.read_csv(path, parse_dates=["time_utc"])
        row = {
            "key": path.stem,
            "stadium": df["stadium"].iloc[0],
            "city": df["city"].iloc[0],
            "n_hours": len(df),
            "year_min": int(df["time_utc"].dt.year.min()),
            "year_max": int(df["time_utc"].dt.year.max()),
            "grid_lat": float(df["grid_lat"].iloc[0]),
            "grid_lon": float(df["grid_lon"].iloc[0]),
        }
        for qq in q:
            row[f"wbgt_p{qq}"] = np.nanpercentile(df["wbgt_c"].values, qq)
        rows.append(row)
    return pd.DataFrame(rows)
