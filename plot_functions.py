# plot_functions.py — unified, clean version (Bokeh + CSV fallback)

from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Tuple, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.palettes import Category10, RdYlGn11
from bokeh.models import ColorBar, ColumnDataSource, HoverTool, LinearColorMapper, Span
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


def plot_vertical_plume_contour(C, x_grid, z_grid, L_max_n, L_D, S_T, R_Ta, R_Tb, A_T, delta_x, C_D, C_A):
    """Create the vertical numerical plume contour plot used by the Panel numerical apps."""
    C = np.asarray(C, dtype=float)
    x_grid = np.asarray(x_grid, dtype=float)
    z_grid = np.asarray(z_grid, dtype=float)

    fig, ax = plt.subplots(figsize=(10, 5))
    finite = C[np.isfinite(C)]
    if finite.size == 0 or np.nanmin(finite) == np.nanmax(finite):
        ax.imshow(
            np.nan_to_num(C),
            extent=[float(x_grid.min()), float(x_grid.max()), float(z_grid.min()), float(z_grid.max())],
            origin="lower",
            aspect="auto",
            cmap="RdYlGn_r",
        )
    else:
        levels = np.linspace(float(np.nanmin(finite)), float(np.nanmax(finite)), 15)
        contourf_obj = ax.contourf(x_grid, z_grid, C, levels=levels, cmap="RdYlGn_r")
        ax.contour(x_grid, z_grid, C, levels=levels, colors="black", linewidths=0.5, alpha=0.6)

        x_idx = int(np.argmin(np.abs(x_grid - L_max_n)))
        source_mid_z = R_Tb + (S_T / 2.0)
        z_idx = int(np.argmin(np.abs(z_grid - source_mid_z)))
        threshold_level = float(C[z_idx, x_idx])
        if np.isfinite(threshold_level) and float(np.nanmin(finite)) < threshold_level < float(np.nanmax(finite)):
            ax.contour(x_grid, z_grid, C, levels=[threshold_level], colors="purple", linewidths=2.5)
        fig.colorbar(contourf_obj, ax=ax, label="Concentration [mg/L]")

    # Source zone rectangles — width = delta_x (first grid column only)
    sw = float(delta_x)
    # R_Tb zone (bottom buffer) — solid dark blue, alpha 0.3
    ax.fill_betweenx([0, R_Tb], 0, sw, color="#2C3E7A", alpha=0.3)
    # S_T zone (active source) — solid dark red, alpha 0.85, no hatch
    ax.fill_betweenx(
        [R_Tb, R_Tb + S_T],
        0,
        sw,
        color="#8B1A1A",
        alpha=0.85,
        label="Active source zone",
    )
    # R_Ta zone (top buffer) — solid dark blue, alpha 0.3
    ax.fill_betweenx([R_Tb + S_T, A_T], 0, sw, color="#2C3E7A", alpha=0.3)

    # Boundary condition annotations — left boundary (vertical text inside source column)
    label_x = sw / 2.0
    if R_Ta > 0:
        ax.text(label_x, R_Tb + S_T + R_Ta / 2.0, "Reactant Conc. (C_A)",
                rotation=90, ha="center", va="center", color="blue", fontsize=7, clip_on=True)
    ax.text(label_x, R_Tb + S_T / 2.0, "Source Conc. (C_D)",
            rotation=90, ha="center", va="center", color="#8B1A1A", fontsize=7, clip_on=True)
    if R_Tb > 0:
        ax.text(label_x, R_Tb / 2.0, "Reactant Conc. (C_A)",
                rotation=90, ha="center", va="center", color="blue", fontsize=7, clip_on=True)

    # Top boundary
    ax.text(L_D / 2.0, A_T * 0.98, "C_A",
            rotation=0, ha="center", va="top", color="blue", fontsize=9)
    # Right boundary
    ax.text(L_D * 0.97, A_T / 2.0, "C_A",
            rotation=90, ha="right", va="center", color="blue", fontsize=9)
    # Bottom boundary
    ax.text(L_D / 2.0, A_T * 0.02, "Confined aquifer bottom",
            rotation=0, ha="center", va="bottom", color="grey", fontsize=8)

    ax.axvline(x=L_max_n, color="navy", linestyle="--", linewidth=1.5, label=f"L_max^n = {L_max_n:.1f} m")
    ax.axvline(x=L_D, color="grey", linestyle=":", linewidth=1.2, label=f"LD = {L_D:.1f} m")
    ax.set_xlim(0, L_D)
    ax.set_ylim(0, A_T)
    ax.set_xlabel("Distance Lx [m]")
    ax.set_ylabel("Aquifer Thickness [m]")
    ax.set_title("Contaminant Plume - Vertical Model")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    return fig


