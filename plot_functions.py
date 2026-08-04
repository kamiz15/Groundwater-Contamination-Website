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
from bokeh.palettes import Blues256, Category10, RdYlGn11, Reds256
from bokeh.models import ColorBar, ColumnDataSource, CustomJSTickFormatter, HoverTool, LinearColorMapper, Title
from scipy.stats import norm, lognorm, expon

try:
    from scipy.ndimage import zoom as _nd_zoom
except Exception:  # pragma: no cover
    _nd_zoom = None


def _upsample_field(arr, ny: int = 240, nx: int = 480):
    """Bilinearly upsample a coarse 2-D field for a smooth render (DISPLAY ONLY).

    Mirrors numerical_models._display_field: it does not affect plume length,
    the C0 contour, or hover values (those use the raw grid). Falls back to the
    raw array when scipy is unavailable or the grid is already fine.
    """
    a = np.asarray(arr, dtype=float)
    if _nd_zoom is None or a.ndim != 2:
        return a
    fy = max(1, int(round(ny / max(a.shape[0], 1))))
    fx = max(1, int(round(nx / max(a.shape[1], 1))))
    if fy == 1 and fx == 1:
        return a
    return _nd_zoom(a, (fy, fx), order=1)

# -------------------------------------------------
# Lazy, robust loader for the reference CSV
# -------------------------------------------------
_REF_DF: Optional[pd.DataFrame] = None
_REF_DF_RESOLVED = False  # caches the *miss* too, so a missing CSV is not re-scanned per request


def _load_reference_df() -> Optional[pd.DataFrame]:
    """Try to load the original reference CSV. Returns None if not found."""
    global _REF_DF, _REF_DF_RESOLVED
    if _REF_DF_RESOLVED:
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
                _REF_DF_RESOLVED = True
                print(f"[plot_functions] Loaded reference CSV from: {p}")
                return _REF_DF
            except Exception as e:
                print(f"[plot_functions] Failed to read {p}: {e}")
    print("[plot_functions] WARNING: reference CSV not found. Plots will use only user data.")
    _REF_DF = None
    _REF_DF_RESOLVED = True
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
        fig.colorbar(contourf_obj, ax=ax, label="Contaminant Concentration C_c [mg/L]")

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

    ax.set_xlim(0, L_D)
    ax.set_ylim(0, A_T)
    ax.set_xlabel("Distance Lx [m]")
    ax.set_ylabel("Aquifer Thickness T_A [m]")
    ax.set_title("Contaminant Plume - Vertical Model")
    ax.legend(loc="upper right", fontsize=8)
    fig.tight_layout()
    return fig


def plot_vertical_plume_interactive(C, x_grid, z_grid, L_max_n, L_D, S_T, R_Ta, R_Tb, A_T, c0=None):
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
        y_axis_label="Aquifer Thickness T_A [m]",
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
    p.add_layout(ColorBar(color_mapper=mapper, label_standoff=8, title="Contaminant Concentration C_c [mg/L]"), "right")
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

            if c0 is not None:
                threshold_level = float(c0)
            else:
                x_idx = int(np.argmin(np.abs(x_grid - L_max_n)))
                z_idx = int(np.argmin(np.abs(z_grid - (R_Tb + S_T / 2.0))))
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
                    p.multi_line(txs, tys, color="purple", line_width=3.0, alpha=0.95, legend_label="Plume boundary (C_c = 0)")
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


    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    return p


def plot_horizontal_plume_interactive(C, x_grid, y_grid, L_max_h, L_D, Sw, A_W, c0=None):
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
    p.add_layout(ColorBar(color_mapper=mapper, label_standoff=8, title="Contaminant Concentration C_c [mg/L]"), "right")
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

    if c0 is not None and finite.size and c_min < float(c0) < c_max:
        bfig, bax = plt.subplots()
        try:
            bobj = bax.contour(x_grid, y_grid, C, levels=[float(c0)])
            bxs, bys = [], []
            for segs in bobj.allsegs:
                for seg in segs:
                    if len(seg) >= 2:
                        bxs.append(seg[:, 0].tolist())
                        bys.append(seg[:, 1].tolist())
            if bxs:
                p.multi_line(bxs, bys, color="purple", line_width=3.0, alpha=0.95,
                             legend_label="Plume boundary (C_c = 0)")
        finally:
            plt.close(bfig)

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


    p.legend.location = "top_right"
    p.legend.click_policy = "hide"
    return p


