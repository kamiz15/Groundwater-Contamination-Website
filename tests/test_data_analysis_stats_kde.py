"""Unit tests for data_analysis.stats and data_analysis.kde."""
from __future__ import annotations

import io
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_analysis import kde, stats


def _sample_frame():
    return pd.DataFrame({
        "a": [1.0, 2.0, 3.0, 4.0, 5.0],
        "b": [2.0, 4.0, 6.0, 8.0, 10.0],
        "label": ["x", "y", "z", "x", "y"],
    })


def test_describe_frame_columns_and_index():
    table = stats.describe_frame(_sample_frame())
    # Only numeric columns are summarised.
    assert list(table.index) == ["a", "b"]
    for col in ("count", "mean", "std", "min", "max", "skew", "kurtosis", "missing"):
        assert col in table.columns


def test_describe_frame_no_numeric_raises():
    df = pd.DataFrame({"label": ["x", "y"]})
    with pytest.raises(ValueError, match="No numeric"):
        stats.describe_frame(df)


def test_stats_csv_round_trips():
    raw = stats.stats_csv_bytes(_sample_frame())
    restored = pd.read_csv(io.BytesIO(raw))
    assert restored.columns[0] == "column"
    assert set(restored["column"]) == {"a", "b"}


def test_qq_lognormal_rejects_non_positive():
    values = np.array([1.0, 2.0, -3.0, 4.0])
    with pytest.raises(ValueError, match="strictly positive"):
        stats.qq_data(values, dist="lognormal")


def test_qq_normal_returns_reference_line():
    rng = np.random.default_rng(1)
    data = stats.qq_data(rng.normal(0, 1, 200), dist="normal")
    assert data.theoretical.shape == data.ordered.shape
    assert 0.9 < data.r <= 1.0


def test_pdf_cdf_data_shapes():
    rng = np.random.default_rng(2)
    data = stats.pdf_cdf_data(np.abs(rng.normal(5, 1, 100)) + 1, dist="lognormal")
    assert data.density.size == data.bin_edges.size - 1
    assert data.pdf_x.shape == data.pdf_y.shape
    assert np.all(data.cdf_y >= 0) and np.all(data.cdf_y <= 1)


def test_kde_density_integrates_to_one():
    rng = np.random.default_rng(3)
    x, y = kde.kde_curve(rng.normal(0, 1, 500), bw="ISJ")
    assert np.all(y >= 0)
    area = np.trapezoid(y, x)
    assert area == pytest.approx(1.0, abs=0.02)


def test_kde_falls_back_on_tiny_sample():
    # ISJ typically fails on 3 points; should silently fall back to silverman.
    x, y = kde.kde_curve(np.array([1.0, 2.0, 3.0]), bw="ISJ")
    assert x.size == 1024
    assert np.all(y >= 0)


def test_kde_rejects_degenerate_input():
    with pytest.raises(ValueError, match="spread"):
        kde.kde_curve(np.array([5.0, 5.0, 5.0, 5.0]))
