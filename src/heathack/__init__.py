"""heathack — extreme heat / wet-bulb exceedance at FIFA World Cup venues from ERA5.

Modules:
    config       : load config/project.yaml; path builders; constants.
    era5         : nearest-grid-point extraction from ERA5 monthly netCDF (UTC).
    thermo       : wet-bulb (Stull, metpy/Davies-Jones) and WBGT approximations.
    climatology  : 1960-1990 diurnal climatology (mean, 95% CI, full range) per venue.
    exceedance   : threshold-exceedance hours within match windows and monthly series.
    viz          : sanity/publication plotting helpers.

All timestamps are timezone-aware; ERA5 is UTC. Never mix UTC and local silently.
"""
__version__ = "0.1.0"