def _reactive_ca_cd_fields(concentration, ca, cd, gamma):
    """Return display-only Ca/Cd fields from the raw numerical concentration."""
    c0 = float(ca)
    gamma = float(gamma)
    concentration = np.asarray(concentration, dtype=float)
    ca_field = np.where(concentration < c0, c0 - concentration, np.nan)
    cd_field = np.where(concentration > c0, (concentration - c0) / gamma, np.nan)
    ca_field = np.clip(ca_field, 0.0, float(ca))
    cd_field = np.clip(cd_field, 0.0, float(cd))
    return ca_field, cd_field


def _contour_segments(x_grid, cross_grid, concentration, level):
    finite = concentration[np.isfinite(concentration)]
    if not finite.size or not (float(np.nanmin(finite)) < float(level) < float(np.nanmax(finite))):
        return [], []
    fig, ax = plt.subplots()
    try:
        contour = ax.contour(x_grid, cross_grid, concentration, levels=[float(level)])
        xs, ys = [], []
        for level_segments in contour.allsegs:
            for segment in level_segments:
                if len(segment) >= 2:
                    xs.append(segment[:, 0].tolist())
                    ys.append(segment[:, 1].tolist())
        return xs, ys
    finally:
        plt.close(fig)


def _contour_segments_from_extent(concentration, level, extent):
    finite = concentration[np.isfinite(concentration)]
    if not finite.size or not (float(np.nanmin(finite)) < float(level) < float(np.nanmax(finite))):
        return [], []
    fig, ax = plt.subplots()
    try:
        contour = ax.contour(concentration, levels=[float(level)], extent=extent)
        xs, ys = [], []
        for level_segments in contour.allsegs:
            for segment in level_segments:
                if len(segment) >= 2:
                    xs.append(segment[:, 0].tolist())
                    ys.append(segment[:, 1].tolist())
        return xs, ys
    finally:
        plt.close(fig)


def _cell_edge_extent(grid, fallback_extent):
    grid = np.asarray(grid, dtype=float)
    if len(grid) > 1:
        if np.isclose(float(grid[0]), 0.0):
            return 0.0, float(fallback_extent)
        step = float(np.median(np.diff(grid)))
        return float(grid[0] - step / 2.0), float(grid[-1] + step / 2.0)
    if len(grid) == 1:
        center = float(grid[0])
        return center - 0.5, center + 0.5
    return 0.0, float(fallback_extent)


def _hover_grid_source(x_grid, cross_grid, ca_field, cd_field, concentration):
    xx, yy = np.meshgrid(x_grid, cross_grid)
    return ColumnDataSource(data={
        "x": xx.ravel(),
        "y": yy.ravel(),
        "ca": np.nan_to_num(ca_field, nan=0.0).ravel(),
        "cd": np.nan_to_num(cd_field, nan=0.0).ravel(),
        "conc": np.asarray(concentration, dtype=float).ravel(),
    })


