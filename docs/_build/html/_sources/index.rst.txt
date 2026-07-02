WBGT World Cup Heat Analysis
============================

This project was created for `HeatHack 2026 <https://karenamckinnon.github.io/heathack.html>`_,
a hackathon for early-career climate and statistics researchers hosted at the National
Center for Atmospheric Research (NCAR) Mesa Lab in Boulder, Colorado (June 30 – July 2, 2026).
The documentation gives an overview of the project framing, the methodology, and the steps for
reproducing the results.

The analysis computes the hourly **sunlit wet-bulb globe temperature (WBGT)** at every FIFA
World Cup stadium from 1950 to 2023 using the ERA5 reanalysis, then derives per-stadium heat
statistics and the WBGT at the kickoff of each match.

Primary Research Questions
--------------------------

1. **What percentage of World Cup matches (1950–2023) have exceeded the 26 °C, 28 °C, and
   32 °C wet-bulb globe temperature (WBGT) thresholds?** These thresholds correspond to
   escalating heat-stress guidance for physical activity.

2. **How has match-time WBGT changed over time relative to a per-stadium climatological
   baseline?** Each stadium's baseline is the distribution of its own historical hourly WBGT
   over the tournament months (see :doc:`generate_data`), so a match can be placed against the
   local climate rather than an absolute scale.

Methodology
-----------

:Computational resource:
   NCAR Casper HPC, high-throughput compute nodes.
:Climate dataset:
   ERA5 0.25° × 0.25° hourly surface analysis and forecast-radiation data (NSF NCAR / RDA
   ds633.0, ``/glade/campaign/collections/gdex/data/d633000``, DOI
   `10.5065/BH6N-5N20 <https://doi.org/10.5065/BH6N-5N20>`_).
:Match dataset:
   Gender, host city, stadium, date, and local kickoff time for each World Cup match from 1950
   to 2023, pulled from `FBref <https://fbref.com/en/>`_ with stadium latitude and longitude
   coordinates validated by hand. Matches before 1950 are out of scope by data design.

For each match we take the host stadium's latitude/longitude and extract an hourly time series
for the nearest ERA5 grid cell. Seven ERA5 variables feed the WBGT model:

.. list-table::
   :header-rows: 1
   :widths: 12 14 50 12

   * - Short name
     - ERA5 code
     - Description
     - Source
   * - ``t2m``
     - ``2t``
     - 2 m air (dry-bulb) temperature
     - Analysis
   * - ``d2m``
     - ``2d``
     - 2 m dew-point temperature (used to derive relative humidity)
     - Analysis
   * - ``sp``
     - ``sp``
     - Surface pressure
     - Analysis
   * - ``u10``
     - ``10u``
     - 10 m eastward wind component
     - Analysis
   * - ``v10``
     - ``10v``
     - 10 m northward wind component
     - Analysis
   * - ``ssrd``
     - ``ssrd``
     - Surface solar radiation downwards (global horizontal shortwave)
     - Forecast
   * - ``fdir``
     - ``fdir``
     - Direct (beam) component of surface solar radiation
     - Forecast

The two forecast-radiation fields are stored as per-step hourly accumulations
[J m\ :sup:`-2`]; dividing by 3600 s gives the hourly-mean flux [W m\ :sup:`-2`]. From these raw
variables the model derives needed quantities to compute WBGT: relative humidity from ``t2m``
and ``d2m`` (Buck 1981/1996), 10 m wind speed from ``u10`` and ``v10``, the direct-beam fraction
``fdir / ssrd`` (clipped to [0, 0.9]), and the cosine of the solar zenith angle from a
Spencer (1971) solar-position formula.

Computing WBGT
~~~~~~~~~~~~~~

Sunlit WBGT is the standard weighted sum of three temperatures:

.. math::

   \mathrm{WBGT} = 0.7\,T_\mathrm{nwb} + 0.2\,T_\mathrm{g} + 0.1\,T_\mathrm{a}

where

* :math:`T_\mathrm{a}` is the 2 m air (dry-bulb) temperature, taken directly from ``t2m``;
* :math:`T_\mathrm{g}` is the **globe temperature**, the equilibrium temperature of a standard
  black globe; and
* :math:`T_\mathrm{nwb}` is the **natural wet-bulb temperature**, the equilibrium temperature of
  a naturally ventilated wetted wick.

:math:`T_\mathrm{g}` and :math:`T_\mathrm{nwb}` have no closed form. Each is solved iteratively
from a steady-state energy balance following Liljegren et al. (2008), which couples the sensor's
radiative exchange (direct beam, diffuse sky, and ground-reflected shortwave plus longwave) to
convective evaporative exchange with the surrounding air. Before the
balance is solved, the 10 m wind is scaled to the 2 m sensor height through a Pasquill–Gifford
stability class derived from wind speed and incoming solar radiation.

The physics is a pure-`numba <https://numba.pydata.org/>`_ port of the WBGT implementation in
`thermofeel 2.2.0 <https://github.com/ecmwf/thermofeel>`_ (ECMWF, Apache-2.0), itself validated
against Liljegren's reference C code. The port is pinned to thermofeel reference values in the
test suite (max \|Δ\| < 0.1 K over a 2,000-point sweep). See :doc:`dev` for the attribution
details.

From the resulting hourly WBGT series the analysis produces two outputs per run: the WBGT at
each match's kickoff hour, and per-stadium climatological WBGT percentiles over the configured
tournament months. Both are described in :doc:`generate_data`.

Caveats
~~~~~~~

* The solar zenith comes from a low-precision Spencer (1971) formula (error ≲ 0.5°), which is
  ample at hourly resolution.
* Kickoff time zones are resolved from present-day IANA polygons; pre-1970 local rules can
  differ by up to ~1 h, acceptable given the hourly ERA5 sampling.
* Percentiles cover exactly the year × month scope configured in ``run.py`` (see
  :doc:`generate_data`), not a fixed reference period.

Contents
--------

.. toctree::
   :maxdepth: 2

   generate_data
   dev
