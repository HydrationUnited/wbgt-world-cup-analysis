"""worldcupheat: sunlit (Liljegren) WBGT at World Cup stadiums from the ERA5 archive.

Three modules, one linear workflow (driven by the top-level ``run.py``):

  era5  -- xarray readers for the RDA ds633.0 ERA5 archive: hourly surface-analysis
           variables plus de-accumulated forecast radiation (ssrd, fdir), extracted
           at stadium grid cells one month at a time.
  wbgt  -- thermodynamics + solar geometry + the Liljegren WBGT model
           (numpy in / numpy out).
  stats -- match-table utilities: load the cleaned match CSV, slug stadium keys,
           local->UTC kickoff times, nearest-hour WBGT lookup, and per-stadium
           climatological percentiles from the intermediate hourly series.
"""
from . import era5, stats, wbgt

__version__ = "0.1.0"
__all__ = ["era5", "stats", "wbgt"]