def plot_reactive_plume_interactive(
    concentration,
    x_grid,
    cross_grid,
    *,
    ca,
    cd,
    gamma,
    plume_length,
    domain_length,
    cross_extent,
    orientation,
    source_extent=None,
    footer_meta=None,
):
    """Interactive Ca/Cd numerical plume view matching the static report transform."""
    concentration = np.asarray(concentration, dtype=float)
    x_grid = np.asarray(x_grid, dtype=float)
    cross_grid = np.asarray(cross_grid, dtype=float)
    if concentration.shape != (len(cross_grid), len(x_grid)):
        raise ValueError("Concentration grid dimensions do not match the numerical axes.")

    is_vertical = orientation == "vertical"
    cross_label = "Depth [m]" if is_vertical else "Horizontal Width [m]"
    title = None if is_vertical else "Contaminant Plume \u2014 Horizontal Model (Plan View)"
    plot_x0, plot_x1 = (0.0, float(domain_length)) if is_vertical else _cell_edge_extent(x_grid, domain_length)
    plot_y0, plot_y1 = (0.0, float(cross_extent)) if is_vertical else _cell_edge_extent(cross_grid, cross_extent)
    plot_width = plot_x1 - plot_x0
    plot_height = plot_y1 - plot_y0
    y_range = (float(cross_extent), 0.0) if is_vertical else (plot_y0, plot_y1)
    ca_field, cd_field = _reactive_ca_cd_fields(concentration, ca, cd, gamma)

    p = figure(
        title=title,
        x_axis_label="Distance [m]" if is_vertical else "Distance Lx [m]",
        y_axis_label=cross_label,
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
        active_drag="pan",
        active_scroll="wheel_zoom",
        sizing_mode="stretch_width",
        height=350 if is_vertical else 430,
        x_range=(plot_x0, plot_x1),
        y_range=y_range,
    )
    if is_vertical:
        p.background_fill_color = "#eef1f5"
        p.border_fill_color = "#eef1f5"
        p.outline_line_color = "#cbd5e1"
        p.outline_line_width = 1
        p.min_border_left = 70
        p.min_border_right = 20
        p.min_border_bottom = 55
        p.axis.axis_label_text_color = "#334155"
        p.axis.axis_label_text_font_style = "bold"
        p.axis.major_label_text_color = "#475569"

    ca_palette = list(reversed(Blues256))
    cd_palette = list(reversed(Reds256))
    ca_mapper = LinearColorMapper(palette=ca_palette, low=0.0, high=float(ca), nan_color="rgba(255,255,255,0)")
    cd_mapper = LinearColorMapper(palette=cd_palette, low=0.0, high=float(cd), nan_color="rgba(255,255,255,0)")
    # Vertical orientation: the inverted y_range (cross_extent -> 0) already places
    # depth 0 (the shallow acceptor/source band) at the TOP. The field rows are stored
    # with row 0 = cross_grid[0] (shallowest), which Bokeh draws at data y=0, so it lands
    # at the top under the inverted axis. Do NOT also np.flipud here or the depth is
    # flipped twice and the source band would wrongly sink to the bottom.
    #
    # Render the raw per-cell field (no upsampling) so the layer bands stay distinct
    # and the colours do not blend, matching the reference script (vertical_W.py).
    ca_image, cd_image = ca_field, cd_field
    image_alpha = 0.92 if is_vertical else 1.0
    donor_alpha = 0.88 if is_vertical else 1.0
    p.image(image=[ca_image], x=plot_x0, y=plot_y0, dw=plot_width, dh=plot_height,
            color_mapper=ca_mapper, alpha=image_alpha)
    p.image(image=[cd_image], x=plot_x0, y=plot_y0, dw=plot_width, dh=plot_height,
            color_mapper=cd_mapper, alpha=donor_alpha)
    p.add_layout(ColorBar(color_mapper=ca_mapper, label_standoff=8,
                          title="Ca [mg/L]" if is_vertical else "C_a [mg/L]"), "right")
    p.add_layout(ColorBar(color_mapper=cd_mapper, label_standoff=8,
                          title="Cd [mg/L]" if is_vertical else "C_d [mg/L]"), "right")

    if is_vertical:
        cxs, cys = _contour_segments(x_grid, cross_grid, concentration, float(ca))
    else:
        cxs, cys = _contour_segments_from_extent(
            concentration,
            float(ca),
            [plot_x0, plot_x1, plot_y0, plot_y1],
        )
    if cxs:
        p.multi_line(cxs, cys, color="black", line_width=2.0, alpha=0.95)

    if float(plume_length) > 0:
        plume_label = f"Plume length = {plume_length:.2f} m"
        p.line([plume_length, plume_length], [plot_y0, plot_y1], color="black",
               line_dash="dashed", line_width=1.5, legend_label=plume_label)
        # Rotated in-plot label (both orientations), matching the static PDF.
        p.text(
            x=[max(float(plume_length) - plot_width * 0.012, plot_x0)],
            y=[plot_y0 + plot_height * 0.5],
            text=[f"L^n max = {plume_length:.2f} m"],
            angle=np.pi / 2.0,
            text_align="center",
            text_baseline="middle",
            text_color="black",
            text_font_size="8pt",
        )

    if is_vertical:
        # Source band on the left inflow face, spanning the full thickness except
        # the top cell (kept clean, as in the reference vertical_W.py / static PDF).
        top_offset = float(cross_extent) / max(len(cross_grid), 1)
        p.line([0.0, 0.0], [top_offset, float(cross_extent)], color="#7a0a0a",
               line_width=7, legend_label="CD source")
        p.text(x=[float(domain_length) * 0.012], y=[(top_offset + float(cross_extent)) / 2.0],
               text=["CD (ST)"], text_color="#7a0a0a", text_font_size="8pt",
               text_align="left", text_baseline="middle")
        # Acceptor label near the top (shallow) band.
        p.text(x=[float(domain_length) * 0.5], y=[float(cross_extent) * 0.06],
               text=["CA"], text_color="navy", text_font_size="10pt",
               text_align="center", text_baseline="top")
    else:
        width = float(source_extent) if source_extent is not None else float(cross_extent)
        source_y0 = max((float(cross_extent) - width) / 2.0, 0.0)
        source_y1 = min((float(cross_extent) + width) / 2.0, float(cross_extent))
        p.line([0.0, 0.0], [source_y0, source_y1], color="#7a0a0a",
               line_width=7)
        p.text(x=[plot_x0 + plot_width * 0.012], y=[(source_y0 + source_y1) / 2.0],
               text=["CD (Sw)"], text_color="#7a0a0a", text_font_size="8pt",
               text_align="left", text_baseline="middle")
        p.text(x=[plot_x0 + plot_width * 0.5], y=[plot_y0 + plot_height * 0.95],
               text=["CA"], text_color="navy", text_font_size="10pt",
               text_align="center", text_baseline="top")

    hover_source = _hover_grid_source(x_grid, cross_grid, ca_field, cd_field, concentration)
    dx = plot_width / max(concentration.shape[1], 1)
    dy = plot_height / max(concentration.shape[0], 1)
    hover_renderer = p.rect(
        "x", "y", width=dx, height=dy, source=hover_source,
        fill_alpha=0.001, line_alpha=0.0,
    )
    p.add_tools(HoverTool(
        renderers=[hover_renderer],
        tooltips=[
            ("Distance", "@x{0.00} m"),
            ("Depth" if is_vertical else "Width", "@y{0.00} m"),
            ("Raw concentration", "@conc{0.000} mg/L"),
            ("CA", "@ca{0.000} mg/L"),
            ("CD", "@cd{0.000} mg/L"),
        ],
    ))
    p.grid.grid_line_alpha = 0.0 if is_vertical else 0.25
    if p.legend:
        p.legend.location = "top_right"
        p.legend.click_policy = "hide"
        if is_vertical:
            p.legend.background_fill_color = "#eef1f5"
            p.legend.background_fill_alpha = 0.9
            p.legend.border_line_color = "#cbd5e1"
            p.legend.label_text_color = "#334155"
    # Metadata footer (L_D, grid, porosity, K, gradient, Peclet, Courant) below the
    # plot, mirroring the static PDF caption.
    if footer_meta:
        p.add_layout(Title(text=str(footer_meta), text_font_size="8pt",
                           text_font_style="normal", text_color="#6b7280"), "below")
    return p


