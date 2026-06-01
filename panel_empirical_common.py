from __future__ import annotations

import panel as pn
from bokeh.plotting import figure

from data_queries import get_user_sites
from security import user_safe_error


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


def load_field_points(email: str):
    try:
        rows = get_user_sites(email)
    except Exception as exc:
        user_safe_error(exc, "Database error while loading empirical comparison points")
        return [], []
    xs, ys = [], []
    for i, row in enumerate(rows, start=1):
        try:
            plume = float(row[4])
        except Exception:
            continue
        xs.append(i)
        ys.append(plume)
    return xs, ys


def info_card(message: str) -> str:
    return f"""
    <div style="background:#ffffff;border:1px solid #dce9f9;border-radius:14px;padding:16px 18px;box-shadow:0 8px 24px rgba(17,24,39,0.06);">
      <div style="font-size:0.85rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#5b7a9a;margin-bottom:6px;">Result</div>
      <div style="font-size:1rem;color:#1f2937;">{message}</div>
    </div>
    """


def metric_card(label: str, value_text: str, unit: str = "m", title: str = "Simulation Result") -> str:
    unit_html = f'<span style="font-size:1rem;font-weight:700;color:#3d82b6;">{unit}</span>' if unit else ''
    return f"""
    <div style="background:linear-gradient(135deg,#ffffff 0%,#f4f9ff 100%);border:1px solid #c4ddf5;border-radius:16px;padding:18px 20px;box-shadow:0 12px 28px rgba(17,24,39,0.08);">
      <div style="font-size:0.85rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#2f5f8f;margin-bottom:8px;">{title}</div>
      <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">
        <span style="font-size:1rem;font-weight:700;color:#24476b;">{label}</span>
        <span style="font-size:1.9rem;font-weight:800;color:#163c66;line-height:1;">{value_text}</span>
        {unit_html}
      </div>
    </div>
    """


def summary_card(items: list[tuple[str, str]], title: str = "Simulation Summary") -> str:
    blocks = "".join(
        f'<div><span style="font-size:0.92rem;color:#5b7a9a;">{label}</span><div style="font-size:1.8rem;font-weight:800;color:#163c66;">{value}</div></div>'
        for label, value in items
    )
    return f"""
    <div style="background:linear-gradient(135deg,#ffffff 0%,#f4f9ff 100%);border:1px solid #c4ddf5;border-radius:16px;padding:18px 20px;box-shadow:0 12px 28px rgba(17,24,39,0.08);">
      <div style="font-size:0.85rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#2f5f8f;margin-bottom:8px;">{title}</div>
      <div style="display:flex;gap:18px;flex-wrap:wrap;">{blocks}</div>
    </div>
    """


def error_card(message) -> str:
    message = user_safe_error(message)
    return f"""
    <div style="background:#fff4f4;border:1px solid #f1b7b7;border-radius:14px;padding:16px 18px;box-shadow:0 8px 24px rgba(17,24,39,0.05);">
      <div style="font-size:0.85rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#9f2d2d;margin-bottom:6px;">Error</div>
      <div style="font-size:0.98rem;color:#5f1d1d;">{message}</div>
    </div>
    """


def comparison_plot(title: str, manual_label: str, manual_x, manual_y, selected_site_id: int, email: str, manual_axis_label: str):
    p = figure(
        title=title,
        x_axis_label="Site Number" if selected_site_id > 0 else manual_axis_label,
        y_axis_label="Plume Length (m)",
        height=420,
        sizing_mode="stretch_width",
    )
    if selected_site_id > 0:
        field_x, field_y = load_field_points(email)
        if field_x and field_y:
            p.scatter(field_x, field_y, size=12, marker="circle", color="#7fb6e6", legend_label="Database plume length")
    p.scatter(manual_x, manual_y, size=14 if len(manual_y) == 1 else 12, marker="circle", color="#163c66", legend_label=manual_label)
    p.legend.location = "top_right"
    return p
