"""Consistent 2-decimal number formatting across the workbench.

Supervisor requirement: every displayed number carries two digits. Groundwater
data spans orders of magnitude (plume lengths in hundreds of metres, trace
concentrations at 1e-6 mg/L), so a plain "%.2f" would render real values as
"0.00". We therefore use two decimals in the normal range and fall back to
two-decimal scientific notation outside it.
"""
from __future__ import annotations

import numpy as np

# Outside this band, two fixed decimals would lose the value entirely.
_SMALL = 0.01
_LARGE = 100_000.0

# Bokeh NumeralTickFormatter / tooltip patterns.
FIXED_PATTERN = "0.00"
SCIENTIFIC_PATTERN = "0.00e+0"


def fmt(value) -> str:
    """Format a single number with two significant decimals."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not np.isfinite(v):
        return "n/a"
    if v == 0:
        return "0.00"
    if _SMALL <= abs(v) < _LARGE:
        return f"{v:.2f}"
    return f"{v:.2e}"


def needs_scientific(values) -> bool:
    """True when ``values`` sit outside the range two fixed decimals can show."""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr) & (arr != 0)]
    if arr.size == 0:
        return False
    magnitude = np.abs(arr)
    return bool(magnitude.min() < _SMALL or magnitude.max() >= _LARGE)


def tick_pattern(values) -> str:
    """Bokeh numeral pattern suited to ``values``."""
    return SCIENTIFIC_PATTERN if needs_scientific(values) else FIXED_PATTERN


def tooltip_pattern(values) -> str:
    """Bokeh tooltip field pattern, e.g. '@x{0.00}' -> returns the '0.00' part."""
    return tick_pattern(values)


def apply_number_format(fig, values, axis: str = "both") -> None:
    """Attach a two-decimal tick formatter to a Bokeh figure's numeric axes."""
    from bokeh.models import NumeralTickFormatter

    pattern = tick_pattern(values)
    formatter = NumeralTickFormatter(format=pattern)
    if axis in ("x", "both"):
        for ax in fig.xaxis:
            # Categorical axes have no numeric formatter to swap.
            if hasattr(ax, "formatter"):
                try:
                    ax.formatter = formatter
                except Exception:
                    pass
    if axis in ("y", "both"):
        for ax in fig.yaxis:
            if hasattr(ax, "formatter"):
                try:
                    ax.formatter = NumeralTickFormatter(format=pattern)
                except Exception:
                    pass


def format_frame(df, decimals: int = 2):
    """Round a DataFrame's numeric columns for display."""
    out = df.copy()
    for col in out.columns:
        if out[col].dtype.kind in "fc":
            out[col] = out[col].map(fmt)
    return out
