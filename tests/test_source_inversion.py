"""
tests/test_source_inversion.py

Verification gate (per task spec):
  Synthetic round-trip: take known source params → generate signals with the
  forward model → invert → assert recovered params are within tolerance.

Run with:  pytest tests/test_source_inversion.py -v
"""
from __future__ import annotations

import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from analytical_models import liedl_lmax
from source_inversion import Signal, InversionResult, invert_alpha_tv


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_exact_signals(
    alpha_tv_true: float,
    M_values: list[float],
    gamma: float = 3.5,
    Ca: float = 8.0,
    Cd: float = 5.0,
) -> list[Signal]:
    """Generate noiseless signals from known alpha_Tv (synthetic forward pass)."""
    return [
        Signal(
            M=M,
            L_max_obs=liedl_lmax(M, alpha_tv_true, gamma, Ca, Cd),
            gamma=gamma,
            Ca=Ca,
            Cd=Cd,
        )
        for M in M_values
    ]


def _make_noisy_signals(
    alpha_tv_true: float,
    M_values: list[float],
    noise_fractions: list[float],
    gamma: float = 3.5,
    Ca: float = 8.0,
    Cd: float = 5.0,
) -> list[Signal]:
    """Generate noisy signals; noise_fraction is additive fraction of L_max."""
    return [
        Signal(
            M=M,
            L_max_obs=liedl_lmax(M, alpha_tv_true, gamma, Ca, Cd) * (1.0 + noise),
            gamma=gamma,
            Ca=Ca,
            Cd=Cd,
        )
        for M, noise in zip(M_values, noise_fractions)
    ]


# ═══════════════════════════════════════════════════════════════════════════════
# VERIFICATION GATE — synthetic round-trip
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoundTripExact:
    """
    Noiseless synthetic round-trip.

    Forward pass:  known alpha_Tv → 4 exact L_max observations
    Inverse pass:  inversion starting from wrong part of parameter space
    Assert:        recovered alpha_Tv within 0.01 % of truth
    """

    def test_nominal_alpha_tv(self):
        """
        Verification gate (primary): alpha_Tv = 0.001 m, 4 signals.

        Signal table:
          M = [2, 4, 6, 8] m → L_max = [2270.9, 9083.6, 20438.0, 36334.3] m
        Initial bounds: [1e-6, 1.0] m  (truth is interior, not near either end)
        Recovered alpha_Tv must be within 0.01 % of 0.001 m.
        """
        alpha_tv_true = 0.001
        signals = _make_exact_signals(alpha_tv_true, [2.0, 4.0, 6.0, 8.0])

        result = invert_alpha_tv(
            signals,
            bounds=(1e-6, 1.0),
            tol=1e-10,
            maxiter=500,
        )

        assert result.converged, (
            f"Inversion did not converge: {result.message}"
        )
        rel_err = abs(result.alpha_tv_fit - alpha_tv_true) / alpha_tv_true
        assert rel_err < 1e-4, (
            f"Recovered αTv = {result.alpha_tv_fit:.8f}, truth = {alpha_tv_true}, "
            f"relative error = {rel_err:.2e} (must be < 1e-4)"
        )

    def test_small_alpha_tv(self):
        """alpha_Tv = 1e-4 m — near the lower end of realistic range."""
        alpha_tv_true = 1e-4
        signals = _make_exact_signals(alpha_tv_true, [1.0, 3.0, 5.0, 7.0])
        result = invert_alpha_tv(signals, bounds=(1e-7, 1.0), tol=1e-11, maxiter=500)
        assert result.converged
        assert abs(result.alpha_tv_fit - alpha_tv_true) / alpha_tv_true < 1e-4

    def test_large_alpha_tv(self):
        """alpha_Tv = 0.1 m — near the upper end of realistic range."""
        alpha_tv_true = 0.1
        signals = _make_exact_signals(alpha_tv_true, [2.0, 4.0, 6.0, 8.0])
        result = invert_alpha_tv(signals, bounds=(1e-6, 1.0), tol=1e-10, maxiter=500)
        assert result.converged
        assert abs(result.alpha_tv_fit - alpha_tv_true) / alpha_tv_true < 1e-4

    def test_single_signal_still_converges(self):
        """One signal is the minimum required; solution should still be unique."""
        alpha_tv_true = 0.001
        signals = _make_exact_signals(alpha_tv_true, [4.0])
        result = invert_alpha_tv(signals, bounds=(1e-6, 1.0), tol=1e-10, maxiter=500)
        assert result.converged
        assert abs(result.alpha_tv_fit - alpha_tv_true) / alpha_tv_true < 1e-4

    def test_residual_is_near_zero_for_exact_data(self):
        """Sum-of-squared residuals must be essentially zero for noiseless data."""
        alpha_tv_true = 0.001
        signals = _make_exact_signals(alpha_tv_true, [2.0, 4.0, 6.0, 8.0])
        result = invert_alpha_tv(signals, bounds=(1e-6, 1.0), tol=1e-10, maxiter=500)
        assert result.converged
        assert result.residual_sum_sq < 1e-3  # practically zero for exact data

    def test_per_signal_residuals_are_reported(self):
        """InversionResult must carry per-signal diagnostics."""
        signals = _make_exact_signals(0.001, [2.0, 4.0, 6.0, 8.0])
        result = invert_alpha_tv(signals, bounds=(1e-6, 1.0), tol=1e-10, maxiter=500)
        assert result.converged
        assert len(result.per_signal) == 4
        for row in result.per_signal:
            assert set(row.keys()) >= {"M", "L_obs", "L_mod", "residual_m", "residual_pct"}

    def test_varied_chemistry_across_signals(self):
        """Different chemistry per signal still converges to truth."""
        alpha_tv_true = 0.002
        signals = [
            Signal(M=2.0, L_max_obs=liedl_lmax(2.0, alpha_tv_true, 3.5, 8.0, 5.0),
                   gamma=3.5, Ca=8.0, Cd=5.0),
            Signal(M=4.0, L_max_obs=liedl_lmax(4.0, alpha_tv_true, 2.0, 10.0, 4.0),
                   gamma=2.0, Ca=10.0, Cd=4.0),
            Signal(M=6.0, L_max_obs=liedl_lmax(6.0, alpha_tv_true, 4.0, 6.0, 6.0),
                   gamma=4.0, Ca=6.0, Cd=6.0),
            Signal(M=8.0, L_max_obs=liedl_lmax(8.0, alpha_tv_true, 3.0, 9.0, 7.0),
                   gamma=3.0, Ca=9.0, Cd=7.0),
        ]
        result = invert_alpha_tv(signals, bounds=(1e-6, 1.0), tol=1e-10, maxiter=500)
        assert result.converged
        assert abs(result.alpha_tv_fit - alpha_tv_true) / alpha_tv_true < 1e-4


