"""Gridded-data helpers for the scientific (Group 3) plots.

Two entry points:
- :func:`pivot_gridded` turns long-form (x, y, value) rows into a regular grid
  suitable for contour/quiver, validating that the sample points really do form
  a rectangular lattice.
- :func:`long_form_from_result` turns a numerical-model result object back into
  long-form rows, so a future "load my numerical run" feature can feed the same
  code path. It only needs the array attributes, so it accepts anything with
  ``concentration``/``x_grid`` and a ``z_grid`` or ``y_grid`` (duck-typed).

:func:`gradient_vectors` reproduces the −∇C vector maths used by
``plot_functions.plot_concentration_gradient_vectors_interactive``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class GridData:
    """A regular grid: ``values`` has shape ``(len(y), len(x))`` (rows = y)."""
    x: np.ndarray
    y: np.ndarray
    values: np.ndarray
    x_label: str
    y_label: str
    value_label: str


def _regular_axis(sorted_unique: np.ndarray, axis_name: str) -> None:
    """Raise if ``sorted_unique`` is not evenly spaced within tolerance."""
    if sorted_unique.size < 2:
        raise ValueError(f"The {axis_name} axis needs at least 2 distinct values for a grid.")
    diffs = np.diff(sorted_unique)
    step = np.median(diffs)
    if step <= 0:
        raise ValueError(f"The {axis_name} axis values are not increasing.")
    # Allow 1% jitter relative to the median spacing.
    if np.any(np.abs(diffs - step) > 0.01 * abs(step)):
        raise ValueError(
            f"The {axis_name} axis is not evenly spaced, so it can't be gridded. "
            "Use data sampled on a regular grid."
        )


def pivot_gridded(df: pd.DataFrame, x_col: str, y_col: str, value_col: str) -> GridData:
    """Pivot long-form (x, y, value) rows into a :class:`GridData`.

    Raises ``ValueError`` with a friendly message when the columns are missing,
    the grid has holes, or the axes are not evenly spaced.
    """
    for col in (x_col, y_col, value_col):
        if col not in df.columns:
            raise ValueError(f"Column '{col}' is not in the dataset.")
    if len({x_col, y_col, value_col}) < 3:
        raise ValueError("Choose three different columns for X, Y and value.")

    sub = df[[x_col, y_col, value_col]].apply(pd.to_numeric, errors="coerce").dropna()
    if sub.empty:
        raise ValueError("No numeric (X, Y, value) rows to build a grid from.")

    table = sub.pivot_table(index=y_col, columns=x_col, values=value_col, aggfunc="mean")
    if table.isna().to_numpy().any():
        raise ValueError(
            "The grid has missing cells — every (X, Y) combination must have a value. "
            "Check for gaps or duplicate coordinates."
        )

    x = table.columns.to_numpy(dtype=float)
    y = table.index.to_numpy(dtype=float)
    _regular_axis(np.sort(x), "X")
    _regular_axis(np.sort(y), "Y")

    return GridData(
        x=x, y=y, values=table.to_numpy(dtype=float),
        x_label=x_col, y_label=y_col, value_label=value_col,
    )


def long_form_from_result(result) -> pd.DataFrame:
    """Convert a numerical-model result object to long-form (x, cross, value).

    Accepts ``NumericalModelResult`` (vertical; has ``z_grid``) or
    ``HorizontalModelResult`` (plan view; has ``y_grid``). The concentration
    array is stored as ``(len(cross), len(x))`` — verified against
    ``plot_functions._numerical_view_arrays``.
    """
    conc = np.asarray(result.concentration, dtype=float)
    x = np.asarray(result.x_grid, dtype=float)
    if hasattr(result, "z_grid"):
        cross = np.asarray(result.z_grid, dtype=float)
        cross_name = "z_m"
    elif hasattr(result, "y_grid"):
        cross = np.asarray(result.y_grid, dtype=float)
        cross_name = "y_m"
    else:  # pragma: no cover - guards against an unexpected object
        raise ValueError("Result object has neither a z_grid nor a y_grid.")

    if conc.shape != (cross.size, x.size):
        raise ValueError("Concentration grid dimensions do not match the axes.")

    xx, cc = np.meshgrid(x, cross)  # both shape (len(cross), len(x))
    return pd.DataFrame({
        "x_m": xx.ravel(),
        cross_name: cc.ravel(),
        "concentration_mg_L": conc.ravel(),
    })


def aem_result_grid(result):
    """Return validated AEM concentration arrays and display column names."""
    concentration = np.asarray(getattr(result, "result", None), dtype=float)
    x = np.asarray(getattr(result, "xaxis", None), dtype=float)
    cross = np.asarray(getattr(result, "yaxis", None), dtype=float)

    if concentration.ndim != 2 or x.ndim != 1 or cross.ndim != 1:
        raise ValueError("The AEM result does not contain a two-dimensional grid.")
    if concentration.shape != (cross.size, x.size):
        raise ValueError("AEM concentration grid dimensions do not match the axes.")
    if x.size < 2 or cross.size < 2:
        raise ValueError("The AEM result grid needs at least two points on each axis.")
    if not np.isfinite(x).all() or not np.isfinite(cross).all():
        raise ValueError("The AEM result axes contain invalid coordinates.")

    cross_name = (
        "z [m]"
        if getattr(result, "orientation", "horizontal") == "vertical"
        else "y [m]"
    )
    return concentration, x, cross, "x [m]", cross_name, "concentration [mg/L]"


def long_form_from_aem_result(result) -> pd.DataFrame:
    """Convert an AEM field into Workbench-compatible long-form rows."""
    concentration, x, cross, x_name, cross_name, value_name = aem_result_grid(result)
    xx, cc = np.meshgrid(x, cross)
    return pd.DataFrame({
        x_name: xx.ravel(),
        cross_name: cc.ravel(),
        value_name: concentration.ravel(),
    })


def gradient_vectors(grid: GridData, *, max_rows: int = 14, max_cols: int = 24):
    """Return down-gradient (−∇value) vectors sampled for a quiver plot.

    Mirrors the decimation/scaling used in
    ``plot_functions.plot_concentration_gradient_vectors_interactive``.
    Returns a dict of flat arrays keyed x0, y0, x1, y1, angle, magnitude.
    """
    C = grid.values
    x = grid.x
    y = grid.y
    dY, dX = np.gradient(C, y, x, edge_order=1)
    u = -dX
    v = -dY
    magnitude = np.hypot(u, v)

    row_step = max(int(np.ceil(len(y) / max_rows)), 1)
    col_step = max(int(np.ceil(len(x) / max_cols)), 1)
    rows = np.arange(0, len(y), row_step)
    cols = np.arange(0, len(x), col_step)
    xx, yy = np.meshgrid(x[cols], y[rows])
    uu = u[np.ix_(rows, cols)]
    vv = v[np.ix_(rows, cols)]
    mm = magnitude[np.ix_(rows, cols)]

    finite_nonzero = np.isfinite(mm) & (mm > 0)
    safe_mm = np.where(finite_nonzero, mm, 1.0)
    x_scale = (float(x.max()) - float(x.min())) / max(len(cols), 1) * 0.65
    y_scale = (float(y.max()) - float(y.min())) / max(len(rows), 1) * 0.65
    x1 = xx + np.where(finite_nonzero, uu / safe_mm, 0.0) * x_scale
    y1 = yy + np.where(finite_nonzero, vv / safe_mm, 0.0) * y_scale
    angle = np.arctan2(y1 - yy, x1 - xx) - (np.pi / 2.0)

    return {
        "x0": xx.ravel(), "y0": yy.ravel(),
        "x1": x1.ravel(), "y1": y1.ravel(),
        "angle": angle.ravel(), "magnitude": mm.ravel(),
    }