def _mask_concentration_to_fraction(concentration, x_grid, c0, fraction, plume_length, domain_length):
    """Return a copy of the concentration field with everything downstream of
    ``fraction * plume_length`` blanked to ``c0`` (background). Blanking to the
    background concentration c0 keeps both reactive fields (Ca where C<c0, Cd
    where C>c0) empty there, so the plume visibly "grows" from x=0 outward as
    the fraction increases without re-running the simulation."""
    concentration = np.asarray(concentration, dtype=float)
    x_grid = np.asarray(x_grid, dtype=float)
    frac = float(np.clip(fraction, 0.0, 1.0))
    # When a plume length is available, sweep along it; otherwise sweep the
    # whole domain so the field still builds up for degenerate (zero-length) runs.
    sweep_len = float(plume_length) if float(plume_length) > 0 else float(domain_length)
    cutoff = frac * sweep_len
    masked = concentration.copy()
    downstream = x_grid > cutoff
    if downstream.any():
        masked[:, downstream] = float(c0)
    return masked


def plot_reactive_plume_growth_frame(
    concentration,
    x_grid,
    cross_grid,
    *,
    ca,
    cd,
    gamma,
    plume_length,
    domain_length,
    cross_extent,
    orientation,
    fraction,
    source_extent=None,
    footer_meta=None,
):
    """Build one frame of the plume-growth animation.

    Reuses :func:`plot_reactive_plume_interactive` (same orientation handling,
    colour mappers and overlays) on an already-computed concentration field that
    has been masked to the requested ``fraction`` of the plume length. The
    dashed plume-length line / contour sweep along too because the masked field
    no longer exceeds ``c0`` downstream of the cutoff. Nothing is re-simulated.
    """
    frac = float(np.clip(fraction, 0.0, 1.0))
    c0 = float(ca)
    masked = _mask_concentration_to_fraction(
        concentration, x_grid, c0, frac, plume_length, domain_length
    )
    swept_length = frac * float(plume_length)
    return plot_reactive_plume_interactive(
        masked,
        x_grid,
        cross_grid,
        ca=ca,
        cd=cd,
        gamma=gamma,
        plume_length=swept_length,
        domain_length=domain_length,
        cross_extent=cross_extent,
        orientation=orientation,
        source_extent=source_extent,
        footer_meta=footer_meta,
    )


