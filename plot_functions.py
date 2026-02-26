# plot_functions.py — unified, clean version (Bokeh + CSV fallback)

from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Tuple, Optional

from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.palettes import Category10
from bokeh.models import ColumnDataSource, HoverTool
from scipy.stats import norm, lognorm, expon

# -------------------------------------------------
# Lazy, robust loader for the reference CSV
# -------------------------------------------------
_REF_DF: Optional[pd.DataFrame] = None


def _load_reference_df() -> Optional[pd.DataFrame]:
    """Try to load the original reference CSV. Returns None if not found."""
    global _REF_DF
    if _REF_DF is not None:
        return _REF_DF

    candidates = [
        Path(__file__).resolve().parent / "static" / "original.csv",
        Path(__file__).resolve().parent.parent / "static" / "original.csv",
        Path.cwd() / "static" / "original.csv",
        Path.cwd() / "original.csv",
    ]
    for p in candidates:
        if p.exists():
            try:
                df = pd.read_csv(p)
                _REF_DF = df
                print(f"[plot_functions] Loaded reference CSV from: {p}")
                return _REF_DF
            except Exception as e:
                print(f"[plot_functions] Failed to read {p}: {e}")
    print("[plot_functions] WARNING: reference CSV not found. Plots will use only user data.")
    _REF_DF = None
    return None


def _clean(values: List) -> List[float]:
    """Drop None/NaN and convert to float list."""
    out = []
    for v in values:
        try:
            if v is None:
                continue
            if isinstance(v, str) and v.strip() == "":
                continue
            f = float(v)
            if not np.isnan(f):
                out.append(f)
        except Exception:
            continue
    return out


# -------------------------------------------------
# BAR GRAPH
# -------------------------------------------------
def create_bargraph(table_data: List[list]) -> Tuple[str, str]:
    ref_df = _load_reference_df()
    user_plumes = _clean([row[4] for row in table_data])

    p = figure(
        title="Plume Length Comparison",
        x_axis_label="Index",
        y_axis_label="Plume Length (m)",
        height=420,
        sizing_mode="stretch_both",
        toolbar_location="above",
    )

    plotted = False

    if ref_df is not None and "Plume length[m]" in ref_df.columns:
        ref_vals = _clean(ref_df["Plume length[m]"].tolist())
        if ref_vals:
            p.vbar(x=list(range(len(ref_vals))),
                   top=ref_vals,
                   width=0.8,
                   color="#003f5c",
                   legend_label="Original Data")
            plotted = True

    if user_plumes:
        offset = 0.35 if plotted else 0
        p.vbar(x=[i + offset for i in range(len(user_plumes))],
               top=user_plumes,
               width=0.8,
               color="#ffa600",
               legend_label="User Data")
        plotted = True

    if not plotted:
        p.title.text = "No plume length data available yet."

    p.legend.location = "top_right"
    return components(p)


# -------------------------------------------------
# BOX PLOT
# -------------------------------------------------
def create_boxplot(label: str, table_data: list[list], index: int):
    ref_df = _load_reference_df()

    orig_vals = []
    if ref_df is not None and label in ref_df.columns:
        orig_vals = _clean(ref_df[label].tolist())

    user_vals = _clean([row[index] for row in table_data])

    p = figure(
        title=f"{label} Distribution (Original vs User)",
        x_range=["Original", "User"],
        y_axis_label=label,
        height=420,
        sizing_mode="stretch_both",
        toolbar_location="above",
    )

    def draw_box(category: str, vals: list[float], color: str):
        if not vals:
            return
        q1, q2, q3 = np.percentile(vals, [25, 50, 75])
        iqr = q3 - q1
        upper = min(q3 + 1.5 * iqr, max(vals))
        lower = max(q1 - 1.5 * iqr, min(vals))
        p.vbar(x=category, width=0.6, bottom=q1, top=q3,
               fill_color=color, line_color="black")
        p.segment(category, upper, category, q3, line_color="black")
        p.segment(category, lower, category, q1, line_color="black")
        p.rect(category, upper, 0.2, 0.0001, line_color="black")
        p.rect(category, lower, 0.2, 0.0001, line_color="black")
        p.scatter([category], [q2], size=8, color="black", marker="circle")

    draw_box("Original", orig_vals, Category10[10][0])
    draw_box("User", user_vals, Category10[10][1])

    if not orig_vals and not user_vals:
        p.title.text = f"No data available for '{label}'."

    p.legend.location = "top_right"
    return components(p)


