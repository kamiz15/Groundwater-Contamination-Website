"""
Unit tests for source_geometry.py.

Verification gate (per task spec):
  - Small circle  → exactly 4 points at geometric extremes; assert coordinates.
  - Large circle  → more points (threshold-driven count); assert count.
  - Line          → endpoints + interior points per count; assert coordinates.
"""
from __future__ import annotations

import math
import sys
import os

import pytest

# Make project root importable when running from any directory.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from source_geometry import (
    CIRCLE_ELLIPSE_THRESHOLDS,
    LINE_THRESHOLDS,
    auto_point_count_circle,
    auto_point_count_ellipse,
    auto_point_count_line,
    effective_source_width,
    fit_points_circle,
    fit_points_ellipse,
    fit_points_line,
)


# ── Auto point-count thresholds ────────────────────────────────────────────────

class TestAutoPointCount:
    def test_circle_below_first_threshold_gives_minimum(self):
        # 3 < 5 → 4 (minimum, geometric extremes only)
        assert auto_point_count_circle(3.0) == 4

    def test_circle_at_first_threshold_boundary(self):
        # 5 is NOT below 5, so it falls into the [5, 20) bucket
        assert auto_point_count_circle(5.0) == 8

    def test_circle_mid_range(self):
        assert auto_point_count_circle(10.0) == 8   # 5 ≤ 10 < 20

    def test_circle_large(self):
        assert auto_point_count_circle(30.0) == 12  # 20 ≤ 30 < 50

    def test_circle_very_large(self):
        assert auto_point_count_circle(100.0) == 20  # ≥ 50

    def test_circle_at_second_threshold_boundary(self):
        assert auto_point_count_circle(20.0) == 12  # 20 is NOT below 20

    def test_ellipse_uses_largest_semi_axis(self):
        # max(3, 1) = 3 < 5 → 4
        assert auto_point_count_ellipse(3.0, 1.0) == 4
        # max(1, 10) = 10, 5 ≤ 10 < 20 → 8
        assert auto_point_count_ellipse(1.0, 10.0) == 8
        # max(25, 5) = 25, 20 ≤ 25 < 50 → 12
        assert auto_point_count_ellipse(25.0, 5.0) == 12

    def test_line_short(self):
        # length = 5 < 10 → 4
        assert auto_point_count_line(0, 0, 5, 0) == 4

    def test_line_at_first_threshold(self):
        assert auto_point_count_line(0, 0, 10, 0) == 6  # 10 is NOT below 10

    def test_line_medium(self):
        assert auto_point_count_line(0, 0, 20, 0) == 6   # 10 ≤ 20 < 30

    def test_line_long(self):
        assert auto_point_count_line(0, 0, 50, 0) == 10  # 30 ≤ 50 < 100

    def test_line_very_long(self):
        assert auto_point_count_line(0, 0, 200, 0) == 16  # ≥ 100

    def test_line_diagonal_uses_euclidean_length(self):
        # hypot(3, 4) = 5 → still < 10 → 4
        assert auto_point_count_line(0, 0, 3, 4) == 4
        # hypot(6, 8) = 10 → NOT below 10 → 6
        assert auto_point_count_line(0, 0, 6, 8) == 6


# ── fit_points_circle ──────────────────────────────────────────────────────────