def _numerical_view_arrays(C, x_grid, cross_grid):
    C = np.asarray(C, dtype=float)
    x_grid = np.asarray(x_grid, dtype=float)
    cross_grid = np.asarray(cross_grid, dtype=float)
    if C.shape != (len(cross_grid), len(x_grid)):
        raise ValueError("Concentration grid dimensions do not match the numerical view axes.")
    return C, x_grid, cross_grid


def plot_concentration_profile_interactive(C, x_grid, cross_grid, *, cross_axis_label, title):
    """Average a retained numerical result across its transverse axis."""
    C, x_grid, _ = _numerical_view_arrays(C, x_grid, cross_grid)
    with np.errstate(invalid="ignore"):
        profile = np.nanmean(C, axis=0)
    source = ColumnDataSource(data={"x": x_grid, "concentration": profile})
    p = figure(
        title=f"{title} - Mean Concentration Profile",
        x_axis_label="Distance Lx [m]",
        y_axis_label="Mean Contaminant Concentration C_c [mg/L]",
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
        active_drag="pan",
        active_scroll="wheel_zoom",
        sizing_mode="stretch_width",
        height=340,
    )
    p.line("x", "concentration", source=source, color="#0d766e", line_width=3)
    p.scatter("x", "concentration", source=source, color="#0d766e", size=5, alpha=0.7)
    p.add_tools(HoverTool(tooltips=[("Distance", "@x{0.00} m"), ("Mean concentration", "@concentration{0.000} mg/L")]))
    p.grid.grid_line_alpha = 0.25
    return p


