"""Configuration + path helpers. Single source of truth = config/project.yaml.

Usage:
    from heathack import config
    cfg = config.load()
    p = config.era5_sfc_file('t2m', 202211)   # -> monthly netCDF path (globbed)
"""
from __future__ import annotations
import glob
import os
from functools import lru_cache

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CONFIG_PATH = os.path.join(ROOT, "config", "project.yaml")


@lru_cache(maxsize=1)
def load(path: str = CONFIG_PATH) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def era5_root() -> str:
    return load()["era5"]["root"]


def _vardef(var_key: str) -> dict:
    """Look up a variable definition in either analysis vars or forecast fc_vars."""
    e = load()["era5"]
    if var_key in e.get("vars", {}):
        return e["vars"][var_key]
    if var_key in e.get("fc_vars", {}):
        return e["fc_vars"][var_key]
    raise KeyError(f"unknown var_key {var_key!r}")


def _var_code(var_key: str) -> str:
    """Map a friendly var key (t2m,d2m,sp,ssrd,...) to its ERA5 file code."""
    return _vardef(var_key)["code"]


def ncvar(var_key: str) -> str:
    """Name of the variable *inside* the netCDF file (e.g. VAR_2T, SP, SSRD, FDIR)."""
    return _vardef(var_key)["ncvar"]


def era5_fc_files(var_key: str, yyyymm: int | str) -> list[str]:
    """Forecast-accumulation files for a month (usually 2 spanning ~15 days each)."""
    cfg = load()
    root = cfg["era5"]["root"]
    subdir = cfg["era5"]["fc_accumu"]
    code = _var_code(var_key)
    yyyymm = str(yyyymm)
    pat = os.path.join(root, subdir, yyyymm,
                       f"e5.oper.fc.sfc.accumu.{code}.ll025sc.{yyyymm}*.nc")
    hits = sorted(glob.glob(pat))
    if not hits:
        raise FileNotFoundError(f"No ERA5 fc file for {var_key} {yyyymm}: {pat}")
    return hits


def era5_sfc_file(var_key: str, yyyymm: int | str) -> str:
    """Absolute path to the ERA5 surface-analysis monthly file for a variable.

    Uses glob on the code + yyyymm prefix so we don't have to compute month length.
    Raises FileNotFoundError if missing (fail loud — provenance matters).
    """
    cfg = load()
    root = cfg["era5"]["root"]
    subdir = cfg["era5"]["sfc_analysis"]
    code = _var_code(var_key)
    yyyymm = str(yyyymm)
    pat = os.path.join(root, subdir, yyyymm,
                       f"e5.oper.an.sfc.{code}.ll025sc.{yyyymm}*.nc")
    hits = sorted(glob.glob(pat))
    if not hits:
        raise FileNotFoundError(f"No ERA5 file for var={var_key} month={yyyymm}: {pat}")
    if len(hits) > 1:
        raise RuntimeError(f"Ambiguous ERA5 match ({len(hits)}) for {pat}: {hits}")
    return hits[0]


def to_era5_lon(lon: float) -> float:
    """ERA5 longitudes are 0..360. Convert a possibly-negative lon into [0,360)."""
    return lon % 360.0


def path(*parts: str) -> str:
    """Join a path under the project root."""
    return os.path.join(ROOT, *parts)
