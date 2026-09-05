"""
Checks for kohler_model.py against the published numbers.

Run with:  python -m pytest test_kohler_model.py -v
"""

import math

import pytest

from kohler_model import (
    compute_kohler_multiple,
    kohler_lmax,
    kohler_model,
    kohler_tlmax,
)

# Köhler et al. (2024), Table 4 — the two field sites, at both ends of their
# reported parameter ranges. v is not printed in Table 4; 20 m/y (Brand) and
# 26 m/y (Bemidji) are the values that reproduce its published L_max column.
#
#   label, lambda_eff [1/y], v [m/y], gamma [1/y], L_max [m], T_Lmax [y]
FIELD_SITES = [
    ("brand-low",    0.365,  20.0, 0.00033,  462.0,  27.0),
    ("brand-high",   0.730,  20.0, 0.0125,  1850.0,  60.0),
    ("bemidji-low",  0.0185, 26.0, 0.091,   1979.0, 102.0),
    ("bemidji-high", 0.0435, 26.0, 0.182,   1794.0,  90.0),
]


@pytest.mark.parametrize("label,lam,v,gamma,lmax,tlmax", FIELD_SITES)
def test_field_sites_match_table_4(label, lam, v, gamma, lmax, tlmax):
    # Table 4 prints whole metres/years, so 1 unit of tolerance is the
    # rounding of the published value, not slack in the model.
    assert kohler_lmax(lam, v) == pytest.approx(lmax, abs=1.0)
    assert kohler_tlmax(lam, gamma) == pytest.approx(tlmax, abs=1.0)


def test_lmax_shrinks_as_decay_grows_then_turns_back_up():
    """
    L_max falls with lambda_eff only up to a turning point, then rises again.

    This is not a bug: Eq. (13) is a conic section with A4 > 0, so it has a
    minimum in lambda_eff, and for typical velocities that minimum sits INSIDE
    the fitted 0.1–0.45 1/y range. A lambda_eff slider will visibly reverse
    direction there, so the behaviour is pinned rather than assumed away.
    """
    falling = [kohler_lmax(lam, 20.0) for lam in (0.10, 0.20, 0.30, 0.36)]
    assert falling == sorted(falling, reverse=True)

    rising = [kohler_lmax(lam, 20.0) for lam in (0.37, 0.40, 0.45)]
    assert rising == sorted(rising)


def test_lmax_turning_point_in_lambda():
    """The minimum sits where dL/dlambda = A2 + 2*A4*lambda + A6*v = 0."""
    v = 20.0
    vertex = (5808.705 + 85.617 * v) / (2 * 10338.393)
    assert 0.1 < vertex < 0.45  # inside the fitted range, hence reachable
    at_vertex = kohler_lmax(vertex, v)
    assert at_vertex < kohler_lmax(vertex - 0.05, v)
    assert at_vertex < kohler_lmax(vertex + 0.05, v)


def test_lmax_grows_with_velocity():
    """Faster groundwater, longer plume — over the fitted range."""
    lengths = [kohler_lmax(0.2, v) for v in (1.0, 20.0, 40.0, 61.0)]
    assert lengths == sorted(lengths)


def test_model_reports_both_quantities():
    out = kohler_model(0.2, 20.0, 0.5)
    assert out["Lmax"] == kohler_lmax(0.2, 20.0)
    assert out["TLmax"] == kohler_tlmax(0.2, 0.5)
    assert out["warnings"] == []  # every input inside the fitted range


def test_out_of_range_inputs_warn_but_still_compute():
    out = kohler_model(0.73, 20.0, 0.0125)  # Brand: lambda_eff above the range
    assert math.isfinite(out["Lmax"])
    assert any("lambda_eff" in w for w in out["warnings"])


def test_negative_output_is_flagged_not_clipped():
    # A high velocity with almost no decay drives the L_max parabola negative.
    out = kohler_model(0.0, 3000.0, 0.0)
    assert out["Lmax"] < 0
    assert any("negative" in w for w in out["warnings"])


@pytest.mark.parametrize("lam,v", [(-0.1, 20.0), (0.2, 0.0), (0.2, -5.0)])
def test_invalid_inputs_raise(lam, v):
    with pytest.raises(ValueError):
        kohler_lmax(lam, v)


def test_batch_matches_single():
    rows = [(lam, v, g) for _, lam, v, g, _, _ in FIELD_SITES]
    batch = compute_kohler_multiple(rows)
    assert len(batch) == len(rows)
    for row, got in zip(rows, batch):
        assert got == kohler_model(*row)
