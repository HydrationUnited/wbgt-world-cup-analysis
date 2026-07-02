Reproducing the Analysis Data
=============================

The analysis has two inputs: the ERA5 reanalysis, which lives on NCAR Campaign (GDEX) storage
and is *never downloaded*, and the World Cup match table, which is committed to this repository
at::

   data/cleaned/world_cup_matches_1950-2023.csv

Each stadium's location was verified by hand for accuracy; stadium names, kickoff times, and
match gender were pulled from `FBref <https://fbref.com/en/>`_. Because ERA5 is read in place,
step 1 of the workflow must run on a system with access to the GDEX archive.

Install
-------

Reproducing the full data set requires access to a Casper compute node. Clone the repository and
install the package into a virtual environment:

.. code-block:: bash

   git clone https://github.com/HydrationUnited/wbgt-world-cup-analysis.git
   cd wbgt-world-cup-analysis
   pip install -e .

On NSF NCAR systems (Casper / Derecho) load a Python 3.11 environment first:

.. code-block:: bash

   module load conda && conda activate npl
   pip install --user -e .

Only Python 3.11 is committed to (see ``.python-version``); newer versions may lag numba's
supported range.

Configure
---------

All paths and parameters live in the ``CONFIG`` block at the top of ``run.py``. Edit it before
running:

.. code-block:: python

   ERA5_ROOT   = "/glade/campaign/collections/gdex/data/d633000"  # ERA5 archive root
   MATCHES_CSV = "data/cleaned/world_cup_matches_1950-2023.csv"    # committed match table
   OUT_DIR     = "output"                                          # all results land here
   YEARS       = range(1950, 2024)                                 # inclusive of 1950–2023
   MONTHS      = (5, 6, 7, 11, 12)                                 # tournament months

``YEARS`` and ``MONTHS`` are applied as a Cartesian product to every stadium, and they define
exactly the scope of the per-stadium climatological percentiles.

Run
---

Run the entry script from a compute node (a login node lacks the memory and each forecast-radiation
file is decompressed whole, peaking near ~2 GB):

.. code-block:: bash

   python run.py

The workflow is linear and resumable:

**Step 1 - extract and compute.**
   For each unique stadium grid cell, ``run.py`` reads the hourly ERA5 analysis variables and the
   de-accumulated forecast radiation, computes sunlit WBGT (see :doc:`index`), and writes one
   intermediate hourly CSV per stadium to ``output/stadium_wbgt/{key}.csv`` with columns
   ``stadium, city, time_utc, wbgt_c, grid_lat, grid_lon``. Months are extracted in parallel
   across a process pool (netCDF/HDF5 is not thread-safe). Stadiums whose CSV already exists are
   skipped, so an interrupted run can simply be restarted.

**Step 2 - statistics.**
   From the intermediate series, ``run.py`` writes two result tables:

   * ``output/results/stadium_percentiles.csv`` - the 75th, 90th, and 95th WBGT percentiles per
     stadium, plus hour counts and the year range covered.
   * ``output/results/match_wbgt.csv`` - the WBGT at each match's kickoff hour. The local kickoff
     is converted to UTC using the time zone derived from the stadium's coordinates, then matched
     to the nearest hourly sample within a one-hour tolerance (matches outside that window, or at
     stadiums with no extracted series, are recorded as ``NaN``).

Nothing outside ``output/`` is written, and no ERA5 data leaves the archive.
