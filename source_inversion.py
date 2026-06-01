"""
source_inversion.py — Iterative single-source inverse modelling.

Given ~4 observed plume-length signals (each paired with a known effective
source thickness M), this module iterates the Liedl forward model to recover
the transverse dispersivity alpha_Tv that best explains all observations
simultaneously.

Physical interpretation
-----------------------
Each signal represents one field observation:
  • M_i      — source (effective) thickness measured in the field [m]
               (e.g., 2× the circle radius from source geometry, or a borehole
               measurement of the contaminated interval)
  • L_max_obs_i — observed plume length from field mapping [m]
  • gamma_i, Ca_i, Cd_i — chemistry parameters (may vary between campaigns)

The inversion minimises the sum of squared plume-length residuals:

    min_{alpha_Tv}  Σ_i ( L_max_model(M_i, alpha_Tv, …) − L_max_obs_i )²

using SciPy's Brent bounded minimiser.  The forward model call at each
iteration is  analytical_models.liedl_lmax — the same function used by the
forward modelling panels.

OUT OF SCOPE (TODO stubs only):
  • Multi-source inversion
  • Irregular geometry
  • Joint inversion for more than one aquifer parameter
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from scipy.optimize import minimize_scalar

from analytical_models import liedl_lmax


# ── Data containers ────────────────────────────────────────────────────────────

@dataclass
class Signal:
    """One field observation used as an inversion constraint."""
    M: float           # Effective source thickness [m] (known from field)
    L_max_obs: float   # Observed plume length [m]
    gamma: float       # Stoichiometric ratio [-]
    Ca: float          # Electron acceptor concentration [mg/L]
    Cd: float          # Electron donor concentration [mg/L]


@dataclass
class InversionResult:
    """Outcome of invert_alpha_tv.  Check ``converged`` before using the fit."""
    alpha_tv_fit: float
    residual_sum_sq: float       # Σ (L_mod − L_obs)²  [m²]
    converged: bool              # False → do NOT trust alpha_tv_fit
    n_iterations: int            # Solver iteration / function-evaluation count
    message: str                 # Human-readable solver message
    per_signal: list[dict]       # Per-observation diagnostics (see below)
    # Each dict in per_signal has keys:
    #   M, L_obs, L_mod, residual_m (L_mod − L_obs), residual_pct


# ── Core inversion ─────────────────────────────────────────────────────────────

def invert_alpha_tv(
    signals: Sequence[Signal],
    bounds: tuple[float, float] = (1e-7, 1.0),
    tol: float = 1e-9,
    maxiter: int = 500,
) -> InversionResult:
    """
    Iteratively fit transverse dispersivity alpha_Tv to a set of plume-length
    observations by minimising the sum of squared residuals.

    The Liedl forward model is called on every solver iteration; convergence
    is guaranteed for physically plausible inputs because L_max(alpha_Tv) is
    strictly monotone decreasing and smooth.

    Parameters
    ----------
    signals  : sequence of Signal objects.  Minimum 1; >= 4 recommended.
               Different M_i values across signals improve conditioning.
    bounds   : (lower, upper) search bracket for alpha_Tv [m].
               Both must be positive; lower < upper.
    tol      : solver convergence tolerance on alpha_Tv (absolute) [m].
    maxiter  : maximum number of solver iterations.

    Returns
    -------
    InversionResult — always returned even on failure.  The caller MUST check
    ``result.converged`` before using ``result.alpha_tv_fit``.

    Raises
    ------
    ValueError  for obviously invalid inputs (checked before the solver runs).
    """
    if len(signals) == 0:
        raise ValueError("At least one signal is required.")

    lo, hi = bounds
    if lo <= 0:
        raise ValueError(f"Lower bound must be positive (got {lo}).")
    if hi <= lo:
        raise ValueError(f"Upper bound {hi} must be > lower bound {lo}.")
    if tol <= 0:
        raise ValueError(f"Tolerance must be positive (got {tol}).")
    if maxiter < 1:
        raise ValueError(f"maxiter must be >= 1 (got {maxiter}).")

    for i, s in enumerate(signals, 1):
        tag = f"Signal {i}"
        if s.M <= 0:
            raise ValueError(f"{tag}: M must be positive (got {s.M}).")
        if s.L_max_obs <= 0:
            raise ValueError(f"{tag}: L_max_obs must be positive (got {s.L_max_obs}).")
        if s.Ca <= 0:
            raise ValueError(f"{tag}: Ca must be positive (got {s.Ca}).")
        if s.Cd <= 0:
            raise ValueError(f"{tag}: Cd must be positive (got {s.Cd}).")

    # ── Objective function (inner forward-model loop) ──────────────────────────
    def _objective(alpha_tv: float) -> float:
        total = 0.0
        for s in signals:
            try:
                L_mod = liedl_lmax(s.M, alpha_tv, s.gamma, s.Ca, s.Cd)
                total += (L_mod - s.L_max_obs) ** 2
            except (ValueError, ZeroDivisionError, OverflowError):
                return 1e30
        return total

    # ── Brent's bounded 1-D minimiser ─────────────────────────────────────────
    opt = minimize_scalar(
        _objective,
        bounds=bounds,
        method="bounded",
        options={"xatol": tol, "maxiter": maxiter},
    )

    alpha_tv_fit = float(opt.x)
    converged = bool(opt.success)
    n_iter = int(getattr(opt, "nit", getattr(opt, "nfev", 0)))

    # ── Per-signal diagnostics ────────────────────────────────────────────────
    per_signal: list[dict] = []
    for s in signals:
        try:
            L_mod = liedl_lmax(s.M, alpha_tv_fit, s.gamma, s.Ca, s.Cd)
        except Exception:
            L_mod = float("nan")
        res_m = L_mod - s.L_max_obs
        res_pct = 100.0 * res_m / s.L_max_obs if s.L_max_obs != 0 else float("nan")
        per_signal.append({
            "M": s.M,
            "L_obs": s.L_max_obs,
            "L_mod": L_mod,
            "residual_m": res_m,
            "residual_pct": res_pct,
        })

    return InversionResult(
        alpha_tv_fit=alpha_tv_fit,
        residual_sum_sq=float(opt.fun),
        converged=converged,
        n_iterations=n_iter,
        message=getattr(opt, "message", ""),
        per_signal=per_signal,
    )


# ── TODO stubs for out-of-scope features ──────────────────────────────────────

def invert_multi_source(*args, **kwargs):  # pragma: no cover
    """TODO: multi-source inversion (out of scope for MVP)."""
    raise NotImplementedError("Multi-source inversion is not yet supported.")


def invert_irregular_geometry(*args, **kwargs):  # pragma: no cover
    """TODO: inversion for irregular source geometry (out of scope for MVP)."""
    raise NotImplementedError("Irregular geometry inversion is not yet supported.")
