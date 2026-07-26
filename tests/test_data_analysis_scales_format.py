"""Unit tests for data_analysis.scales and data_analysis.formatting."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_analysis import formatting, scales


# ── scales ────────────────────────────────────────────────────────────────────

def test_linear_is_identity():
    values = np.array([-2.0, 0.0, 3.5])
    np.testing.assert_allclose(scales.transform(values, "linear"), values)


@pytest.mark.parametrize("scale,expected", [
    ("ln", np.log([1.0, 10.0, 100.0])),
    ("log10", [0.0, 1.0, 2.0]),
    ("inverse", [1.0, 0.1, 0.01]),
])
def test_transforms(scale, expected):
    got = scales.transform(np.array([1.0, 10.0, 100.0]), scale)
    np.testing.assert_allclose(got, expected)


@pytest.mark.parametrize("scale", ["ln", "log10", "inverse"])
def test_non_positive_raises_with_column_name(scale):
    with pytest.raises(ValueError, match="strictly positive"):
        scales.transform(np.array([1.0, -1.0]), scale, name="conc")


def test_zero_also_rejected():
    with pytest.raises(ValueError, match="strictly positive"):
        scales.transform(np.array([0.0, 1.0]), "log10")


def test_transform_lenient_blanks_instead_of_raising():
    got = scales.transform_lenient(np.array([-1.0, 1.0, 10.0]), "log10")
    assert np.isnan(got[0])
    np.testing.assert_allclose(got[1:], [0.0, 1.0])


def test_axis_labels_are_typeset():
    # axis_label delegates to notation, so it returns LaTeX for Bokeh.
    assert scales.axis_label("conc", "linear") == "$$C_{c}$$"
    assert r"\ln" in scales.axis_label("conc", "ln")
    assert scales.axis_label("conc", "inverse") == "$$1/C_{c}$$"


def test_plain_axis_labels_for_legends():
    assert scales.plain_axis_label("conc", "linear") == "Cc"
    assert scales.plain_axis_label("plume_length_m", "linear") == "L\u209a [m]"


def test_unknown_scale_raises():
    with pytest.raises(ValueError, match="Unknown scale"):
        scales.transform(np.array([1.0]), "sqrt")


# ── formatting ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (12.3456, "12.35"),
    (0.5, "0.50"),
    (0.0, "0.00"),
    (-3.14159, "-3.14"),
])
def test_fmt_fixed_range(value, expected):
    assert formatting.fmt(value) == expected


@pytest.mark.parametrize("value", [1.23e-05, 1.23e08])
def test_fmt_switches_to_scientific(value):
    out = formatting.fmt(value)
    assert "e" in out
    # Two decimals in the mantissa either way.
    assert out.split("e")[0].split(".")[1] == "23"


def test_fmt_handles_nan_and_non_numeric():
    assert formatting.fmt(float("nan")) == "n/a"
    assert formatting.fmt("abc") == "abc"


def test_needs_scientific_detection():
    assert formatting.needs_scientific([1e-6, 2e-6]) is True
    assert formatting.needs_scientific([1.0, 50.0]) is False
    # Zeros are ignored rather than forcing scientific notation.
    assert formatting.needs_scientific([0.0, 1.0]) is False


def test_tick_pattern_matches_magnitude():
    assert formatting.tick_pattern([1.0, 20.0]) == formatting.FIXED_PATTERN
    assert formatting.tick_pattern([1e-9]) == formatting.SCIENTIFIC_PATTERN


def test_format_frame_only_touches_numeric():
    df = pd.DataFrame({"a": [1.23456, 2.0], "label": ["x", "y"]})
    out = formatting.format_frame(df)
    assert list(out["a"]) == ["1.23", "2.00"]
    assert list(out["label"]) == ["x", "y"]