# -------------------------------------------------
# HISTOGRAM
# -------------------------------------------------
def create_histogram(feature: str, table_data: List[list], index: int, parameter: str) -> Tuple[str, str]:
    ref_df = _load_reference_df()

    ref_vals = []
    if ref_df is not None and parameter in ref_df.columns:
        ref_vals = _clean(ref_df[parameter].tolist())

    user_vals = _clean([row[index] for row in table_data])

    p = figure(
        title=f"{feature} Fit for {parameter}",
        x_axis_label=parameter,
        y_axis_label="Density",
        height=420,
        sizing_mode="stretch_both",
        toolbar_location="above",
    )

    plotted = False
    if ref_vals:
        hist, edges = np.histogram(ref_vals, bins=25, density=True)
        p.quad(top=hist, bottom=0, left=edges[:-1], right=edges[1:],
               fill_color="#003f5c", line_color="white", alpha=0.6,
               legend_label="Original")

        x = np.linspace(min(ref_vals), max(ref_vals), 256)
        if feature == "Gaussian":
            mu, std = norm.fit(ref_vals)
            y = norm.pdf(x, mu, std)
            color = "#d45087"
        elif feature == "Log Normal":
            try:
                mu, sigma = np.mean(np.log(ref_vals)), np.std(np.log(ref_vals))
                y = lognorm.pdf(x, s=sigma, scale=np.exp(mu))
            except Exception:
                mu, std = norm.fit(ref_vals)
                y = norm.pdf(x, mu, std)
            color = "#a05195"
        else:
            lam = 1.0 / (np.mean(ref_vals) if np.mean(ref_vals) > 0 else 1.0)
            y = lam * np.exp(-lam * (x - min(ref_vals)))
            y[x < min(ref_vals)] = 0.0
            color = "#665191"

        p.line(x, y, line_width=2, color=color, legend_label=f"{feature} Fit")
        plotted = True

    if user_vals:
        uhist, uedges = np.histogram(user_vals, bins=25, density=True)
        p.quad(top=uhist, bottom=0, left=uedges[:-1], right=uedges[1:],
               fill_color="#ffa600", line_color="white", alpha=0.6,
               legend_label="User")
        plotted = True

    if not plotted:
        p.title.text = f"No data available for '{parameter}'."

    p.legend.location = "top_right"
    return components(p)


# -------------------------------------------------
# LIEDL SINGLE
# -------------------------------------------------
def create_liedl_scatter(user_Lmax: float | None):
    ref_df = _load_reference_df()
    sites, plumes, labels = [], [], []

    if ref_df is not None and {"Site No.", "Plume length[m]"}.issubset(ref_df.columns):
        sites = ref_df["Site No."].tolist()
        plumes = ref_df["Plume length[m]"].tolist()
        labels = ref_df["Site Unit"].tolist() if "Site Unit" in ref_df.columns else [str(s) for s in sites]

    p = figure(
        height=450,
        sizing_mode="stretch_both",
        x_axis_label="Site Number",
        y_axis_label="Plume Length (m)",
        title="User Plume Length vs Original Database",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
        active_drag="pan",
        active_scroll="wheel_zoom",
    )

    if sites and plumes:
        source = ColumnDataSource(data={"site": sites, "plume": plumes, "label": labels})
        p.scatter(x="site", y="plume", source=source, size=8, alpha=0.7, legend_label="Original Database Lmax")

        hover = HoverTool(
            tooltips=[("Site", "@label"), ("Site No.", "@site"), ("Plume Length", "@plume{0.0} m")],
            mode="mouse",
        )
        p.add_tools(hover)

    if user_Lmax is not None:
        p.scatter(x=[-1], y=[user_Lmax], size=12, legend_label="User Lmax")

    p.legend.location = "top_right"
    return components(p)


# -------------------------------------------------
# LIEDL MULTIPLE
# -------------------------------------------------
def create_liedl_multiple_plot(rows, selected_ids):
    selected_ids = {int(s) for s in selected_ids} if selected_ids else set()

    if not rows:
        p = figure(height=300, sizing_mode="stretch_both", title="No scenarios available")
        return components(p)

    site_ids = [r[0] for r in rows]
    M_vals = [r[1] for r in rows]
    alpha_vals = [r[2] for r in rows]
    gamma_vals = [r[3] for r in rows]
    C_ED_vals = [r[4] for r in rows]
    C_EA_vals = [r[5] for r in rows]
    Lmax_vals = [r[6] for r in rows]

    source = ColumnDataSource(
        data={
            "site": site_ids,
            "M": M_vals,
            "alpha_Tv": alpha_vals,
            "gamma": gamma_vals,
            "C_ED0": C_ED_vals,
            "C_EA0": C_EA_vals,
            "Lmax": Lmax_vals,
        }
    )

    p = figure(
        height=450,
        sizing_mode="stretch_both",
        x_axis_label="Scenario ID",
        y_axis_label="Plume Length Lmax (m)",
        title="Liedl et al. (2005) – Multiple Simulation",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
        active_drag="pan",
        active_scroll="wheel_zoom",
    )

    p.scatter(x="site", y="Lmax", source=source, size=8, alpha=0.7, legend_label="All scenarios")

    if selected_ids:
        sel_site = [r[0] for r in rows if int(r[0]) in selected_ids]
        sel_Lmax = [r[6] for r in rows if int(r[0]) in selected_ids]
        if sel_site:
            p.scatter(x=sel_site, y=sel_Lmax, size=12, legend_label="Selected")

    hover = HoverTool(
        tooltips=[
            ("Scenario ID", "@site"),
            ("Lmax", "@Lmax{0.0} m"),
            ("M", "@M{0.00} m"),
            ("α_Tv", "@alpha_Tv{0.0000} m"),
            ("γ", "@gamma{0.0}"),
            ("C_ED°", "@C_ED0{0.0} mg/L"),
            ("C_EA°", "@C_EA0{0.0} mg/L"),
        ],
        mode="mouse",
    )
    p.add_tools(hover)

    p.legend.location = "top_right"
    script, div = components(p)
    print("DEBUG multiple plot: script len =", len(script or ""), "div len =", len(div or ""))
    return script, div
