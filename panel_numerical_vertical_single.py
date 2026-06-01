import io
import logging

import numpy as np
import panel as pn

from analytical_models import liedl_domain_length, liedl_lmax
from numerical_models import balanced_source_buffers, run_numerical_model
from panel_analytical_common import error_card, info_card, query_float, query_int, summary_card
from panel_numerical_comparison import single_comparison_plot
from panel_numerical_optional_views import LazyNumericalViews
from pdf_report import CASTReport
from plot_functions import plot_vertical_plume_interactive

pn.extension(sizing_mode="stretch_width")

logger = logging.getLogger(__name__)


def numerical_vertical_single_app():
    m = pn.widgets.FloatInput(name="Aquifer Thickness M [m]", value=query_float("M", 5.0), step=0.1)
    s_t = pn.widgets.FloatInput(name="Source Thickness ST [m]", value=query_float("S_T", min(1.0, m.value)), step=0.1)
    try:
        default_s_ta, default_s_tb = balanced_source_buffers(m.value, s_t.value)
    except ValueError:
        default_s_ta, default_s_tb = 0.0, 0.0
    s_ta = pn.widgets.FloatInput(name="Buffer Above STa [m]", value=query_float("S_Ta", query_float("R_Ta", default_s_ta)), step=0.1)
    s_tb = pn.widgets.FloatInput(name="Buffer Below STb [m]", value=query_float("S_Tb", query_float("R_Tb", default_s_tb)), step=0.1)
    delta_x = pn.widgets.FloatInput(name="Grid Spacing dx [m]", value=query_float("delta_x", 1.0), step=0.1)
    delta_z = pn.widgets.FloatInput(name="Vertical Grid Spacing dz [m]", value=query_float("delta_z", 0.25), step=0.05)
    alpha_l = pn.widgets.FloatInput(name="Longitudinal Dispersivity alpha L [m]", value=query_float("al", 5.0), step=0.1)
    alpha_th = pn.widgets.FloatInput(name="Horizontal Transverse Dispersivity alpha Th [m]", value=query_float("alpha_Th", query_float("at", 0.2)), step=0.01)
    alpha_tv = pn.widgets.FloatInput(name="Vertical Transverse Dispersivity alpha Tv [m]", value=query_float("alpha_Tv", query_float("av", 0.5)), step=0.1)
    prsity = pn.widgets.FloatInput(name="Porosity n [-]", value=query_float("prsity", 0.3), step=0.01)
    hk = pn.widgets.FloatInput(name="Horizontal Hydraulic Conductivity K_h [m/d]", value=query_float("hk", 1.0), step=0.1)
    vk = pn.widgets.FloatInput(name="Vertical Hydraulic Conductivity K_v [m/d]", value=query_float("vk", query_float("K_v", hk.value)), step=0.1)
    h1 = pn.widgets.FloatInput(name="Head at Left Domain H_L [m]", value=query_float("h1", 10.0), step=0.1)
    h2 = pn.widgets.FloatInput(name="Head at Right Domain H_R [m]", value=query_float("h2", 9.0), step=0.1)
    cd = pn.widgets.FloatInput(name="Electron Donor CD [mg/L]", value=query_float("Cd", query_float("C_D", 5.0)), step=0.1)
    ca = pn.widgets.FloatInput(name="Electron Acceptor CA [mg/L]", value=query_float("Ca", query_float("C_A", 8.0)), step=0.1)
    c0 = pn.widgets.FloatInput(name="Plume Contour Threshold C0 [mg/L]", value=query_float("C0", 8.0), step=0.1)
    gamma = pn.widgets.FloatInput(name="Stoichiometric Ratio gamma [-]", value=query_float("gamma", 3.5), step=0.1)
    perlen = pn.widgets.FloatInput(name="Simulation Time [day]", value=query_float("perlen", 100.0), step=1.0)
    ld_override = pn.widgets.FloatInput(name="Domain Length LD Override [m] (0 = automatic)", value=query_float("L_D_override", 0.0), step=1.0)

    run_btn = pn.widgets.Button(name="Run Vertical Simulation", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Enter vertical model parameters and run the simulation."), sizing_mode="stretch_width")
    graph_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
    comparison_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=340)
    state = {}
    optional_views = LazyNumericalViews(lambda: state.get("optional_view"))

    def _pdf_callback():
        if not state:
            return io.BytesIO(b"")
        report = CASTReport("Numerical Vertical Model - Single Simulation", "Numerical Vertical")
        return io.BytesIO(report.generate(
            state["parameters"],
            state["outputs"],
            plot_data=state.get("plot_data"),
            plot_images=state.get("plot_images"),
        ))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback,
        filename="numerical_vertical_single_report.pdf",
        label="Download PDF Report",
        button_type="primary",
        sizing_mode="stretch_width",
        visible=False,
    )

    def _run(_=None):
        state.pop("optional_view", None)
        optional_views.reset()
        run_btn.disabled = True
        run_btn.name = "Running Vertical Simulation..."
        try:
            if min(m.value, s_t.value, delta_x.value, delta_z.value, prsity.value, alpha_l.value, alpha_th.value, alpha_tv.value, hk.value, vk.value, c0.value, perlen.value) <= 0:
                raise ValueError("Thickness, source thickness, grid spacing, porosity, dispersivity, hydraulic conductivities, C0, and simulation time must be positive.")
            if s_ta.value < 0 or s_tb.value < 0:
                raise ValueError("Vertical source buffers cannot be negative.")
            if s_ta.value + s_t.value + s_tb.value > m.value:
                raise ValueError("STa + ST + STb must fit within aquifer thickness M.")
            if h1.value <= h2.value:
                raise ValueError("Head H_L must be greater than H_R.")

            analytical_lmax = liedl_lmax(m.value, alpha_tv.value, gamma.value, ca.value, cd.value)
            ld = liedl_domain_length(analytical_lmax, ld_override.value)
            ncol = max(int(np.ceil(ld / delta_x.value)), 2)
            nrow = max(int(np.ceil(m.value / delta_z.value)), 2)

            result = run_numerical_model(
                ld,
                m.value,
                ncol,
                nrow,
                prsity.value,
                alpha_l.value,
                alpha_tv.value,
                gamma.value,
                cd.value,
                ca.value,
                h1.value,
                h2.value,
                hk.value,
                vk.value,
                source_thickness=s_t.value,
                source_bottom_buffer=s_tb.value,
                perlen=perlen.value,
                plume_threshold=c0.value,
                ath=alpha_th.value,
            )
            run_btn.name = "Run Vertical Simulation"

            graph_pane.object = plot_vertical_plume_interactive(
                result.concentration,
                result.x_grid,
                result.z_grid,
                result.plume_length,
                ld,
                s_t.value,
                s_ta.value,
                s_tb.value,
                m.value,
            )
            logger.info("Vertical single graph_pane.object assigned")
            comparison_pane.object = single_comparison_plot(
                "Vertical Numerical vs Liedl",
                "Liedl analytical",
                "Vertical numerical",
                analytical_lmax,
                result.plume_length,
            )
            result_pane.object = summary_card(
                [
                    ("Numerical Lmax", f"{result.plume_length:.2f} m"),
                    ("Liedl Lmax", f"{analytical_lmax:.2f} m"),
                    ("Domain Length LD", f"{ld:.2f} m"),
                ],
                title="Vertical Simulation Results",
            )
            state.update({
                "parameters": [
                    {"symbol": "M", "name": "Aquifer Thickness", "value": m.value, "unit": "m"},
                    {"symbol": "ST", "name": "Source Thickness", "value": s_t.value, "unit": "m"},
                    {"symbol": "STa", "name": "Buffer Above", "value": s_ta.value, "unit": "m"},
                    {"symbol": "STb", "name": "Buffer Below", "value": s_tb.value, "unit": "m"},
                    {"symbol": "alpha L", "name": "Longitudinal Dispersivity", "value": alpha_l.value, "unit": "m"},
                    {"symbol": "alpha Th", "name": "Horizontal Transverse Dispersivity", "value": alpha_th.value, "unit": "m"},
                    {"symbol": "alpha Tv", "name": "Vertical Transverse Dispersivity", "value": alpha_tv.value, "unit": "m"},
                    {"symbol": "K_h", "name": "Horizontal Hydraulic Conductivity", "value": hk.value, "unit": "m/d"},
                    {"symbol": "K_v", "name": "Vertical Hydraulic Conductivity", "value": vk.value, "unit": "m/d"},
                    {"symbol": "C0", "name": "Plume Contour Threshold", "value": c0.value, "unit": "mg/L"},
                    {"symbol": "perlen", "name": "Simulation Time", "value": perlen.value, "unit": "day"},
                    {"symbol": "LD", "name": "Domain Length Override", "value": ld_override.value or "automatic", "unit": "m"},
                    {"symbol": "CD", "name": "Electron Donor", "value": cd.value, "unit": "mg/L"},
                    {"symbol": "CA", "name": "Electron Acceptor", "value": ca.value, "unit": "mg/L"},
                    {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma.value, "unit": "-"},
                ],
                "outputs": [
                    {"label": "Vertical Numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"},
                    {"label": "Liedl Lmax", "value": f"{analytical_lmax:.2f}", "unit": "m"},
                    {"label": "Domain Length LD", "value": f"{ld:.2f}", "unit": "m"},
                ],
                "plot_data": {
                    "labels": ["Liedl analytical", "Vertical numerical"],
                    "values": [analytical_lmax, result.plume_length],
                    "ylabel": "Plume Length (m)",
                    "title": "Vertical Numerical vs Liedl",
                },
                "plot_images": [
                    {
                        "title": "Vertical Plume Concentration",
                        "bytes": result.plot_png,
                        "caption": "Simulated contaminant plume — vertical cross-section.",
                    }
                ] if result.plot_png else [],
                "optional_view": {
                    "concentration": result.concentration,
                    "x_grid": result.x_grid,
                    "cross_grid": result.z_grid,
                    "cross_axis_label": "Aquifer Thickness [m]",
                    "title": "Vertical Numerical Model",
                },
            })
            export_btn.visible = True
        except Exception as exc:
            logger.exception("Vertical numerical single simulation failed")
            result_pane.object = error_card(exc)
            graph_pane.object = None
            comparison_pane.object = None
            export_btn.visible = False
        finally:
            run_btn.disabled = False
            run_btn.name = "Run Vertical Simulation"

    run_btn.on_click(_run)
    if query_int("output_only", 0):
        should_run = query_int("run", 0)
        if should_run:
            _run()
        output_objects = [result_pane]
        if should_run:
            output_objects.extend([graph_pane, comparison_pane, optional_views.panel])
        return pn.Column(*output_objects, sizing_mode="stretch_width", styles={"gap": "14px"})

    return pn.Column(
        "## Vertical Numerical Model",
        pn.Row(m, s_t, s_ta, s_tb, sizing_mode="stretch_width"),
        pn.Row(delta_x, delta_z, prsity, sizing_mode="stretch_width"),
        pn.Row(alpha_l, alpha_th, alpha_tv, sizing_mode="stretch_width"),
        pn.Row(hk, vk, sizing_mode="stretch_width"),
        pn.Row(h1, h2, gamma, sizing_mode="stretch_width"),
        pn.Row(cd, ca, c0, perlen, sizing_mode="stretch_width"),
        pn.Accordion(("Advanced Overrides", pn.Column(ld_override, sizing_mode="stretch_width")), active=[]),
        run_btn,
        result_pane,
        graph_pane,
        comparison_pane,
        optional_views.panel,
        export_btn,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