def plot_vertical_plume_interactive(C, x_grid, z_grid, L_max_n, L_D, S_T, R_Ta, R_Tb, A_T):
    """Create an interactive Bokeh version of the vertical numerical plume contour plot."""
    C = np.asarray(C, dtype=float)
    x_grid = np.asarray(x_grid, dtype=float)
    z_grid = np.asarray(z_grid, dtype=float)
    finite = C[np.isfinite(C)]
    c_min = float(np.nanmin(finite)) if finite.size else 0.0
    c_max = float(np.nanmax(finite)) if finite.size else 1.0
    if c_min == c_max:
        c_max = c_min + 1.0

    p = figure(
        title="Contaminant Plume - Vertical Model",
        x_axis_label="Distance Lx [m]",
        y_axis_label="Aquifer Thickness [m]",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
        active_drag="pan",
        active_scroll="wheel_zoom",
        sizing_mode="stretch_width",
        height=430,
        x_range=(0, L_D),
        y_range=(0, A_T),
    )

    mapper = LinearColorMapper(palette=list(reversed(RdYlGn11)), low=c_min, high=c_max)
    image_renderer = p.image(
        image=[np.flipud(C)],
        x=0,
        y=0,
        dw=L_D,
        dh=A_T,
        color_mapper=mapper,
        alpha=0.95,
    )
    p.add_layout(ColorBar(color_mapper=mapper, label_standoff=8, title="Concentration [mg/L]"), "right")
    p.add_tools(
        HoverTool(
            renderers=[image_renderer],
            tooltips=[("Distance", "$x{0.0} m"), ("Aquifer thickness", "$y{0.00} m")],
        )
    )

    levels = np.linspace(c_min, c_max, 15)
    if finite.size and c_min < c_max:
        contour_fig, contour_ax = plt.subplots()
        try:
            contour_obj = contour_ax.contour(x_grid, z_grid, C, levels=levels)
            xs, ys = [], []
            for level_segments in contour_obj.allsegs:
                for segment in level_segments:
                    if len(segment) >= 2:
                        xs.append(segment[:, 0].tolist())
                        ys.append(segment[:, 1].tolist())
            if xs:
                p.multi_line(xs, ys, color="black", line_width=0.8, alpha=0.55)

            x_idx = int(np.argmin(np.abs(x_grid - L_max_n)))
            source_mid_z = R_Tb + (S_T / 2.0)
            z_idx = int(np.argmin(np.abs(z_grid - source_mid_z)))
            threshold_level = float(C[z_idx, x_idx])
            if np.isfinite(threshold_level) and c_min < threshold_level < c_max:
                threshold_obj = contour_ax.contour(x_grid, z_grid, C, levels=[threshold_level])
                txs, tys = [], []
                for level_segments in threshold_obj.allsegs:
                    for segment in level_segments:
                        if len(segment) >= 2:
                            txs.append(segment[:, 0].tolist())
                            tys.append(segment[:, 1].tolist())
                if txs:
                    p.multi_line(txs, tys, color="purple", line_width=3.0, alpha=0.95, legend_label="L_max^n boundary")
        finally:
            plt.close(contour_fig)

    source_width = float(x_grid[1] - x_grid[0]) if len(x_grid) > 1 else max(float(L_D) * 0.02, 1.0)
    source_width = max(source_width, float(L_D) * 0.015)
    p.quad(
        left=0,
        right=source_width,
        bottom=0,
        top=R_Tb,
        color="#d1d5db",
        alpha=0.45,
        line_color="#6b7280",
        legend_label="Source buffer",
    )
    p.quad(
        left=0,
        right=source_width,
        bottom=R_Tb,
        top=R_Tb + S_T,
        color="#f97316",
        alpha=0.65,
        line_color="#9a3412",
        legend_label="Active source zone",
    )
    p.quad(
        left=0,
        right=source_width,
        bottom=R_Tb + S_T,
        top=A_T,
        color="#d1d5db",
        alpha=0.45,
        line_color="#6b7280",
    )

    lmax_span = Span(location=L_max_n, dimension="height", line_color="navy", line_dash="dashed", line_width=2)
    ld_span = Span(location=L_D, dimension="height", line_color="grey", line_dash="dotted", line_width=2)
    p.add_layout(lmax_span)
    p.add_layout(ld_span)
    p.line([L_max_n, L_max_n], [0, A_T], color="navy", line_dash="dashed", line_width=2, legend_label=f"L_max^n = {L_max_n:.1f} m")
    p.line([L_D, L_D], [0, A_T], color="grey", line_dash="dotted", line_width=2, legend_label=f"LD = {L_D:.1f} m")

    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    return p


