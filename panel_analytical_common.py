from __future__ import annotations

import panel as pn
from bokeh.plotting import figure

from data_queries import get_user_sites
from security import user_safe_error


PARAM_ALIASES = {
    "M": ("M", "H", "aquifer_thickness"),
    "H": ("H", "M", "aquifer_thickness"),
    "W": ("W", "Sw", "S_w", "sourceWidthW", "plume_width"),
    "Sw": ("Sw", "W", "S_w", "sourceWidthW", "plume_width"),
    "S_w": ("S_w", "Sw", "W", "sourceWidthW", "plume_width"),
    "C_EA0": ("C_EA0", "C_A", "Ca", "electron_acceptor_o2"),
    "C_A": ("C_A", "Ca", "C_EA0", "electron_acceptor_o2"),
    "Ca": ("Ca", "C_A", "C_EA0", "electron_acceptor_o2"),
    "C_ED0": ("C_ED0", "C_D", "Cd", "c0", "electron_donor"),
    "C_D": ("C_D", "Cd", "C_ED0", "c0", "electron_donor"),
    "Cd": ("Cd", "C_D", "C_ED0", "c0", "electron_donor"),
    "c0": ("c0", "C_D", "Cd", "C_ED0", "electron_donor"),
    "alpha_Tv": ("alpha_Tv", "av", "tv"),
    "av": ("av", "alpha_Tv", "tv"),
    "tv": ("tv", "alpha_Tv", "av"),
    "alpha_Th": ("alpha_Th", "alpha_th", "at", "ay"),
    "alpha_th": ("alpha_th", "alpha_Th", "at", "ay"),
    "at": ("at", "alpha_Th", "alpha_th", "ay"),
    "hk": ("hk", "K", "hydraulic_conductivity"),
    "K": ("K", "hk", "hydraulic_conductivity"),
    "K_h": ("K_h", "Kh", "hk", "K", "hydraulic_conductivity"),
    "vk": ("vk", "K_v", "Kv", "vertical_hydraulic_conductivity"),
    "K_v": ("K_v", "vk", "Kv", "vertical_hydraulic_conductivity"),
    "C0": ("C0", "c0_threshold", "plume_threshold"),
    "perlen": ("perlen", "simulation_time", "simulation_days"),
    "gamma": ("gamma", "g"),
    "g": ("g", "gamma"),
    "S_Ta": ("S_Ta", "R_Ta"),
    "S_Tb": ("S_Tb", "R_Tb"),
    "R_Ta": ("R_Ta", "S_Ta"),
    "R_Tb": ("R_Tb", "S_Tb"),
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
        user_safe_error(exc, "Database error while loading analytical comparison points")
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
    <div style="background:#eef1f5;border:1px solid #e3e8ef;border-radius:10px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,0.07);">
      <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#5b6b7f;margin-bottom:6px;">Result</div>
      <div style="font-size:1rem;color:#16212e;">{message}</div>
    </div>
    """


def metric_card(label: str, value_text: str, unit: str = "m", title: str = "Simulation Result") -> str:
    unit_html = f'<span style="font-size:1rem;font-weight:700;color:#1f72cd;">{unit}</span>' if unit else ''
    return f"""
    <div style="background:#eef1f5;border:1px solid #e3e8ef;border-left:3px solid #1f72cd;border-radius:10px;padding:18px 20px;box-shadow:0 1px 3px rgba(16,24,40,0.07);">
      <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#5b6b7f;margin-bottom:8px;">{title}</div>
      <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">
        <span style="font-size:1rem;font-weight:600;color:#5b6b7f;">{label}</span>
        <span style="font-size:1.9rem;font-weight:800;color:#0b2c4f;line-height:1;">{value_text}</span>
        {unit_html}
      </div>
    </div>
    """


def summary_card(items: list[tuple[str, str]], title: str = "Simulation Summary") -> str:
    blocks = "".join(
        f'<div><span style="font-size:0.85rem;color:#5b6b7f;">{label}</span><div style="font-size:1.7rem;font-weight:800;color:#0b2c4f;">{value}</div></div>'
        for label, value in items
    )
    return f"""
    <div style="background:#eef1f5;border:1px solid #e3e8ef;border-left:3px solid #1f72cd;border-radius:10px;padding:18px 20px;box-shadow:0 1px 3px rgba(16,24,40,0.07);">
      <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#5b6b7f;margin-bottom:8px;">{title}</div>
      <div style="display:flex;gap:18px;flex-wrap:wrap;">{blocks}</div>
    </div>
    """


def error_card(message) -> str:
    message = user_safe_error(message)
    return f"""
    <div style="background:#fef3f2;border:1px solid #f7c5c0;border-radius:10px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,0.05);">
      <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#b42318;margin-bottom:6px;">Error</div>
      <div style="font-size:0.98rem;color:#7a271a;">{message}</div>
    </div>
    """


def comparison_plot_data(title: str, manual_label: str, manual_x, manual_y,
                         selected_site_id: int, email: str, manual_axis_label: str):
    field_x, field_y = load_field_points(email) if selected_site_id > 0 else ([], [])
    return {
        "type": "comparison_scatter",
        "title": title,
        "x_label": "Site Number" if selected_site_id > 0 else manual_axis_label,
        "y_label": "Plume Length (m)",
        "field_label": "Database plume length",
        "field_x": field_x,
        "field_y": field_y,
        "manual_label": manual_label,
        "manual_x": list(manual_x),
        "manual_y": list(manual_y),
        "caption": ("Database plume lengths compared with the model result."
                    if field_x else "Computed model plume lengths."),
    }


def comparison_plot(title: str, manual_label: str, manual_x, manual_y,
                    selected_site_id: int, email: str, manual_axis_label: str,
                    return_data: bool = False):
    plot_data = comparison_plot_data(
        title, manual_label, manual_x, manual_y,
        selected_site_id, email, manual_axis_label,
    )
    p = figure(
        title=plot_data["title"],
        x_axis_label=plot_data["x_label"],
        y_axis_label=plot_data["y_label"],
        height=420,
        sizing_mode="stretch_width",
    )
    if plot_data["field_x"] and plot_data["field_y"]:
        p.scatter(plot_data["field_x"], plot_data["field_y"], size=12, marker="circle", color="#5598e3", legend_label=plot_data["field_label"])
    p.scatter(plot_data["manual_x"], plot_data["manual_y"], size=14 if len(plot_data["manual_y"]) == 1 else 12, marker="circle", color="#0e3a69", legend_label=plot_data["manual_label"])
    p.legend.location = "top_right"
    return (p, plot_data) if return_data else p