class TestFitPointsCircle:
    """Verification gate: small circle → exactly 4 extremes with asserted coords."""

    def test_small_circle_yields_exactly_four_extremes(self):
        """
        Circle with radius 3 m (< 5 m threshold) → auto count = 4.
        Four geometric extremes:
          index 0  downstream   (right)   angle = 0°   → (cx+r, cy)
          index 1  lateral-top            angle = 90°  → (cx,   cy+r)
          index 2  upstream     (left)    angle = 180° → (cx-r, cy)
          index 3  lateral-bot            angle = 270° → (cx,   cy-r)
        """
        r = 3.0
        assert auto_point_count_circle(r) == 4, "Pre-condition: small radius should give 4 auto points"

        pts = fit_points_circle(0, 0, r, 4)

        assert len(pts) == 4

        # downstream (angle = 0)
        assert pts[0].x == pytest.approx(3.0)
        assert pts[0].y == pytest.approx(0.0, abs=1e-12)

        # lateral top (angle = 90°)
        assert pts[1].x == pytest.approx(0.0, abs=1e-12)
        assert pts[1].y == pytest.approx(3.0)

        # upstream (angle = 180°)
        assert pts[2].x == pytest.approx(-3.0)
        assert pts[2].y == pytest.approx(0.0, abs=1e-12)

        # lateral bottom (angle = 270°)
        assert pts[3].x == pytest.approx(0.0, abs=1e-12)
        assert pts[3].y == pytest.approx(-3.0)

    def test_small_circle_with_nonzero_centre(self):
        """Centre offset must shift every point by (cx, cy)."""
        pts = fit_points_circle(10.0, 5.0, 3.0, 4)
        assert pts[0].x == pytest.approx(13.0)   # downstream
        assert pts[0].y == pytest.approx(5.0, abs=1e-12)
        assert pts[2].x == pytest.approx(7.0)    # upstream
        assert pts[2].y == pytest.approx(5.0, abs=1e-12)

    def test_large_circle_yields_more_points(self):
        """
        Verification gate: large circle (r = 25 m, 20 ≤ 25 < 50) → auto count = 12.
        """
        r = 25.0
        n = auto_point_count_circle(r)
        assert n == 12, f"Expected 12 points for r={r}, got {n}"

        pts = fit_points_circle(0, 0, r, n)
        assert len(pts) == 12

    def test_very_large_circle_yields_20_points(self):
        r = 75.0
        n = auto_point_count_circle(r)
        assert n == 20
        pts = fit_points_circle(0, 0, r, n)
        assert len(pts) == 20

    def test_all_points_lie_on_circumference(self):
        """Every fitted point must be exactly radius away from the centre."""
        cx, cy, r = 1.5, -2.3, 7.0
        pts = fit_points_circle(cx, cy, r, 20)
        for pt in pts:
            dist = math.hypot(pt.x - cx, pt.y - cy)
            assert dist == pytest.approx(r, abs=1e-9)

    def test_requires_four_or_more_points(self):
        with pytest.raises(ValueError, match="n_points must be >= 4"):
            fit_points_circle(0, 0, 5.0, 3)

    def test_requires_positive_radius(self):
        with pytest.raises(ValueError):
            fit_points_circle(0, 0, 0.0, 4)
        with pytest.raises(ValueError):
            fit_points_circle(0, 0, -1.0, 4)


# ── fit_points_ellipse ─────────────────────────────────────────────────────────

class TestFitPointsEllipse:
    def test_four_extremes_no_rotation(self):
        """With angle_deg=0 the four points are at the axis tips."""
        pts = fit_points_ellipse(0, 0, 6.0, 3.0, 0.0, 4)
        assert len(pts) == 4
        # t=0°: (semi_a, 0)
        assert pts[0].x == pytest.approx(6.0)
        assert pts[0].y == pytest.approx(0.0, abs=1e-12)
        # t=90°: (0, semi_b)
        assert pts[1].x == pytest.approx(0.0, abs=1e-12)
        assert pts[1].y == pytest.approx(3.0)
        # t=180°: (-semi_a, 0)
        assert pts[2].x == pytest.approx(-6.0)
        assert pts[2].y == pytest.approx(0.0, abs=1e-12)
        # t=270°: (0, -semi_b)
        assert pts[3].x == pytest.approx(0.0, abs=1e-12)
        assert pts[3].y == pytest.approx(-3.0)

    def test_all_points_satisfy_ellipse_equation(self):
        """x²/a² + y²/b² = 1 for all points when angle_deg=0."""
        a, b = 8.0, 4.0
        pts = fit_points_ellipse(0, 0, a, b, 0.0, 12)
        for pt in pts:
            assert (pt.x / a) ** 2 + (pt.y / b) ** 2 == pytest.approx(1.0, abs=1e-9)

    def test_90_degree_rotation_swaps_axes(self):
        """Rotating 90° CCW should move the first point from (a,0) to (0,a)."""
        pts_90 = fit_points_ellipse(0, 0, 6.0, 3.0, 90.0, 4)
        # t=0, angle=90°: gx = cos90·6 - sin90·0 = 0, gy = sin90·6 + cos90·0 = 6
        assert pts_90[0].x == pytest.approx(0.0, abs=1e-12)
        assert pts_90[0].y == pytest.approx(6.0)

    def test_invalid_args_raise(self):
        with pytest.raises(ValueError, match="n_points must be >= 4"):
            fit_points_ellipse(0, 0, 5, 3, 0, 3)
        with pytest.raises(ValueError, match="semi-axes must be positive"):
            fit_points_ellipse(0, 0, 0, 3, 0, 4)