def plot_horizontal_plume_interactive(C, x_grid, y_grid, L_max_h, L_D, Sw, A_W):
    """Interactive Bokeh plan-view (horizontal) plume contour plot."""
    C = np.asarray(C, dtype=float)
    x_grid = np.asarray(x_grid, dtype=float)
    y_grid = np.asarray(y_grid, dtype=float)
    finite = C[np.isfinite(C)]
    c_min = float(np.nanmin(finite)) if finite.size else 0.0
    c_max = float(np.nanmax(finite)) if finite.size else 1.0
    if c_min == c_max:
        c_max = c_min + 1.0

    p = figure(
        title="Contaminant Plume \u2014 Horizontal Model (Plan View)",
        x_axis_label="Distance Lx [m]",
        y_axis_label="Horizontal Width [m]",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
        active_drag="pan",
        active_scroll="wheel_zoom",
        sizing_mode="stretch_width",
        height=430,
        x_range=(0, L_D),
        y_range=(0, A_W),
    )

    mapper = LinearColorMapper(palette=list(reversed(RdYlGn11)), low=c_min, high=c_max)
    img_renderer = p.image(
        image=[np.flipud(C)],
        x=0, y=0, dw=L_D, dh=A_W,
        color_mapper=mapper, alpha=0.95,
    )
    p.add_layout(ColorBar(color_mapper=mapper, label_standoff=8, title="Concentration [mg/L]"), "right")
    p.add_tools(HoverTool(
        renderers=[img_renderer],
        tooltips=[("Distance", "$x{0.0} m"), ("Width", "$y{0.00} m")],
    ))

    # Contour lines
    levels = np.linspace(c_min, c_max, 15)
    if finite.size and c_min < c_max:
        cfig, cax = plt.subplots()
        try:
            cobj = cax.contour(x_grid, y_grid, C, levels=levels)
            xs, ys = [], []
            for segs in cobj.allsegs:
                for seg in segs:
                    if len(seg) >= 2:
                        xs.append(seg[:, 0].tolist())
                        ys.append(seg[:, 1].tolist())
            if xs:
                p.multi_line(xs, ys, color="black", line_width=0.8, alpha=0.55)
        finally:
            plt.close(cfig)

    # Source strip centred in y
    source_y0 = (A_W - Sw) / 2.0
    source_y1 = (A_W + Sw) / 2.0
    src_w = float(x_grid[1] - x_grid[0]) if len(x_grid) > 1 else max(float(L_D) * 0.02, 1.0)
    src_w = max(src_w, float(L_D) * 0.015)

    if source_y0 > 0:
        p.quad(left=0, right=src_w, bottom=0, top=source_y0,
               color="#d1d5db", alpha=0.45, line_color="#6b7280", legend_label="Ambient zone")
    p.quad(left=0, right=src_w, bottom=source_y0, top=source_y1,
           color="#f97316", alpha=0.65, line_color="#9a3412", legend_label="Active source zone (Sw)")
    if source_y1 < A_W:
        p.quad(left=0, right=src_w, bottom=source_y1, top=A_W,
               color="#d1d5db", alpha=0.45, line_color="#6b7280")

    lmax_span = Span(location=L_max_h, dimension="height", line_color="navy", line_dash="dashed", line_width=2)
    ld_span = Span(location=L_D, dimension="height", line_color="grey", line_dash="dotted", line_width=2)
    p.add_layout(lmax_span)
    p.add_layout(ld_span)
    p.line([L_max_h, L_max_h], [0, A_W], color="navy", line_dash="dashed", line_width=2,
           legend_label=f"L_max^h = {L_max_h:.1f} m")
    p.line([L_D, L_D], [0, A_W], color="grey", line_dash="dotted", line_width=2,
           legend_label=f"L_D = {L_D:.1f} m")

    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    return p


