"""Data-analysis helpers for the visual analysis workbench.

Pure numpy/pandas/scipy (and optionally KDEpy) logic, kept separate from the
Panel UI so it can be unit-tested in isolation.
"""
from __future__ import annotations

from . import datasets, fits, formatting, grids, kde, scales, stats

# ``plots`` pulls in Bokeh and ``modflow`` needs flopy only when actually used;
# both are imported lazily by callers to keep this package light to import.
__all__ = [
    "datasets", "fits", "formatting", "grids", "kde", "scales", "stats",
    "plots", "modflow",
]
