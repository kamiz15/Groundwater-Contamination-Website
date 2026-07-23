"""Unit tests for data_analysis.fits — coefficient recovery, R2, CI bands, errors."""
from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_analysis.fits import fit_curve


def test_linear_recovers_coefficients():
    x = np.linspace(0, 10, 50)
    y = 3.0 * x + 2.0
    fit = fit_curve(x, y, "linear")
    assert fit.params["c1"] == pytest.approx(3.0, abs=1e-6)
    assert fit.params["c0"] == pytest.approx(2.0, abs=1e-6)
    assert fit.r2 == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("degree", [2, 3, 4])
def test_polynomial_recovers_and_fits(degree):
    x = np.linspace(-3, 3, 60)
    coeffs = np.array([0.5, -1.0, 0.25, 2.0, -0.5][: degree + 1])
    y = np.polyval(coeffs, x)
    fit = fit_curve(x, y, f"polynomial-{degree}")
    assert fit.r2 == pytest.approx(1.0, abs=1e-6)
    np.testing.assert_allclose(list(fit.params.values()), coeffs, atol=1e-6)


def test_exponential_recovers_parameters():
    x = np.linspace(0, 4, 40)
    y = 2.0 * np.exp(0.7 * x)
    fit = fit_curve(x, y, "exponential")
    assert fit.params["a"] == pytest.approx(2.0, rel=1e-4)
    assert fit.params["b"] == pytest.approx(0.7, rel=1e-4)
    assert fit.r2 == pytest.approx(1.0, abs=1e-6)


def test_logarithmic_recovers_parameters():
    x = np.linspace(1, 20, 40)
    y = 1.5 + 2.0 * np.log(x)
    fit = fit_curve(x, y, "logarithmic")
    assert fit.params["a"] == pytest.approx(1.5, abs=1e-6)
    assert fit.params["b"] == pytest.approx(2.0, abs=1e-6)
    assert fit.r2 == pytest.approx(1.0, abs=1e-9)


def test_confidence_band_widens_away_from_center():
    rng = np.random.default_rng(0)
    x = np.linspace(0, 10, 40)
    y = 2.0 * x + 1.0 + rng.normal(0, 1.0, x.size)
    fit = fit_curve(x, y, "linear", with_band=True)
    assert fit.band is not None
    lower, upper = fit.band
    width = upper - lower
    center = np.argmin(np.abs(fit.x_grid - np.mean(x)))
    # Band is narrowest near the mean of x, wider at the extremes.
    assert width[0] > width[center]
    assert width[-1] > width[center]


def test_log_fit_rejects_non_positive_x():
    x = np.linspace(-1, 5, 20)
    y = np.ones_like(x)
    with pytest.raises(ValueError, match="strictly positive"):
        fit_curve(x, y, "logarithmic")


def test_too_few_points_raises():
    x = np.array([1.0, 2.0])
    y = np.array([1.0, 2.0])
    with pytest.raises(ValueError, match="at least"):
        fit_curve(x, y, "linear")


def test_nan_pairs_dropped():
    x = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0])
    y = np.array([2.0, 4.0, 5.0, np.nan, 10.0, 12.0])
    fit = fit_curve(x, y, "linear")
    assert fit.n == 4  # two pairs dropped
    assert fit.params["c1"] == pytest.approx(2.0, abs=1e-6)


def test_unknown_fit_type_raises():
    x = np.linspace(0, 5, 10)
    with pytest.raises(ValueError, match="Unknown fit type"):
        fit_curve(x, x, "cubic-spline")