def plot_numerical_vs_cirpka_comparison(
    numerical_lmax_v: float,
    numerical_lmax_h: float,
    cirpka_lmax_val: float,
    liedl_lmax_val: float,
):
    """Bar chart comparing Liedl, Cirpka, vertical-numerical and horizontal-numerical Lmax."""
    labels = ["Liedl\nAnalytical", "Cirpka\nAnalytical", "Numerical\nVertical", "Numerical\nHorizontal"]
    values = [liedl_lmax_val, cirpka_lmax_val, numerical_lmax_v, numerical_lmax_h]
    colors = ["#3B82F6", "#0D9887", "#1B3A6B", "#2E6EBD"]

    source = ColumnDataSource(data={"labels": labels, "values": values, "colors": colors})

    p = figure(
        x_range=labels,
        title="Model Comparison \u2014 Plume Length L_max",
        x_axis_label="Model",
        y_axis_label="Plume Length [m]",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        sizing_mode="stretch_width",
        height=400,
        toolbar_location="above",
        active_drag="pan",
    )
    p.vbar(x="labels", top="values", width=0.55, source=source,
           color="colors", alpha=0.88, line_color="white", line_width=1.5)
    p.add_tools(HoverTool(tooltips=[("Model", "@labels"), ("L_max", "@values{0.00} m")]))
    p.y_range.start = 0
    p.xgrid.grid_line_color = None
    p.xaxis.major_label_text_font_size = "9pt"
    p.title.text_font_size = "11pt"
    return p


def plot_lmax_scatter(
    db_analytical_lmax,
    db_plume_lengths,
    numerical_lmax,
    analytical_lmax,
    avg_analytical_lmax,
    avg_db_plume_length,
    selected_site=None,
    numerical_runs=None,
):
    """Create the numerical-vs-analytical Lmax comparison plot."""
    db_analytical_lmax = _clean(db_analytical_lmax)
    db_plume_lengths = _clean(db_plume_lengths)
    numerical_runs = numerical_runs or [(analytical_lmax, numerical_lmax, "Numerical L\u2098\u2090\u2093\u207f")]

    p = figure(
        title="Numerical Model Plume Length Comparison",
        x_axis_label="Analytical L\u2098\u2090\u2093 [m]",
        y_axis_label="Numerical / Observed Plume Length [m]",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        sizing_mode="stretch_width",
        height=400,
        toolbar_location="above",
        active_drag="pan",
        active_scroll="wheel_zoom",
    )

    ref_candidates = db_analytical_lmax + db_plume_lengths
    for x_val, y_val, _label in numerical_runs:
        ref_candidates.extend(_clean([x_val, y_val]))
    if selected_site:
        ref_candidates.extend(_clean([selected_site.get("analytical_lmax"), selected_site.get("plume_length")]))
    ref_max = max(ref_candidates) * 1.1 if ref_candidates else 1.0
    p.line([0, ref_max], [0, ref_max], line_dash="dashed", line_color="lightgrey", line_width=1.5, legend_label="1:1 reference")

    if db_analytical_lmax and db_plume_lengths:
        pair_count = min(len(db_analytical_lmax), len(db_plume_lengths))
        db_source = ColumnDataSource(
            data={
                "x": db_analytical_lmax[:pair_count],
                "y": db_plume_lengths[:pair_count],
                "site": list(range(1, pair_count + 1)),
            }
        )
        db_renderer = p.scatter(
            "x",
            "y",
            source=db_source,
            size=7,
            marker="circle",
            color="#AED6F1",
            alpha=0.45,
            legend_label="Database plume length",
        )
        p.add_tools(
            HoverTool(
                renderers=[db_renderer],
                tooltips=[("Site index", "@site"), ("Analytical Lmax", "@x{0.0} m"), ("Plume length", "@y{0.0} m")],
            )
        )

    if avg_analytical_lmax is not None and avg_db_plume_length is not None:
        p.scatter(
            [avg_analytical_lmax],
            [avg_db_plume_length],
            size=14,
            marker="circle",
            color="#16803c",
            alpha=0.85,
            legend_label="Average site Lmax",
        )

    if selected_site is not None:
        p.scatter(
            [selected_site["analytical_lmax"]],
            [selected_site["plume_length"]],
            size=18,
            marker="cross",
            color="hotpink",
            line_width=3,
            legend_label="Selected site Lmax",
        )

    palette = ["#2E86C1", "#1B4F72", "#2874A6", "#5499C7", "#154360"]
    for idx, (x_val, y_val, label) in enumerate(numerical_runs):
        num_source = ColumnDataSource(data={"x": [x_val], "y": [y_val], "label": [label]})
        num_renderer = p.scatter(
            "x",
            "y",
            source=num_source,
            size=17,
            marker="triangle",
            color=palette[idx % len(palette)],
            alpha=0.95,
            legend_label=label,
        )
        p.add_tools(
            HoverTool(
                renderers=[num_renderer],
                tooltips=[("Run", "@label"), ("Analytical Lmax", "@x{0.0} m"), ("Numerical Lmax", "@y{0.0} m")],
            )
        )

    p.legend.location = "top_left"
    p.legend.click_policy = "hide"
    return p


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
