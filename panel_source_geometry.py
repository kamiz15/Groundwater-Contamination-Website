"""
panel_source_geometry.py — Panel app for regular source-shape forward modelling.

User defines a source as circle, ellipse, or line; the app fits source points
to the shape, maps the transverse extent to the Liedl M parameter, and runs
liedl_lmax to obtain the maximum plume length.  A Bokeh figure shows the source
outline, the fitted points, and the plume extent from each point.

Physics: Liedl et al. (2005) analytical forward model.
Geometry: source_geometry.fit_points_* + source_geometry.effective_source_width.
"""
from __future__ import annotations

import io
import math

import numpy as np
import panel as pn
from bokeh.plotting import figure

from analytical_models import liedl_lmax
from panel_analytical_common import (
    error_card,
    info_card,
    query_float,
    query_int,
    query_str,
    summary_card,
)
from pdf_report import CASTReport
from source_geometry import (
    auto_point_count_circle,
    auto_point_count_ellipse,
    auto_point_count_line,
    effective_source_width,
    fit_points_circle,
    fit_points_ellipse,
    fit_points_line,
)

pn.extension(sizing_mode="stretch_width")


def source_geometry_app():  # noqa: C901 — complexity is inherent in a multi-shape UI
    # ── Shape type selector ───────────────────────────────────────────────────
    shape_sel = pn.widgets.Select(
        name="Source Shape",
        options=["circle", "ellipse", "line"],
        value=query_str("shape", "circle"),
        sizing_mode="stretch_width",
    )

    # ── Circle parameters ─────────────────────────────────────────────────────
    cx_w = pn.widgets.FloatInput(name="Centre x [m]", value=query_float("cx", 0.0), step=1.0)
    cy_w = pn.widgets.FloatInput(name="Centre y [m]", value=query_float("cy", 0.0), step=1.0)
    radius_w = pn.widgets.FloatInput(
        name="Radius [m]", value=query_float("radius", 10.0), step=0.5, start=0.01
    )
    circle_col = pn.Column(
        pn.pane.HTML('<div style="font-weight:700;margin:10px 0 4px;color:#163c66;">Circle Parameters</div>'),
        cx_w, cy_w, radius_w,
        sizing_mode="stretch_width",
    )

    # ── Ellipse parameters ────────────────────────────────────────────────────
    semi_a_w = pn.widgets.FloatInput(
        name="Semi-axis a [m] — along flow", value=query_float("semi_a", 15.0), step=0.5, start=0.01
    )
    semi_b_w = pn.widgets.FloatInput(
        name="Semi-axis b [m] — transverse", value=query_float("semi_b", 8.0), step=0.5, start=0.01
    )
    angle_w = pn.widgets.FloatInput(
        name="Rotation angle θ [°]", value=query_float("angle_deg", 0.0), step=5.0
    )
    ellipse_col = pn.Column(
        pn.pane.HTML('<div style="font-weight:700;margin:10px 0 4px;color:#163c66;">Ellipse Parameters</div>'),
        semi_a_w, semi_b_w, angle_w,
        sizing_mode="stretch_width",
        visible=False,
    )

    # ── Line parameters ───────────────────────────────────────────────────────
    x1_w = pn.widgets.FloatInput(name="Start x₁ [m]", value=query_float("x1", -20.0), step=1.0)
    y1_w = pn.widgets.FloatInput(name="Start y₁ [m]", value=query_float("y1", -10.0), step=1.0)
    x2_w = pn.widgets.FloatInput(name="End x₂ [m]", value=query_float("x2", 20.0), step=1.0)
    y2_w = pn.widgets.FloatInput(name="End y₂ [m]", value=query_float("y2", 10.0), step=1.0)
    line_col = pn.Column(
        pn.pane.HTML('<div style="font-weight:700;margin:10px 0 4px;color:#163c66;">Line Parameters</div>'),
        x1_w, y1_w, x2_w, y2_w,
        sizing_mode="stretch_width",
        visible=False,
    )

    # ── Point count ───────────────────────────────────────────────────────────
    n_pts_w = pn.widgets.IntInput(
        name="Source points (0 = auto from size)",
        value=query_int("n_pts", 0),
        step=1,
        start=0,
        sizing_mode="stretch_width",
    )
    n_hint = pn.pane.HTML("", sizing_mode="stretch_width")

    # ── Physical parameters (Liedl) ───────────────────────────────────────────
    alpha_tv_w = pn.widgets.FloatInput(
        name="αTv — Transverse Dispersivity [m]",
        value=query_float("alpha_Tv", 0.001),
        step=0.0001,
        start=1e-9,
    )
    gamma_w = pn.widgets.FloatInput(
        name="γ — Stoichiometric Ratio [-]",
        value=query_float("gamma", 3.5),
        step=0.1,
    )
    c_ea0_w = pn.widgets.FloatInput(
        name="Cₐ — Electron Acceptor [mg/L]",
        value=query_float("C_EA0", 8.0),
        step=0.1,
        start=1e-9,
    )
    c_ed0_w = pn.widgets.FloatInput(
        name="Cₓ — Electron Donor [mg/L]",
        value=query_float("C_ED0", 5.0),
        step=0.1,
        start=1e-9,
    )

    run_btn = pn.widgets.Button(
        name="Run Forward Model",
        button_type="primary",
        sizing_mode="stretch_width",
    )
    result_pane = pn.pane.HTML(
        info_card("Define the source geometry and physical parameters, then click Run."),
        sizing_mode="stretch_width",
    )
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=480)

    _state: dict = {}

    # ── Dynamic shape-section visibility ──────────────────────────────────────
    def _on_shape_change(event):
        shape = event.new
        circle_col.visible = (shape == "circle")
        ellipse_col.visible = (shape == "ellipse")
        line_col.visible = (shape == "line")
        _refresh_hint()

    shape_sel.param.watch(_on_shape_change, "value")

    # Initialise visibility from the query-string default
    circle_col.visible = (shape_sel.value == "circle")
    ellipse_col.visible = (shape_sel.value == "ellipse")
    line_col.visible = (shape_sel.value == "line")

    # ── Auto point-count hint ─────────────────────────────────────────────────
    def _auto_n() -> int:
        shape = shape_sel.value
        if shape == "circle":
            return auto_point_count_circle(max(radius_w.value or 0.01, 0.01))
        if shape == "ellipse":
            return auto_point_count_ellipse(
                max(semi_a_w.value or 0.01, 0.01),
                max(semi_b_w.value or 0.01, 0.01),
            )
        return auto_point_count_line(
            x1_w.value or 0.0, y1_w.value or 0.0,
            x2_w.value or 0.0, y2_w.value or 0.0,
        )

    def _effective_n() -> int:
        manual = n_pts_w.value or 0
        return manual if manual >= 2 else _auto_n()

    def _refresh_hint(*_args):
        auto = _auto_n()
        n_hint.object = (
            f'<p style="font-size:0.83rem;color:#5b7a9a;margin:2px 0 8px;">'
            f"Auto for this size: <strong>{auto}</strong> points. "
            "Set to 0 to use auto.</p>"
        )

    for _w in (radius_w, semi_a_w, semi_b_w, x1_w, y1_w, x2_w, y2_w):
        _w.param.watch(_refresh_hint, "value")
    _refresh_hint()

    # ── Geometry helpers ──────────────────────────────────────────────────────
    def _fit_points():
        shape = shape_sel.value
        n = _effective_n()
        if shape == "circle":
            return fit_points_circle(cx_w.value or 0.0, cy_w.value or 0.0, radius_w.value, n)
        if shape == "ellipse":
            return fit_points_ellipse(
                cx_w.value or 0.0, cy_w.value or 0.0,
                semi_a_w.value, semi_b_w.value,
                angle_w.value or 0.0,
                n,
            )
        return fit_points_line(
            x1_w.value or 0.0, y1_w.value or 0.0,
            x2_w.value or 0.0, y2_w.value or 0.0,
            n,
        )

    def _get_W() -> float:
        shape = shape_sel.value
        if shape == "circle":
            return effective_source_width("circle", radius=radius_w.value)
        if shape == "ellipse":
            return effective_source_width("ellipse", semi_b=semi_b_w.value)
        return effective_source_width(
            "line",
            x1=x1_w.value or 0.0, y1=y1_w.value or 0.0,
            x2=x2_w.value or 0.0, y2=y2_w.value or 0.0,
        )

    # ── Bokeh plot builder ────────────────────────────────────────────────────
    def _make_plot(points, lmax, shape, W):
        p = figure(
            title=f"Source Geometry — {shape.capitalize()}  |  Lmax = {lmax:.1f} m",
            x_axis_label="x — flow direction [m]",
            y_axis_label="y — transverse [m]",
            height=480,
            sizing_mode="stretch_width",
            match_aspect=True,
            toolbar_location="above",
        )

        # Source outline
        t = np.linspace(0, 2 * math.pi, 300)
        if shape == "circle":
            sx = (cx_w.value or 0.0) + radius_w.value * np.cos(t)
            sy = (cy_w.value or 0.0) + radius_w.value * np.sin(t)
            p.patch(list(sx), list(sy),
                    fill_color="#163c66", fill_alpha=0.12,
                    line_color="#163c66", line_width=2,
                    legend_label="Source outline")
        elif shape == "ellipse":
            ar = math.radians(angle_w.value or 0.0)
            lx = semi_a_w.value * np.cos(t)
            ly = semi_b_w.value * np.sin(t)
            sx = (cx_w.value or 0.0) + math.cos(ar) * lx - math.sin(ar) * ly
            sy = (cy_w.value or 0.0) + math.sin(ar) * lx + math.cos(ar) * ly
            p.patch(list(sx), list(sy),
                    fill_color="#163c66", fill_alpha=0.12,
                    line_color="#163c66", line_width=2,
                    legend_label="Source outline")
        else:  # line
            p.segment(
                x0=[x1_w.value or 0.0], y0=[y1_w.value or 0.0],
                x1=[x2_w.value or 0.0], y1=[y2_w.value or 0.0],
                line_color="#163c66", line_width=4,
                legend_label="Source line",
            )

        # Plume extent segments (all at once)
        xs0 = [pt.x for pt in points]
        ys0 = [pt.y for pt in points]
        xs1 = [pt.x + lmax for pt in points]
        ys1 = list(ys0)
        p.segment(xs0, ys0, xs1, ys1,
                  line_color="#7fb6e6", line_width=1.5, line_alpha=0.55,
                  legend_label=f"Plume extents (Lmax = {lmax:.1f} m)")

        # Fitted source points
        p.scatter(xs0, ys0,
                  size=10, color="#e05c00", marker="circle",
                  legend_label="Source points")

        # Plume-front marker (dashed vertical at furthest x + lmax)
        front_x = max(xs1)
        y_lo = min(ys0) - W * 0.25
        y_hi = max(ys0) + W * 0.25
        p.line([front_x, front_x], [y_lo, y_hi],
               line_color="#163c66", line_dash="dashed", line_width=2,
               legend_label="Plume front")

        p.legend.location = "top_right"
        p.legend.click_policy = "hide"
        return p

    # ── PDF callback ──────────────────────────────────────────────────────────
    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Source Geometry Forward Model", "Analytical — Liedl et al. (2005)")
        return io.BytesIO(report.generate(
            _state["parameters"], _state["outputs"], _state.get("plot_data")
        ))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback,
        filename="source_geometry_report.pdf",
        label="↓ Download PDF Report",
        button_type="primary",
        sizing_mode="stretch_width",
        visible=False,
    )

    # ── Run callback ──────────────────────────────────────────────────────────
    def _run(_=None):
        run_btn.disabled = True
        try:
            shape = shape_sel.value
            n = _effective_n()

            # Geometry-specific minimum validation
            if shape in ("circle", "ellipse") and n < 4:
                raise ValueError("Source points must be ≥ 4 for circular / ellipse shapes.")
            if shape == "line" and n < 2:
                raise ValueError("Source points must be ≥ 2 for a line source.")

            points = _fit_points()
            W = _get_W()
            if W <= 0:
                raise ValueError("Effective source width must be positive.")

            lmax = liedl_lmax(W, alpha_tv_w.value, gamma_w.value, c_ea0_w.value, c_ed0_w.value)

            result_pane.object = summary_card(
                [
                    ("Effective source width W", f"{W:.2f} m"),
                    ("Liedl Lₘₐₓ", f"{lmax:.2f} m"),
                    ("Source points N", str(len(points))),
                ],
                title=f"Forward Model — {shape.capitalize()} Source",
            )
            plot_pane.object = _make_plot(points, lmax, shape, W)

            _state.update({
                "parameters": [
                    *_geometry_params(shape),
                    {"symbol": "Wₑff", "name": "Effective Source Width", "value": W, "unit": "m"},
                    {"symbol": "αTv", "name": "Transverse Dispersivity", "value": alpha_tv_w.value, "unit": "m"},
                    {"symbol": "γ", "name": "Stoichiometric Ratio", "value": gamma_w.value, "unit": "-"},
                    {"symbol": "Cₐ", "name": "Electron Acceptor", "value": c_ea0_w.value, "unit": "mg/L"},
                    {"symbol": "Cₓ", "name": "Electron Donor", "value": c_ed0_w.value, "unit": "mg/L"},
                    {"symbol": "N", "name": "Source Points", "value": len(points), "unit": "-"},
                ],
                "outputs": [
                    {"label": "Effective Source Width W", "value": f"{W:.2f}", "unit": "m"},
                    {"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"},
                    {"label": "Source Points N", "value": str(len(points)), "unit": "-"},
                ],
                "plot_data": {
                    "labels": ["W_eff", "Lmax"],
                    "values": [W, lmax],
                    "ylabel": "Length [m]",
                    "title": f"Source Geometry — {shape.capitalize()}",
                },
            })
            export_btn.visible = True

        except Exception as exc:
            result_pane.object = error_card(exc)
            plot_pane.object = None
            export_btn.visible = False
        finally:
            run_btn.disabled = False

    def _geometry_params(shape):
        if shape == "circle":
            return [
                {"symbol": "cx", "name": "Centre x", "value": cx_w.value or 0.0, "unit": "m"},
                {"symbol": "cy", "name": "Centre y", "value": cy_w.value or 0.0, "unit": "m"},
                {"symbol": "r",  "name": "Radius",   "value": radius_w.value, "unit": "m"},
            ]
        if shape == "ellipse":
            return [
                {"symbol": "cx", "name": "Centre x",    "value": cx_w.value or 0.0, "unit": "m"},
                {"symbol": "cy", "name": "Centre y",    "value": cy_w.value or 0.0, "unit": "m"},
                {"symbol": "a",  "name": "Semi-axis a", "value": semi_a_w.value, "unit": "m"},
                {"symbol": "b",  "name": "Semi-axis b", "value": semi_b_w.value, "unit": "m"},
                {"symbol": "θ", "name": "Rotation", "value": angle_w.value or 0.0, "unit": "°"},
            ]
        return [
            {"symbol": "x₁", "name": "Start x", "value": x1_w.value or 0.0, "unit": "m"},
            {"symbol": "y₁", "name": "Start y", "value": y1_w.value or 0.0, "unit": "m"},
            {"symbol": "x₂", "name": "End x",   "value": x2_w.value or 0.0, "unit": "m"},
            {"symbol": "y₂", "name": "End y",   "value": y2_w.value or 0.0, "unit": "m"},
        ]

    run_btn.on_click(_run)

    # ── Output-only mode (embedded iframe, outputs only) ──────────────────────
    if query_int("output_only", 0):
        if query_int("run", 0):
            _run()
        return pn.Column(result_pane, plot_pane, sizing_mode="stretch_width", styles={"gap": "14px"})

    # ── Full layout ───────────────────────────────────────────────────────────
    controls = pn.Column(
        pn.pane.HTML('<h3 style="margin:0 0 10px;color:#1B3A6B;">Source Geometry</h3>'),
        shape_sel,
        circle_col,
        ellipse_col,
        line_col,
        pn.pane.HTML('<div style="font-weight:700;margin:12px 0 4px;color:#163c66;">Point Discretisation</div>'),
        n_pts_w,
        n_hint,
        pn.pane.HTML('<div style="font-weight:700;margin:12px 0 4px;color:#163c66;">Physical Parameters — Liedl (2005)</div>'),
        alpha_tv_w,
        gamma_w,
        c_ea0_w,
        c_ed0_w,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs_col = pn.Column(
        plot_pane,
        sizing_mode="stretch_both",
        styles={"flex": "2 1 540px", "min-width": "340px"},
    )
    body = pn.FlexBox(
        controls,
        outputs_col,
        sizing_mode="stretch_both",
        flex_wrap="wrap",
        styles={"gap": "16px"},
    )
    return pn.Column(
        run_btn,
        result_pane,
        body,
        export_btn,
        sizing_mode="stretch_both",
        styles={"gap": "14px"},
    )