def plot_concentration_gradient_vectors_interactive(C, x_grid, cross_grid, *, cross_axis_label, title):
    """Show decreasing-concentration vectors derived from a retained numerical result."""
    C, x_grid, cross_grid = _numerical_view_arrays(C, x_grid, cross_grid)
    dcross, dx = np.gradient(C, cross_grid, x_grid, edge_order=1)
    u = -dx
    v = -dcross
    magnitude = np.hypot(u, v)

    row_step = max(int(np.ceil(len(cross_grid) / 14)), 1)
    col_step = max(int(np.ceil(len(x_grid) / 24)), 1)
    rows = np.arange(0, len(cross_grid), row_step)
    cols = np.arange(0, len(x_grid), col_step)
    xx, yy = np.meshgrid(x_grid[cols], cross_grid[rows])
    uu = u[np.ix_(rows, cols)]
    vv = v[np.ix_(rows, cols)]
    mm = magnitude[np.ix_(rows, cols)]

    finite_nonzero = np.isfinite(mm) & (mm > 0)
    safe_mm = np.where(finite_nonzero, mm, 1.0)
    x_scale = (float(x_grid.max()) - float(x_grid.min())) / max(len(cols), 1) * 0.65
    y_scale = (float(cross_grid.max()) - float(cross_grid.min())) / max(len(rows), 1) * 0.65
    x1 = xx + np.where(finite_nonzero, uu / safe_mm, 0.0) * x_scale
    y1 = yy + np.where(finite_nonzero, vv / safe_mm, 0.0) * y_scale
    angle = np.arctan2(y1 - yy, x1 - xx) - (np.pi / 2.0)

    source = ColumnDataSource(data={
        "x0": xx.ravel(),
        "y0": yy.ravel(),
        "x1": x1.ravel(),
        "y1": y1.ravel(),
        "angle": angle.ravel(),
        "magnitude": mm.ravel(),
    })
    p = figure(
        title=f"{title} - Decreasing-Concentration Vector View",
        x_axis_label="Distance Lx [m]",
        y_axis_label=cross_axis_label,
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
        active_drag="pan",
        active_scroll="wheel_zoom",
        sizing_mode="stretch_width",
        height=430,
        x_range=(float(x_grid.min()), float(x_grid.max())),
        y_range=(float(cross_grid.min()), float(cross_grid.max())),
    )
    finite = C[np.isfinite(C)]
    c_min = float(np.nanmin(finite)) if finite.size else 0.0
    c_max = float(np.nanmax(finite)) if finite.size else 1.0
    if c_min == c_max:
        c_max = c_min + 1.0
    mapper = LinearColorMapper(palette=list(reversed(RdYlGn11)), low=c_min, high=c_max)
    p.image(
        image=[np.flipud(C)],
        x=float(x_grid.min()),
        y=float(cross_grid.min()),
        dw=float(x_grid.max()) - float(x_grid.min()),
        dh=float(cross_grid.max()) - float(cross_grid.min()),
        color_mapper=mapper,
        alpha=0.45,
    )
    p.segment("x0", "y0", "x1", "y1", source=source, color="#163c66", line_width=1.4, alpha=0.8)
    p.scatter("x1", "y1", angle="angle", source=source, marker="triangle", color="#163c66", size=7, alpha=0.9)
    p.add_tools(HoverTool(tooltips=[("Gradient magnitude", "@magnitude{0.000}")]))
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
        y_axis_label="Plume Length L_p [m]",
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
        sizing_mode="stretch_width",
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
        p.title.text = "No data available for plume length."
        p.text(x=[0], y=[0], text=["No data available"], text_align="center")
    else:
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
        sizing_mode="stretch_width",
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
        p.text(x=["Original"], y=[0], text=["No data available"], text_align="center")

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
        sizing_mode="stretch_width",
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
        p.text(x=[0], y=[0], text=["No data available"], text_align="center")
    else:
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
        y_axis_label="Maximum Plume Length L_max [m]",
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


