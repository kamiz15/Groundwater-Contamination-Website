from __future__ import annotations

import panel as pn

# The cards and the comparison chart are identical for analytical and empirical
# pages; only the query-parameter aliases below differ.
from panel_analytical_common import (  # noqa: F401  (re-exported for the panels)
    comparison_plot,
    comparison_plot_data,
    error_card,
    info_card,
    load_field_points,
    metric_card,
    summary_card,
)


PARAM_ALIASES = {
    "M": ("M", "H", "aquifer_thickness"),
    "Ca": ("Ca", "C_A", "C_EA0", "electron_acceptor_o2"),
    "Cd": ("Cd", "C_D", "C_ED0", "c0", "electron_donor"),
    "tv": ("tv", "alpha_Tv", "av"),
    "g": ("g", "gamma"),
    "R": ("R",),
}


def _request_arg(name: str):
    req = pn.state.curdoc.session_context.request
    names = PARAM_ALIASES.get(name, (name,))
    for candidate in names:
        if candidate in req.arguments:
            return req.arguments[candidate][0].decode()
    return None


def query_float(name: str, default: float) -> float:
    try:
        raw = _request_arg(name)
        if raw is None or raw == "":
            return default
        return float(raw)
    except Exception:
        return default


def query_int(name: str, default: int = 0) -> int:
    try:
        raw = _request_arg(name)
        if raw is None or raw == "":
            return default
        return int(float(raw))
    except Exception:
        return default


def query_str(name: str, default: str = "") -> str:
    try:
        raw = _request_arg(name)
        return raw if raw is not None else default
    except Exception:
        return default
