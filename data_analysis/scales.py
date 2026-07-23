"""Axis-scale transforms: linear, natural log, log base 10, inverse.

Bokeh only ships a native log10 axis, so instead of switching axis types we
transform the data and relabel the axis. That gives all four scales identical,
predictable behaviour on every plot.

ln / log10 / inverse are undefined at or below zero, so each transform raises a
``ValueError`` with a message safe to show the user.
"""
from __future__ import annotations

import numpy as np

SCALES = ("linear", "ln", "log10", "inverse")


def axis_label(name: str, scale: str = "linear") -> str:
    """Typeset axis title for ``name`` under ``scale`` (LaTeX, for Bokeh)."""
    if scale not in SCALES:
        raise ValueError(f"Unknown scale '{scale}'.")
    from . import notation
    return notation.latex_label(name, scale)


def plain_axis_label(name: str, scale: str = "linear") -> str:
    """Plain-text label for legends, tooltips and titles Bokeh will not typeset."""
    if scale not in SCALES:
        raise ValueError(f"Unknown scale '{scale}'.")
    from . import notation
    return notation.plain_label(name, scale)


def requires_positive(scale: str) -> bool:
    return scale in ("ln", "log10", "inverse")


def transform(values, scale: str = "linear", *, name: str = "values") -> np.ndarray:
    """Apply ``scale`` to ``values``.

    Raises ``ValueError`` if the scale needs strictly positive data and the
    input contains zero or negative entries.
    """
    if scale not in SCALES:
        raise ValueError(f"Unknown scale '{scale}'.")
    arr = np.asarray(values, dtype=float)
    if scale == "linear":
        return arr

    finite = arr[np.isfinite(arr)]
    if finite.size and np.any(finite <= 0):
        raise ValueError(
            f"The {scale} scale needs strictly positive values, but '{name}' "
            "contains zero or negative entries. Use the linear scale for this column."
        )
    with np.errstate(divide="ignore", invalid="ignore"):
        if scale == "ln":
            return np.log(arr)
        if scale == "log10":
            return np.log10(arr)
        return 1.0 / arr  # inverse


def transform_lenient(values, scale: str = "linear") -> np.ndarray:
    """Like :func:`transform` but yields NaN for out-of-domain entries.

    Used for fitted curves and confidence bands: a fit computed on positive raw
    data can still predict a non-positive value, and one such point should blank
    out that part of the curve rather than abort the whole plot.
    """
    if scale not in SCALES:
        raise ValueError(f"Unknown scale '{scale}'.")
    arr = np.asarray(values, dtype=float)
    if scale == "linear":
        return arr
    out = np.full(arr.shape, np.nan, dtype=float)
    valid = np.isfinite(arr) & (arr > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        if scale == "ln":
            out[valid] = np.log(arr[valid])
        elif scale == "log10":
            out[valid] = np.log10(arr[valid])
        else:
            out[valid] = 1.0 / arr[valid]
    return out


def transform_pair(x, y, x_scale: str, y_scale: str, *, x_name="x", y_name="y"):
    """Transform an (x, y) pair, dropping points that become non-finite."""
    tx = transform(x, x_scale, name=x_name)
    ty = transform(y, y_scale, name=y_name)
    mask = np.isfinite(tx) & np.isfinite(ty)
    return tx[mask], ty[mask], mask
