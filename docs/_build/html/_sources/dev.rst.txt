Development Guide
=================

This guide covers the repository layout, running the test suite locally, and the licensing and
attribution obligations that come with the code. Reproducing the full data set is covered
separately in :doc:`generate_data`; it needs the ERA5 archive and is not required for
development.

Repository layout
-----------------

::

   run.py                         workflow driver - ALL paths and parameters live here
   worldcupheat/                  importable package
     era5.py                      xarray ERA5 readers (analysis vars + forecast-radiation
                                  de-accumulation)
     wbgt.py                      numba physics: Liljegren WBGT, humidity, solar zenith
     stats.py                     match CSV handling, time zones, percentiles, per-match WBGT
   data/cleaned/
     world_cup_matches_1950-2023.csv   the ONLY input (1,258 matches, 216 stadiums)
   tests/test_wbgt.py             physics pinned to thermofeel 2.2.0 reference values
   docs/                          this documentation

The package is deliberately small: three modules and one linear driver. ``run.py`` owns every
path and tunable parameter, so the modules stay free of configuration and are easy to test in
isolation.

Local setup
-----------

Development only needs the committed match CSV - the physics tests do **not** touch ERA5 or the
GLADE/GDEX archive, so they run anywhere (including CI). Install with the ``dev`` extra, which
adds pytest, ruff, and Sphinx:

.. code-block:: bash

   uv sync --group dev        # with uv (recommended)
   # or
   pip install -e ".[dev]"

Testing and linting
--------------------

.. code-block:: bash

   uv run pytest              # physics reference values; no ERA5/GLADE access needed
   uv run ruff check .        # lint (line length 100; rules E, F, I, W)

``tests/test_wbgt.py`` pins the numba WBGT port to reference values from thermofeel 2.2.0
(max \|Δ\| < 0.1 K over a 2,000-point sweep). Both commands run on every push and pull request
via the GitHub Actions workflow in ``.github/workflows/ci.yml``.

A container image is also provided for a reproducible test environment:

.. code-block:: bash

   docker build -t worldcupheat .
   docker run --rm worldcupheat        # runs `pytest -v tests/`

Building the documentation
--------------------------

The docs are built with `Sphinx <https://www.sphinx-doc.org/>`_ (installed by the ``dev``
extra):

.. code-block:: bash

   cd docs
   make html                  # output in docs/_build/html
   # or, for a live-reloading preview:
   sphinx-autobuild . _build/html

Licensing and attribution
-------------------------

The WBGT physics in ``worldcupheat/wbgt.py`` (property functions, energy-balance solvers,
wind-profile scaling, and the KNMI operational guards) is transcribed from
`thermofeel 2.2.0 <https://github.com/ecmwf/thermofeel>`_, which is

   Copyright 2021 European Centre for Medium-Range Weather Forecasts (ECMWF), released under the
   `Apache License 2.0 <https://www.apache.org/licenses/LICENSE-2.0>`_.

The Apache-2.0 license requires that the copyright notice and license text be preserved when the
code is redistributed. Any distribution of this project must therefore retain that attribution.

.. note::

   The repository does not yet carry a top-level ``LICENSE`` file or a ``license`` field in
   ``pyproject.toml``. Add both - including a copy of the Apache-2.0 terms covering the ported
   thermofeel physics - before publishing or releasing, so the project's own license and the
   upstream obligation are unambiguous.

Scientific references
---------------------

* Liljegren, J. C., et al. (2008). *Modeling the Wet Bulb Globe Temperature Using Standard
  Meteorological Measurements.* https://doi.org/10.1080/15459620802310770
* Kong, Q., & Huber, M. (2022). *Explicit calculations of Wet-Bulb Globe Temperature compared
  with approximations and why it matters for labor productivity.*
  https://doi.org/10.1029/2021EF002334
* Buck, A. L. (1981/1996). Saturation vapour pressure over water.
* Spencer, J. W. (1971). Fourier-series representation of the position of the Sun.
