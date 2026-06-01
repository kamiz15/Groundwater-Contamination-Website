"""
source_geometry.py — Regular source-shape discretisation for forward modelling.

Converts a circle, ellipse, or line source description into a set of
representative source points, then maps those points to the existing
analytical model pipeline (Liedl effective-source-width parameter M).

OUT OF SCOPE — TODO stubs only:
  - Irregular / hand-drawn polygon shapes
  - Automatic circle-fill of arbitrary regions
  - Multi-source superposition
  - 3-D source volumes
"""
from __future__ import annotations

import math
from typing import Literal, NamedTuple


# ── Size → point-count thresholds ─────────────────────────────────────────────
# "size" for circles / ellipses = largest semi-axis (radius or max(semi_a, semi_b)).
# "size" for lines             = Euclidean segment length.
#
# Each tuple is (upper_bound_exclusive, n_points).  The last entry has
# upper_bound = None (catch-all for any size >= the previous bound).
#
# The minimum across all shapes is 4 points, placed at the geometric extremes:
#   one downstream (right), one upstream (left), two lateral (top / bottom).

CIRCLE_ELLIPSE_THRESHOLDS: tuple[tuple[float | None, int], ...] = (
    (5.0,   4),   # size <  5 m  → 4 points  (geometric extremes only)
    (20.0,  8),   # 5  ≤ size < 20 m → 8 points
    (50.0, 12),   # 20 ≤ size < 50 m → 12 points
    (None, 20),   # size ≥ 50 m      → 20 points
)

LINE_THRESHOLDS: tuple[tuple[float | None, int], ...] = (
    (10.0,   4),  # length <  10 m  →  4 points (2 endpoints + 2 interior)
    (30.0,   6),  # 10  ≤ length <  30 m →  6 points
    (100.0, 10),  # 30  ≤ length < 100 m → 10 points
    (None,  16),  # length ≥ 100 m       → 16 points
)


class SourcePoint(NamedTuple):
    x: float
    y: float


# ── Internal helpers ───────────────────────────────────────────────────────────

def _count_from_thresholds(
    size: float,
    thresholds: tuple[tuple[float | None, int], ...],
) -> int:
    for upper, n in thresholds:
        if upper is None or size < upper:
            return n
    return thresholds[-1][1]


# ── Auto point-count API ───────────────────────────────────────────────────────

def auto_point_count_circle(radius: float) -> int:
    """Return the automatic point count for a circle of the given radius."""
    return _count_from_thresholds(radius, CIRCLE_ELLIPSE_THRESHOLDS)


def auto_point_count_ellipse(semi_a: float, semi_b: float) -> int:
    """Return the automatic point count for an ellipse; size = max semi-axis."""
    return _count_from_thresholds(max(semi_a, semi_b), CIRCLE_ELLIPSE_THRESHOLDS)


def auto_point_count_line(x1: float, y1: float, x2: float, y2: float) -> int:
    """Return the automatic point count for a line segment."""
    return _count_from_thresholds(math.hypot(x2 - x1, y2 - y1), LINE_THRESHOLDS)


# ── Point-fitting functions ────────────────────────────────────────────────────

def fit_points_circle(
    cx: float,
    cy: float,
    radius: float,
    n_points: int,
) -> list[SourcePoint]:
    """
    Place n_points evenly around a circle's circumference.

    For n_points = 4 the angles are 0°, 90°, 180°, 270°, placing one point
    at each geometric extreme:
      index 0 — downstream (right,  angle = 0°)
      index 1 — lateral-top         (angle = 90°)
      index 2 — upstream  (left,    angle = 180°)
      index 3 — lateral-bottom      (angle = 270°)
    For larger n the spacing is uniform and the 0° anchor is preserved.
    """
    if n_points < 4:
        raise ValueError("n_points must be >= 4")
    if radius <= 0:
        raise ValueError("radius must be positive")
    return [
        SourcePoint(
            cx + radius * math.cos(2 * math.pi * i / n_points),
            cy + radius * math.sin(2 * math.pi * i / n_points),
        )
        for i in range(n_points)
    ]


