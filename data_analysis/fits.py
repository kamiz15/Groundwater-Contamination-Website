"""Curve fitting for scatter plots: linear, polynomial, exponential, logarithmic.

Each fit returns a :class:`FitResult` carrying the parameters, a vectorised
``predict`` callable, R2, the sample size and (optionally) a 95% confidence band
evaluated on a dense grid for drawing. All maths is numpy/scipy; no plotting.

Confidence bands are for the mean response (not prediction intervals):
    ci = t(0.975, dof) * sqrt(var(yhat))
where ``var(yhat)`` comes from the parameter covariance propagated through the
model Jacobian at each x (delta method).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy import optimize
from scipy import stats

FIT_TYPES = ("linear", "exponential", "logarithmic", "polynomial-2", "polynomial-3", "polynomial-4")


@dataclass
class FitResult:
    name: str
    params: dict[str, float]
    predict: Callable[[np.ndarray], np.ndarray]
    r2: float
    n: int
    label: str
    # Dense grid + confidence band for drawing (band is None if unavailable).
    x_grid: np.ndarray
    y_grid: np.ndarray
    band: tuple[np.ndarray, np.ndarray] | None = None


def _clean_xy(x, y) -> tuple[np.ndarray, np.ndarray]:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.shape != y.shape:
        raise ValueError("X and Y must have the same length.")
    mask = np.isfinite(x) & np.isfinite(y)
    return x[mask], y[mask]


def _r2(y: np.ndarray, y_hat: np.ndarray) -> float:
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    if ss_tot == 0.0:
        # A perfectly flat y: the fit explains it iff residuals vanish.
        return 1.0 if ss_res == 0.0 else 0.0
    return 1.0 - ss_res / ss_tot


def _dense_grid(x: np.ndarray, n: int = 200) -> np.ndarray:
    return np.linspace(float(np.min(x)), float(np.max(x)), n)


def _poly_fit(x, y, degree: int, *, with_band: bool, label_name: str) -> FitResult:
    n = x.size
    n_params = degree + 1
    if n < n_params + 2:
        raise ValueError(
            f"Need at least {n_params + 2} points for a {label_name} fit; got {n}."
        )
    coef, cov = np.polyfit(x, y, degree, cov=True)
    predict = lambda xq: np.polyval(coef, np.asarray(xq, dtype=float))
    r2 = _r2(y, predict(x))

    xg = _dense_grid(x)
    yg = predict(xg)
    band = None
    if with_band:
        dof = n - n_params
        if dof > 0:
            tval = float(stats.t.ppf(0.975, dof))
            # Vandermonde row for each grid point, highest power first to match polyfit.
            powers = np.arange(degree, -1, -1)
            vand = xg[:, None] ** powers[None, :]
            var_yhat = np.einsum("ij,jk,ik->i", vand, cov, vand)
            se = np.sqrt(np.clip(var_yhat, 0.0, None))
            band = (yg - tval * se, yg + tval * se)

    params = {f"c{degree - i}": float(c) for i, c in enumerate(coef)}
    return FitResult(
        name=label_name, params=params, predict=predict, r2=r2, n=n,
        label=_poly_label(coef, degree), x_grid=xg, y_grid=yg, band=band,
    )


def _poly_label(coef: np.ndarray, degree: int) -> str:
    terms = []
    for i, c in enumerate(coef):
        p = degree - i
        if p == 0:
            terms.append(f"{c:.4g}")
        elif p == 1:
            terms.append(f"{c:.4g}·x")
        else:
            terms.append(f"{c:.4g}·x^{p}")
    return "y = " + " + ".join(terms)


def _exp_fit(x, y, *, with_band: bool) -> FitResult:
    n = x.size
    if n < 4:
        raise ValueError(f"Need at least 4 points for an exponential fit; got {n}.")

    def model(xq, a, b):
        return a * np.exp(b * xq)

    # Seed from a log-linear fit when all y are positive; else a flat guess.
    if np.all(y > 0):
        b0, log_a0 = np.polyfit(x, np.log(y), 1)
        p0 = (float(np.exp(log_a0)), float(b0))
    else:
        p0 = (float(np.mean(y)) or 1.0, 0.0)

    try:
        popt, pcov = optimize.curve_fit(model, x, y, p0=p0, maxfev=10000)
    except (RuntimeError, ValueError) as exc:
        raise ValueError(
            "Exponential fit did not converge for this data. "
            "Try a polynomial fit instead."
        ) from exc

    a, b = float(popt[0]), float(popt[1])
    predict = lambda xq: model(np.asarray(xq, dtype=float), a, b)
    r2 = _r2(y, predict(x))

    xg = _dense_grid(x)
    yg = predict(xg)
    band = None
    if with_band:
        dof = n - 2
        if dof > 0 and np.all(np.isfinite(pcov)):
            tval = float(stats.t.ppf(0.975, dof))
            # Jacobian of a·e^{bx} wrt (a, b): [e^{bx}, a·x·e^{bx}].
            exp_bx = np.exp(b * xg)
            jac = np.stack([exp_bx, a * xg * exp_bx], axis=1)
            var_yhat = np.einsum("ij,jk,ik->i", jac, pcov, jac)
            se = np.sqrt(np.clip(var_yhat, 0.0, None))
            band = (yg - tval * se, yg + tval * se)

    return FitResult(
        name="exponential", params={"a": a, "b": b}, predict=predict, r2=r2, n=n,
        label=f"y = {a:.4g}·e^({b:.4g}·x)", x_grid=xg, y_grid=yg, band=band,
    )


def _log_fit(x, y, *, with_band: bool) -> FitResult:
    n = x.size
    if n < 4:
        raise ValueError(f"Need at least 4 points for a logarithmic fit; got {n}.")
    if np.any(x <= 0):
        raise ValueError("Logarithmic fit needs strictly positive X values.")

    lx = np.log(x)
    coef, cov = np.polyfit(lx, y, 1, cov=True)
    b, a = float(coef[0]), float(coef[1])  # y = a + b·ln x
    predict = lambda xq: a + b * np.log(np.asarray(xq, dtype=float))
    r2 = _r2(y, predict(x))

    xg = _dense_grid(x)
    yg = predict(xg)
    band = None
    if with_band:
        dof = n - 2
        if dof > 0:
            tval = float(stats.t.ppf(0.975, dof))
            lxg = np.log(xg)
            vand = np.stack([lxg, np.ones_like(lxg)], axis=1)  # matches [b, a] order
            var_yhat = np.einsum("ij,jk,ik->i", vand, cov, vand)
            se = np.sqrt(np.clip(var_yhat, 0.0, None))
            band = (yg - tval * se, yg + tval * se)

    return FitResult(
        name="logarithmic", params={"a": a, "b": b}, predict=predict, r2=r2, n=n,
        label=f"y = {a:.4g} + {b:.4g}·ln(x)", x_grid=xg, y_grid=yg, band=band,
    )


def fit_curve(x, y, kind: str, *, with_band: bool = False) -> FitResult:
    """Fit ``kind`` to (x, y). ``kind`` is one of :data:`FIT_TYPES`."""
    x, y = _clean_xy(x, y)
    if x.size == 0:
        raise ValueError("No finite (x, y) pairs to fit.")

    if kind == "linear":
        return _poly_fit(x, y, 1, with_band=with_band, label_name="linear")
    if kind == "exponential":
        return _exp_fit(x, y, with_band=with_band)
    if kind == "logarithmic":
        return _log_fit(x, y, with_band=with_band)
    if kind.startswith("polynomial-"):
        degree = int(kind.split("-", 1)[1])
        if degree < 2 or degree > 4:
            raise ValueError("Polynomial fits support orders 2 to 4.")
        return _poly_fit(x, y, degree, with_band=with_band, label_name=f"polynomial (order {degree})")
    raise ValueError(f"Unknown fit type '{kind}'.")
