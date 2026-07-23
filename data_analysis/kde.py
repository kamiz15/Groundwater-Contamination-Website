"""Kernel density estimation via KDEpy's FFTKDE.

KDEpy is imported lazily so the rest of the package still works if the optional
dependency is missing. FFTKDE is fast and supports the ISJ (Improved
Sheather-Jones) automatic bandwidth, which we default to and fall back from.

See https://kdepy.readthedocs.io/en/latest/index.html
"""
from __future__ import annotations

import numpy as np

# KDEpy kernels we expose; "gaussian" is the sensible default.
KERNELS = ("gaussian", "epa", "tri", "biweight", "triweight", "cosine")
BANDWIDTHS = ("ISJ", "silverman", "scott")


def _import_fftkde():
    try:
        from KDEpy import FFTKDE
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ValueError(
            "KDE requires the 'KDEpy' package. Install it with: pip install KDEpy"
        ) from exc
    return FFTKDE


def kde_curve(
    values: np.ndarray,
    kernel: str = "gaussian",
    bw: str | float = "ISJ",
    n_grid: int = 1024,
) -> tuple[np.ndarray, np.ndarray]:
    """Estimate a density curve for 1-D ``values``.

    ``bw`` is an automatic-rule name (see :data:`BANDWIDTHS`) or a positive
    float. If an automatic rule fails on a small/degenerate sample we retry with
    Silverman's rule so the UI still renders something sensible.
    """
    FFTKDE = _import_fftkde()

    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 2:
        raise ValueError("Need at least 2 values for a KDE.")
    if np.ptp(values) == 0:
        raise ValueError("KDE needs values with some spread (all values are equal).")

    if isinstance(bw, str) and bw not in BANDWIDTHS:
        raise ValueError(f"Unknown bandwidth rule '{bw}'.")
    if not isinstance(bw, str) and float(bw) <= 0:
        raise ValueError("Manual bandwidth must be a positive number.")

    try:
        x, y = FFTKDE(kernel=kernel, bw=bw).fit(values).evaluate(n_grid)
    except Exception:
        # ISJ in particular can fail on tiny samples; Silverman is robust.
        x, y = FFTKDE(kernel=kernel, bw="silverman").fit(values).evaluate(n_grid)
    return x, y