# ── fit_points_line ────────────────────────────────────────────────────────────

class TestFitPointsLine:
    """Verification gate: line → endpoints + interior points with asserted coords."""

    def test_four_points_positions(self):
        """
        Verification gate: a horizontal 30 m line with n=4 yields points at
        x = 0, 10, 20, 30 m (t = 0, 1/3, 2/3, 1).
        """
        pts = fit_points_line(0.0, 0.0, 30.0, 0.0, 4)
        assert len(pts) == 4

        assert pts[0].x == pytest.approx(0.0)
        assert pts[0].y == pytest.approx(0.0)

        assert pts[1].x == pytest.approx(10.0)   # 30 × 1/3
        assert pts[1].y == pytest.approx(0.0, abs=1e-12)

        assert pts[2].x == pytest.approx(20.0)   # 30 × 2/3
        assert pts[2].y == pytest.approx(0.0, abs=1e-12)

        assert pts[3].x == pytest.approx(30.0)
        assert pts[3].y == pytest.approx(0.0, abs=1e-12)

    def test_endpoints_always_included(self):
        """First and last points must equal the supplied endpoints."""
        for n in (2, 4, 6, 10):
            pts = fit_points_line(1.0, 2.0, 11.0, 7.0, n)
            assert pts[0].x == pytest.approx(1.0)
            assert pts[0].y == pytest.approx(2.0)
            assert pts[-1].x == pytest.approx(11.0)
            assert pts[-1].y == pytest.approx(7.0)

    def test_auto_count_medium_line_gives_six_points(self):
        """
        Verification gate: a 20 m line (10 ≤ 20 < 30) → auto count = 6.
        """
        n = auto_point_count_line(0, 0, 20, 0)
        assert n == 6, f"Expected 6 for 20 m line, got {n}"
        pts = fit_points_line(0, 0, 20, 0, n)
        assert len(pts) == 6
        # Points at t = 0, 0.2, 0.4, 0.6, 0.8, 1.0 → x = 0, 4, 8, 12, 16, 20
        expected_x = [0.0, 4.0, 8.0, 12.0, 16.0, 20.0]
        for pt, ex in zip(pts, expected_x):
            assert pt.x == pytest.approx(ex, abs=1e-10)

    def test_all_points_collinear(self):
        """All fitted points must lie on the segment (satisfy the line equation)."""
        x1, y1, x2, y2 = 0.0, 0.0, 10.0, 5.0
        slope = (y2 - y1) / (x2 - x1)
        pts = fit_points_line(x1, y1, x2, y2, 10)
        for pt in pts:
            assert pt.y == pytest.approx(slope * pt.x, abs=1e-10)

    def test_requires_two_or_more_points(self):
        with pytest.raises(ValueError, match="n_points must be >= 2"):
            fit_points_line(0, 0, 10, 0, 1)


# ── effective_source_width ─────────────────────────────────────────────────────

class TestEffectiveSourceWidth:
    def test_circle_width_is_diameter(self):
        assert effective_source_width("circle", radius=5.0) == pytest.approx(10.0)

    def test_circle_width_scales_with_radius(self):
        assert effective_source_width("circle", radius=7.5) == pytest.approx(15.0)

    def test_ellipse_width_is_twice_semi_b(self):
        assert effective_source_width("ellipse", semi_b=3.0) == pytest.approx(6.0)

    def test_line_transverse_projection(self):
        # y1=0, y2=10 → dy = 10
        w = effective_source_width("line", x1=0.0, y1=0.0, x2=20.0, y2=10.0)
        assert w == pytest.approx(10.0)

    def test_line_horizontal_falls_back_to_full_length(self):
        # y1 = y2 = 0 → horizontal line → fall back to Euclidean length = 20
        w = effective_source_width("line", x1=0.0, y1=0.0, x2=20.0, y2=0.0)
        assert w == pytest.approx(20.0)

    def test_line_vertical_equals_dy(self):
        # x1 = x2 → purely transverse → dy = 15
        w = effective_source_width("line", x1=5.0, y1=0.0, x2=5.0, y2=15.0)
        assert w == pytest.approx(15.0)

    def test_unknown_shape_raises(self):
        with pytest.raises(ValueError, match="Unknown shape"):
            effective_source_width("polygon", radius=5.0)