def fit_points_ellipse(
    cx: float,
    cy: float,
    semi_a: float,
    semi_b: float,
    angle_deg: float,
    n_points: int,
) -> list[SourcePoint]:
    """
    Place n_points evenly (by parametric angle) on an ellipse.

    semi_a     : semi-axis in the local x direction (along flow when angle_deg=0).
    semi_b     : semi-axis in the local y direction (transverse when angle_deg=0).
    angle_deg  : counter-clockwise rotation of the major axis from the x-axis.

    For n_points = 4 the four parametric extremes at t = 0°, 90°, 180°, 270°
    map to the downstream, top, upstream, and bottom extremes of the ellipse.
    """
    if n_points < 4:
        raise ValueError("n_points must be >= 4")
    if semi_a <= 0 or semi_b <= 0:
        raise ValueError("semi-axes must be positive")
    cos_a = math.cos(math.radians(angle_deg))
    sin_a = math.sin(math.radians(angle_deg))
    points = []
    for i in range(n_points):
        t = 2 * math.pi * i / n_points
        lx = semi_a * math.cos(t)
        ly = semi_b * math.sin(t)
        points.append(SourcePoint(
            cx + cos_a * lx - sin_a * ly,
            cy + sin_a * lx + cos_a * ly,
        ))
    return points


def fit_points_line(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    n_points: int,
) -> list[SourcePoint]:
    """
    Place n_points evenly along a line segment; endpoints always included.

    For n_points = 4 the four points are at t = 0, 1/3, 2/3, 1.
    n_points must be >= 2.
    """
    if n_points < 2:
        raise ValueError("n_points must be >= 2 for a line")
    return [
        SourcePoint(
            x1 + (i / (n_points - 1)) * (x2 - x1),
            y1 + (i / (n_points - 1)) * (y2 - y1),
        )
        for i in range(n_points)
    ]


# ── Geometry → physics mapping ─────────────────────────────────────────────────

def effective_source_width(
    shape: Literal["circle", "ellipse", "line"],
    **kwargs: float,
) -> float:
    """
    Derive the effective transverse source width W [m] for the Liedl / Chu
    forward models (used as the M or W parameter, respectively).

    circle  : W = 2 * radius        (full diameter = transverse extent)
    ellipse : W = 2 * semi_b        (minor/transverse semi-axis)
    line    : W = |y2 - y1|         (transverse projection of the segment);
              falls back to the full Euclidean length when the line is
              axis-aligned along x (i.e. horizontal, parallel to flow).
    """
    if shape == "circle":
        return 2.0 * float(kwargs["radius"])
    if shape == "ellipse":
        return 2.0 * float(kwargs["semi_b"])
    if shape == "line":
        dy = abs(float(kwargs["y2"]) - float(kwargs["y1"]))
        if dy > 1e-9:
            return dy
        return math.hypot(float(kwargs["x2"]) - float(kwargs["x1"]), dy)
    raise ValueError(f"Unknown shape: {shape!r}")


# ── TODO stubs for out-of-scope features ──────────────────────────────────────

def fit_points_irregular(*args, **kwargs):  # pragma: no cover
    """TODO: irregular / hand-drawn polygon source (out of scope for MVP)."""
    raise NotImplementedError("Irregular shapes are not yet supported.")


def fit_points_multi_source(*args, **kwargs):  # pragma: no cover
    """TODO: multi-source superposition (out of scope for MVP)."""
    raise NotImplementedError("Multi-source modelling is not yet supported.")


def fit_points_3d(*args, **kwargs):  # pragma: no cover
    """TODO: 3-D source volumes (out of scope for MVP)."""
    raise NotImplementedError("3-D source geometry is not yet supported.")