def plot_aem_field_interactive(
    result_array,
    xaxis,
    yaxis,
    l_max=None,
    *,
    ca=8.0,
    gamma=3.5,
    orientation="horizontal",
):
    """Interactive Bokeh view of an AEM transport concentration field.

    Renders ``result_array`` (2D field of shape (len(yaxis), len(xaxis))) as a
    Bokeh image with a diverging-style colour mapping: acceptor depletion is
    negative (blue), donor plume is positive (red). A dashed vertical line marks
    the plume length L_max, and a HoverTool exposes the underlying concentration.

    Styled to match :func:`plot_reactive_plume_interactive` (stretch width,
    light fills, ColorBar). Returns a Bokeh ``figure``.
    """
    result_array = np.asarray(result_array, dtype=float)
    xaxis = np.asarray(xaxis, dtype=float)
    yaxis = np.asarray(yaxis, dtype=float)
    if result_array.ndim != 2:
        raise ValueError("AEM result array must be 2D.")

    x0 = float(xaxis[0]) if xaxis.size else 0.0
    x1 = float(xaxis[-1]) if xaxis.size else float(result_array.shape[1])
    y0 = float(yaxis[0]) if yaxis.size else 0.0
    y1 = float(yaxis[-1]) if yaxis.size else float(result_array.shape[0])
    dw = max(x1 - x0, 1e-9)
    dh = max(y1 - y0, 1e-9)

    is_vertical = orientation == "vertical"
    cross_label = "Depth [m]" if is_vertical else "Cross-distance y [m]"

    p = figure(
        title="AEM Transport — Concentration Field",
        x_axis_label="Distance x [m]",
        y_axis_label=cross_label,
        tools="pan,wheel_zoom,box_zoom,reset,save",
        toolbar_location="above",
        active_drag="pan",
        active_scroll="wheel_zoom",
        sizing_mode="stretch_width",
        height=430,
        x_range=(x0, x1),
        y_range=(y0, y1),
    )
    p.background_fill_color = "#eef1f5"
    p.border_fill_color = "#eef1f5"
    p.outline_line_color = "#cbd5e1"
    p.outline_line_width = 1
    p.min_border_left = 70
    p.min_border_right = 20
    p.axis.axis_label_text_color = "#334155"
    p.axis.axis_label_text_font_style = "bold"
    p.axis.major_label_text_color = "#475569"

    finite = result_array[np.isfinite(result_array)]
    max_val = float(np.max(finite)) if finite.size else 0.0
    min_val = float(np.min(finite)) if finite.size else 0.0
    abs_min = abs(min_val)

    # Coordinate vectors for the contour grid (z has shape (ny, nx)).
    cny, cnx = result_array.shape
    cx = xaxis if xaxis.size == cnx else np.linspace(x0, x1, cnx)
    cy = yaxis if yaxis.size == cny else np.linspace(y0, y1, cny)

    # Independent donor / acceptor colour scaling, matching the matplotlib
    # reference (ATSimulation.plot_result):
    #   donor    C > 0  -> 'Reds'    over [0, max_val]   (11 levels, 10 bands)
    #   acceptor C < 0  -> 'Blues_r' over [-abs_min, 0]  (9 levels,  8 bands)
    # Reds256/Blues256 run light->dark; reversing Blues256 reproduces 'Blues_r'
    # so the most negative value is darkest and the zero edge is lightest. Each
    # side is normalised to its own extreme, exactly as the two contourf calls.
    def _sample(palette, n):
        idx = np.linspace(0, len(palette) - 1, n).round().astype(int)
        return [palette[int(i)] for i in idx]

    if max_val > 0:
        donor_levels = list(np.linspace(0, max_val, 11))
        donor_r = p.contour(
            cx, cy, result_array, donor_levels,
            fill_color=_sample(list(Reds256), len(donor_levels) - 1))
        p.add_layout(
            donor_r.construct_color_bar(
                title="Electron donor concentration [mg/L]", label_standoff=8),
            "right")

    if abs_min > 0:
        acceptor_levels = list(np.linspace(-abs_min, 0, 9))
        acceptor_r = p.contour(
            cx, cy, result_array, acceptor_levels,
            fill_color=_sample(list(reversed(Blues256)), len(acceptor_levels) - 1))
        p.add_layout(
            acceptor_r.construct_color_bar(
                title="Electron acceptor concentration [mg/L]", label_standoff=8,
                formatter=CustomJSTickFormatter(
                    code="return Math.abs(tick).toFixed(0)")),
            "right")

    # Zero-concentration contour = donor/acceptor interface (plume envelope),
    # drawn as a solid black line just as in the matplotlib reference.
    if max_val > 0 and abs_min > 0:
        p.contour(cx, cy, result_array, [0.0], line_color="black", line_width=2)

    if l_max is not None and float(l_max) > x0:
        plume_label = f"L_max = {float(l_max):.1f} m"
        p.line([float(l_max), float(l_max)], [y0, y1], color="black",
               line_dash="dashed", line_width=1.8, legend_label=plume_label)

    # Hover layer over the field.
    nx = result_array.shape[1]
    ny = result_array.shape[0]
    gx = np.linspace(x0, x1, nx) if nx > 1 else np.array([x0])
    gy = np.linspace(y0, y1, ny) if ny > 1 else np.array([y0])
    mesh_x, mesh_y = np.meshgrid(gx, gy)
    hover_source = ColumnDataSource(data={
        "x": mesh_x.ravel(),
        "y": mesh_y.ravel(),
        "conc": result_array.ravel(),
    })
    cell_w = dw / max(nx, 1)
    cell_h = dh / max(ny, 1)
    hover_renderer = p.rect(
        "x", "y", width=cell_w, height=cell_h, source=hover_source,
        fill_alpha=0.001, line_alpha=0.0,
    )
    p.add_tools(HoverTool(
        renderers=[hover_renderer],
        tooltips=[
            ("Distance x", "@x{0.00} m"),
            ("Depth" if is_vertical else "y", "@y{0.00} m"),
            ("Concentration", "@conc{0.000} mg/L"),
        ],
    ))
    p.grid.grid_line_alpha = 0.15
    if l_max is not None and float(l_max) > x0:
        p.legend.location = "top_right"
        p.legend.click_policy = "hide"
        p.legend.background_fill_color = "#eef1f5"
        p.legend.background_fill_alpha = 0.9
        p.legend.border_line_color = "#cbd5e1"
        p.legend.label_text_color = "#334155"
    return p
