import io
import logging

import numpy as np
import panel as pn

from analytical_models import cirpka_domain_length, cirpka_lmax
from numerical_models import run_numerical_model_horizontal
from panel_analytical_common import error_card, info_card, query_float, query_int, summary_card
from panel_numerical_comparison import single_comparison_plot
from panel_numerical_optional_views import LazyNumericalViews
from pdf_report import CASTReport
from plot_functions import plot_horizontal_plume_interactive

pn.extension(sizing_mode="stretch_width")

logger = logging.getLogger(__name__)


def numerical_horizontal_single_app():
    sw = pn.widgets.FloatInput(name="Source Width Sw [m]", value=query_float("Sw", 5.0), step=0.1)
    r_wu = pn.widgets.FloatInput(name="Upper Reactant Buffer R_Wu [m]", value=query_float("R_Wu", 7.5), step=0.1)
    r_wb = pn.widgets.FloatInput(name="Lower Reactant Buffer R_Wb [m]", value=query_float("R_Wb", 7.5), step=0.1)
    delta_x = pn.widgets.FloatInput(name="Grid Spacing dx [m]", value=query_float("delta_x", 1.0), step=0.1)
    delta_y = pn.widgets.FloatInput(name="Lateral Grid Spacing dy [m]", value=query_float("delta_y", query_float("delta_z", 0.25)), step=0.05)
    alpha_l = pn.widgets.FloatInput(name="Longitudinal Dispersivity alpha L [m]", value=query_float("al", 5.0), step=0.1)
    alpha_th = pn.widgets.FloatInput(name="Horizontal Transverse Dispersivity alpha Th [m]", value=query_float("alpha_Th", 0.1), step=0.01)
    prsity = pn.widgets.FloatInput(name="Porosity n [-]", value=query_float("prsity", 0.3), step=0.01)
    hk = pn.widgets.FloatInput(name="Hydraulic Conductivity K [m/d]", value=query_float("hk", 1.0), step=0.1)
    h1 = pn.widgets.FloatInput(name="Head at Left Domain H_L [m]", value=query_float("h1", 10.0), step=0.1)
    h2 = pn.widgets.FloatInput(name="Head at Right Domain H_R [m]", value=query_float("h2", 9.0), step=0.1)
    cd = pn.widgets.FloatInput(name="Electron Donor CD [mg/L]", value=query_float("Cd", query_float("C_D", 5.0)), step=0.1)
    ca = pn.widgets.FloatInput(name="Electron Acceptor CA [mg/L]", value=query_float("Ca", query_float("C_A", 8.0)), step=0.1)
    c0 = pn.widgets.FloatInput(name="Plume Contour Threshold C0 [mg/L]", value=query_float("C0", 8.0), step=0.1)
    gamma = pn.widgets.FloatInput(name="Stoichiometric Ratio gamma [-]", value=query_float("gamma", 3.5), step=0.1)
    perlen = pn.widgets.FloatInput(name="Simulation Time [day]", value=query_float("perlen", 100.0), step=1.0)
    ld_override = pn.widgets.FloatInput(name="Domain Length LD Override [m] (0 = automatic)", value=query_float("L_D_override", 0.0), step=1.0)

    run_btn = pn.widgets.Button(name="Run Horizontal Simulation", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Enter horizontal model parameters and run the simulation."), sizing_mode="stretch_width")
    graph_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
    comparison_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=340)
    state = {}
    optional_views = LazyNumericalViews(lambda: state.get("optional_view"))

    def _pdf_callback():
        if not state:
            return io.BytesIO(b"")
        report = CASTReport("Numerical Horizontal Model - Single Simulation", "Numerical Horizontal")
        return io.BytesIO(report.generate(
            state["parameters"],
            state["outputs"],
            plot_data=state.get("plot_data"),
            plot_images=state.get("plot_images"),
        ))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback,
        filename="numerical_horizontal_single_report.pdf",
        label="Download PDF Report",
        button_type="primary",
        sizing_mode="stretch_width",
        visible=False,
    )

    def _run(_=None):
        state.pop("optional_view", None)
        optional_views.reset()
        run_btn.disabled = True
        run_btn.name = "Running Horizontal Simulation..."
        try:
            if min(sw.value, delta_x.value, delta_y.value, prsity.value, alpha_l.value, alpha_th.value, hk.value, c0.value, perlen.value) <= 0:
                raise ValueError("Source width, grid spacing, porosity, dispersivity, K, C0, and simulation time must be positive.")
            if r_wu.value < 0 or r_wb.value < 0:
                raise ValueError("Horizontal reactant buffers cannot be negative.")
            if h1.value <= h2.value:
                raise ValueError("Head H_L must be greater than H_R.")

            analytical_lmax = cirpka_lmax(sw.value, alpha_th.value, gamma.value, ca.value, cd.value)
            ld = cirpka_domain_length(analytical_lmax, ld_override.value)
            domain_width = r_wb.value + sw.value + r_wu.value
            ncol = max(int(np.ceil(ld / delta_x.value)), 2)
            nrow = max(int(np.ceil(domain_width / delta_y.value)), 2)

            result = run_numerical_model_horizontal(
                ld,
                domain_width,
                sw.value,
                ncol,
                nrow,
                prsity.value,
                alpha_l.value,
                alpha_th.value,
                gamma.value,
                cd.value,
                ca.value,
                h1.value,
                h2.value,
                hk.value,
                perlen=perlen.value,
                plume_threshold=c0.value,
            )
            run_btn.name = "Run Horizontal Simulation"

            graph_pane.object = plot_horizontal_plume_interactive(
                result.concentration,
                result.x_grid,
                result.y_grid,
                result.plume_length,
                ld,
                sw.value,
                domain_width,
            )
            logger.info("Horizontal single graph_pane.object assigned")
            comparison_pane.object = single_comparison_plot(
                "Horizontal Numerical vs Cirpka",
                "Cirpka analytical",
                "Horizontal numerical",
                analytical_lmax,
                result.plume_length,
            )
            result_pane.object = summary_card(
                [
                    ("Numerical Lmax", f"{result.plume_length:.2f} m"),
                    ("Cirpka Lmax", f"{analytical_lmax:.2f} m"),
                    ("Domain Length LD", f"{ld:.2f} m"),
                ],
                title="Horizontal Simulation Results",
            )
            state.update({
                "parameters": [
                    {"symbol": "Sw", "name": "Source Width", "value": sw.value, "unit": "m"},
                    {"symbol": "R_Wu", "name": "Upper Reactant Buffer", "value": r_wu.value, "unit": "m"},
                    {"symbol": "R_Wb", "name": "Lower Reactant Buffer", "value": r_wb.value, "unit": "m"},
                    {"symbol": "alpha L", "name": "Longitudinal Dispersivity", "value": alpha_l.value, "unit": "m"},
                    {"symbol": "alpha Th", "name": "Horizontal Transverse Dispersivity", "value": alpha_th.value, "unit": "m"},
                    {"symbol": "K", "name": "Hydraulic Conductivity", "value": hk.value, "unit": "m/d"},
                    {"symbol": "C0", "name": "Plume Contour Threshold", "value": c0.value, "unit": "mg/L"},
                    {"symbol": "perlen", "name": "Simulation Time", "value": perlen.value, "unit": "day"},
                    {"symbol": "LD", "name": "Domain Length Override", "value": ld_override.value or "automatic", "unit": "m"},
                    {"symbol": "CD", "name": "Electron Donor", "value": cd.value, "unit": "mg/L"},
                    {"symbol": "CA", "name": "Electron Acceptor", "value": ca.value, "unit": "mg/L"},
                    {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma.value, "unit": "-"},
                ],
                "outputs": [
                    {"label": "Horizontal Numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"},
                    {"label": "Cirpka Lmax", "value": f"{analytical_lmax:.2f}", "unit": "m"},
                    {"label": "Domain Length LD", "value": f"{ld:.2f}", "unit": "m"},
                ],
                "plot_data": {
                    "labels": ["Cirpka analytical", "Horizontal numerical"],
                    "values": [analytical_lmax, result.plume_length],
                    "ylabel": "Plume Length (m)",
                    "title": "Horizontal Numerical vs Cirpka",
                },
                "plot_images": [
                    {
                        "title": "Horizontal Plume Concentration",
                        "bytes": result.plot_png,
                        "caption": "Simulated contaminant plume — plan view (horizontal model).",
                    }
                ] if result.plot_png else [],
                "optional_view": {
                    "concentration": result.concentration,
                    "x_grid": result.x_grid,
                    "cross_grid": result.y_grid,
                    "cross_axis_label": "Horizontal Width [m]",
                    "title": "Horizontal Numerical Model",
                },
            })
            export_btn.visible = True
        except Exception as exc:
            logger.exception("Horizontal numerical single simulation failed")
            result_pane.object = error_card(exc)
            graph_pane.object = None
            comparison_pane.object = None
            export_btn.visible = False
        finally:
            run_btn.disabled = False
            run_btn.name = "Run Horizontal Simulation"

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
        "## Horizontal Numerical Model",
        pn.Row(sw, r_wu, r_wb, sizing_mode="stretch_width"),
        pn.Row(delta_x, delta_y, prsity, sizing_mode="stretch_width"),
        pn.Row(alpha_l, alpha_th, hk, sizing_mode="stretch_width"),
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
