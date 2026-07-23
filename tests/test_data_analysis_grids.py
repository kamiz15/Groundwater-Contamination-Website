"""Unit tests for data_analysis.grids and data_analysis.datasets."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_analysis import datasets, grids


def test_pivot_gridded_round_trip():
    xs = np.arange(4.0)
    ys = np.arange(3.0)
    XX, YY = np.meshgrid(xs, ys)
    values = XX + 10.0 * YY
    long = pd.DataFrame({"x": XX.ravel(), "y": YY.ravel(), "v": values.ravel()})
    grid = grids.pivot_gridded(long, "x", "y", "v")
    assert grid.values.shape == (3, 4)  # (len(y), len(x))
    np.testing.assert_allclose(grid.values, values)
    np.testing.assert_allclose(grid.x, xs)
    np.testing.assert_allclose(grid.y, ys)


def test_pivot_gridded_irregular_axis_raises():
    bad = pd.DataFrame({
        "x": [0, 1, 3, 0, 1, 3],  # gap between 1 and 3
        "y": [0, 0, 0, 1, 1, 1],
        "v": [1, 2, 3, 4, 5, 6],
    })
    with pytest.raises(ValueError, match="evenly spaced"):
        grids.pivot_gridded(bad, "x", "y", "v")


def test_pivot_gridded_holes_raise():
    # Missing the (1, 1) cell leaves a NaN hole after pivoting.
    holed = pd.DataFrame({
        "x": [0, 1, 0, 1],
        "y": [0, 0, 1, 1],
        "v": [1, 2, 3, 4],
    }).drop(index=3)
    with pytest.raises(ValueError, match="missing cells"):
        grids.pivot_gridded(holed, "x", "y", "v")


def test_pivot_gridded_same_column_raises():
    df = pd.DataFrame({"x": [0, 1], "v": [1, 2]})
    with pytest.raises(ValueError, match="three different"):
        grids.pivot_gridded(df, "x", "x", "v")


@dataclass
class _FakeVertical:
    concentration: np.ndarray
    x_grid: np.ndarray
    z_grid: np.ndarray


def test_long_form_from_result_orientation():
    x = np.array([0.0, 1.0, 2.0, 3.0])   # 4 columns
    z = np.array([0.0, 5.0, 10.0])       # 3 rows
    # concentration must be (len(z), len(x)) = (3, 4)
    conc = np.arange(12.0).reshape(3, 4)
    result = _FakeVertical(concentration=conc, x_grid=x, z_grid=z)
    long = grids.long_form_from_result(result)
    assert set(long.columns) == {"x_m", "z_m", "concentration_mg_L"}
    assert len(long) == 12
    # Re-pivoting must reproduce the original grid.
    regrid = grids.pivot_gridded(long, "x_m", "z_m", "concentration_mg_L")
    np.testing.assert_allclose(regrid.values, conc)


def test_long_form_from_result_shape_mismatch_raises():
    result = _FakeVertical(
        concentration=np.zeros((2, 2)),
        x_grid=np.array([0.0, 1.0, 2.0]),
        z_grid=np.array([0.0, 1.0]),
    )
    with pytest.raises(ValueError, match="do not match"):
        grids.long_form_from_result(result)


def test_long_form_from_aem_result_uses_orientation_labels():
    result = SimpleNamespace(
        result=np.arange(6.0).reshape(2, 3),
        xaxis=np.array([0.0, 1.0, 2.0]),
        yaxis=np.array([-1.0, 0.0]),
        orientation="vertical",
    )

    long = grids.long_form_from_aem_result(result)

    assert list(long.columns) == ["x [m]", "z [m]", "concentration [mg/L]"]
    assert len(long) == 6
    regrid = grids.pivot_gridded(
        long, "x [m]", "z [m]", "concentration [mg/L]"
    )
    np.testing.assert_allclose(regrid.values, result.result)


def test_long_form_from_aem_result_rejects_shape_mismatch():
    result = SimpleNamespace(
        result=np.zeros((2, 2)),
        xaxis=np.array([0.0, 1.0, 2.0]),
        yaxis=np.array([0.0, 1.0]),
        orientation="horizontal",
    )
    with pytest.raises(ValueError, match="dimensions do not match"):
        grids.long_form_from_aem_result(result)


def test_gradient_vectors_keys():
    xs = np.arange(6.0)
    ys = np.arange(5.0)
    XX, YY = np.meshgrid(xs, ys)
    values = 100.0 * np.exp(-((XX - 2) ** 2 + (YY - 2) ** 2) / 5.0)
    long = pd.DataFrame({"x": XX.ravel(), "y": YY.ravel(), "v": values.ravel()})
    grid = grids.pivot_gridded(long, "x", "y", "v")
    vectors = grids.gradient_vectors(grid)
    assert set(vectors) == {"x0", "y0", "x1", "y1", "angle", "magnitude"}


def test_load_csv_and_typing():
    raw = b"a,b,label\n1,2.5,x\n3,4.5,y\n"
    df = datasets.load_csv(raw)
    assert list(df.columns) == ["a", "b", "label"]
    assert datasets.numeric_columns(df) == ["a", "b"]
    assert datasets.categorical_columns(df) == ["label"]


def test_load_csv_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        datasets.load_csv(b"")


def test_load_csv_header_only_raises():
    with pytest.raises(ValueError, match="no data rows"):
        datasets.load_csv(b"a,b,c\n")
