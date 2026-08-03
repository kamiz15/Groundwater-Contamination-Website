"""Unit tests for the workbench's .npz grid intake (datasets.load_npz)."""
from __future__ import annotations

import io
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_analysis import datasets, grids


def _npz_bytes(x, y, values) -> bytes:
    """The archive at_grid_export.grid_npz_bytes writes: 1D axes, 2D values."""
    buffer = io.BytesIO()
    np.savez_compressed(buffer, x_m=x, y_m=y, concentration_mgL=values)
    return buffer.getvalue()


def test_load_npz_round_trips_through_pivot_gridded():
    x = np.arange(4.0)
    y = np.arange(3.0) * 5.0
    values = np.arange(12.0).reshape(3, 4)  # (len(y), len(x))

    df = datasets.load_npz(_npz_bytes(x, y, values))
    assert list(df.columns) == ["x_m", "y_m", "concentration_mgL"]
    grid = grids.pivot_gridded(df, "x_m", "y_m", "concentration_mgL")
    np.testing.assert_allclose(grid.x, x)
    np.testing.assert_allclose(grid.y, y)
    np.testing.assert_allclose(grid.values, values)

    # A grid re-exported by the download button must load back identically.
    regrid = grids.pivot_gridded(
        datasets.load_npz(_npz_bytes(grid.x, grid.y, grid.values)),
        "x_m", "y_m", "concentration_mgL",
    )
    np.testing.assert_allclose(regrid.values, values)


def test_load_npz_shape_mismatch_raises():
    raw = _npz_bytes(np.arange(4.0), np.arange(3.0), np.zeros((4, 3)))
    with pytest.raises(ValueError, match="does not match"):
        datasets.load_npz(raw)


def test_load_npz_missing_key_raises():
    buffer = io.BytesIO()
    np.savez_compressed(buffer, x_m=np.arange(3.0), y_m=np.arange(2.0))
    with pytest.raises(ValueError, match="must contain"):
        datasets.load_npz(buffer.getvalue())


def test_load_npz_garbage_raises_value_error():
    with pytest.raises(ValueError, match="Could not read"):
        datasets.load_npz(b"not an npz archive at all")


def test_load_npz_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        datasets.load_npz(b"")