class TestRoundTripWithNoise:
    """
    Noisy synthetic round-trip.

    Forward pass:  known alpha_Tv → 4 L_max observations + Gaussian-like noise
    Inverse pass:  inversion from wide bounds
    Assert:        recovered alpha_Tv within 5 % of truth
    """

    def test_five_percent_noise(self):
        """5 % measurement noise → recovered αTv within 5 % of truth."""
        alpha_tv_true = 0.001
        noise = [0.05, -0.03, 0.04, -0.02]
        signals = _make_noisy_signals(alpha_tv_true, [2.0, 4.0, 6.0, 8.0], noise)

        result = invert_alpha_tv(signals, bounds=(1e-6, 1.0), tol=1e-9, maxiter=500)

        assert result.converged, f"Did not converge: {result.message}"
        rel_err = abs(result.alpha_tv_fit - alpha_tv_true) / alpha_tv_true
        assert rel_err < 0.05, (
            f"With 5 % noise, αTv error = {rel_err:.2%} (must be < 5 %)"
        )

    def test_ten_percent_noise(self):
        """10 % noise → recovered αTv within 15 % of truth (looser tolerance)."""
        alpha_tv_true = 0.001
        noise = [0.10, -0.08, 0.09, -0.07]
        signals = _make_noisy_signals(alpha_tv_true, [2.0, 4.0, 6.0, 8.0], noise)

        result = invert_alpha_tv(signals, bounds=(1e-6, 1.0), tol=1e-9, maxiter=500)

        assert result.converged
        rel_err = abs(result.alpha_tv_fit - alpha_tv_true) / alpha_tv_true
        assert rel_err < 0.15


# ═══════════════════════════════════════════════════════════════════════════════
# Convergence detection
# ═══════════════════════════════════════════════════════════════════════════════

class TestNonConvergenceDetection:
    """
    The inversion MUST report failure and MUST NOT present a result as
    valid when the solver did not converge.
    """

    def test_maxiter_1_reports_not_converged(self):
        """maxiter=1 is too few; solver must set converged=False."""
        signals = _make_exact_signals(0.001, [2.0, 4.0, 6.0, 8.0])
        result = invert_alpha_tv(signals, bounds=(1e-6, 1.0), tol=1e-9, maxiter=1)
        assert not result.converged, (
            "Expected non-convergence with maxiter=1 but got converged=True"
        )

    def test_non_convergence_still_returns_result_object(self):
        """Even on failure, InversionResult is returned (not an exception)."""
        signals = _make_exact_signals(0.001, [2.0, 4.0])
        result = invert_alpha_tv(signals, bounds=(1e-6, 1.0), tol=1e-15, maxiter=2)
        # May or may not converge with 2 iterations, but must not raise
        assert isinstance(result, InversionResult)

    def test_iteration_count_is_reported(self):
        """n_iterations must be a positive integer in the result."""
        signals = _make_exact_signals(0.001, [2.0, 4.0, 6.0, 8.0])
        result = invert_alpha_tv(signals, bounds=(1e-6, 1.0), tol=1e-10, maxiter=500)
        assert isinstance(result.n_iterations, int)
        assert result.n_iterations > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Input validation
# ═══════════════════════════════════════════════════════════════════════════════

class TestInputValidation:
    def test_empty_signals_raises(self):
        with pytest.raises(ValueError, match="At least one signal"):
            invert_alpha_tv([])

    def test_negative_M_raises(self):
        with pytest.raises(ValueError, match="M must be positive"):
            invert_alpha_tv([Signal(M=-1.0, L_max_obs=1000.0, gamma=3.5, Ca=8.0, Cd=5.0)])

    def test_zero_L_max_obs_raises(self):
        with pytest.raises(ValueError, match="L_max_obs must be positive"):
            invert_alpha_tv([Signal(M=2.0, L_max_obs=0.0, gamma=3.5, Ca=8.0, Cd=5.0)])

    def test_invalid_bounds_raises(self):
        signals = _make_exact_signals(0.001, [2.0])
        with pytest.raises(ValueError, match="Lower bound"):
            invert_alpha_tv(signals, bounds=(-1.0, 1.0))
        with pytest.raises(ValueError, match="Upper bound"):
            invert_alpha_tv(signals, bounds=(0.5, 0.1))

    def test_zero_tol_raises(self):
        signals = _make_exact_signals(0.001, [2.0])
        with pytest.raises(ValueError, match="Tolerance"):
            invert_alpha_tv(signals, tol=0.0)

    def test_zero_maxiter_raises(self):
        signals = _make_exact_signals(0.001, [2.0])
        with pytest.raises(ValueError, match="maxiter"):
            invert_alpha_tv(signals, maxiter=0)
