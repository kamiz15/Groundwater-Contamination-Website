import io
import logging

import numpy as np
import panel as pn

from numerical_models import run_numerical_model_horizontal
from panel_analytical_common import error_card, info_card, query_float, query_int, summary_card
from panel_numerical_optional_views import LazyNumericalViews
from pdf_report import CASTReport
from plot_functions import plot_horizontal_plume_interactive

pn.extension(sizing_mode="stretch_width")

logger = logging.getLogger(__name__)


def numerical_horizontal_single_app():
    lx = pn.widgets.FloatInput(name="Domain Length Lx [m]", value=query_float("Lx", 100.0), step=1.0)
    ly = pn.widgets.FloatInput(name="Domain Width Ly [m]", value=query_float("Ly", 20.0), step=1.0)
    nrow = pn.widgets.IntInput(name="Rows nrow [-]", value=query_int("nrow", 40), step=1)
    ncol = pn.widgets.IntInput(name="Columns ncol [-]", value=query_int("ncol", 100), step=1)
    source = pn.widgets.FloatInput(name="Source Width source [m]", value=query_float("source", query_float("Sw", 5.0)), step=0.1)
    alpha_l = pn.widgets.FloatInput(name="Longitudinal Dispersivity alpha L [m]", value=query_float("al", 5.0), step=0.1)
    at = pn.widgets.FloatInput(name="Transverse Dispersivity at [m]", value=query_float("at", query_float("alpha_Th", 0.1)), step=0.01)
    prsity = pn.widgets.FloatInput(name="Porosity n [-]", value=query_float("prsity", 0.3), step=0.01)
    hk = pn.widgets.FloatInput(name="Hydraulic Conductivity K [m/d]", value=query_float("hk", 1.0), step=0.1)
    h1 = pn.widgets.FloatInput(name="Head at Left Domain H_L [m]", value=query_float("h1", 10.0), step=0.1)
    h2 = pn.widgets.FloatInput(name="Head at Right Domain H_R [m]", value=query_float("h2", 9.0), step=0.1)
    cd = pn.widgets.FloatInput(name="Electron Donor CD [mg/L]", value=query_float("Cd", query_float("C_D", 5.0)), step=0.1)
    ca = pn.widgets.FloatInput(name="Electron Acceptor CA [mg/L]", value=query_float("Ca", query_float("C_A", 8.0)), step=0.1)
    c0 = pn.widgets.FloatInput(name="Plume Contour Threshold C0 [mg/L]", value=query_float("C0", 8.0), step=0.1)
    gamma = pn.widgets.FloatInput(name="Stoichiometric Ratio gamma [-]", value=query_float("gamma", 3.5), step=0.1)
    perlen = pn.widgets.FloatInput(name="Simulation Time [day]", value=query_float("perlen", 100.0), step=1.0)

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
            if min(lx.value, ly.value, source.value, prsity.value, alpha_l.value, at.value, hk.value, c0.value, perlen.value) <= 0:
                raise ValueError("Lx, Ly, source, porosity, dispersivity, K, C0, and simulation time must be positive.")
            if nrow.value < 2 or ncol.value < 6:
                raise ValueError("nrow must be at least 2 and ncol must be at least 6 for Orlando's source column.")
            if h1.value <= h2.value:
                raise ValueError("Head H_L must be greater than H_R.")

            result = run_numerical_model_horizontal(
                lx.value,
                ly.value,
                source.value,
                ncol.value,
                nrow.value,
                prsity.value,
                alpha_l.value,
                at.value,
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
                lx.value,
                source.value,
                ly.value,
            )
            logger.info("Horizontal single graph_pane.object assigned")
            comparison_pane.object = None
            result_pane.object = summary_card(
                [
                    ("Numerical Lmax", f"{result.plume_length:.2f} m"),
                    ("Domain Length Lx", f"{lx.value:.2f} m"),
                ],
                title="Horizontal Simulation Results",
            )
            state.update({
                "parameters": [
                    {"symbol": "Lx", "name": "Domain Length", "value": lx.value, "unit": "m"},
                    {"symbol": "Ly", "name": "Domain Width", "value": ly.value, "unit": "m"},
                    {"symbol": "nrow", "name": "Rows", "value": nrow.value, "unit": "-"},
                    {"symbol": "ncol", "name": "Columns", "value": ncol.value, "unit": "-"},
                    {"symbol": "source", "name": "Source Width", "value": source.value, "unit": "m"},
                    {"symbol": "alpha L", "name": "Longitudinal Dispersivity", "value": alpha_l.value, "unit": "m"},
                    {"symbol": "at", "name": "Transverse Dispersivity", "value": at.value, "unit": "m"},
                    {"symbol": "K", "name": "Hydraulic Conductivity", "value": hk.value, "unit": "m/d"},
                    {"symbol": "C0", "name": "Plume Contour Threshold", "value": c0.value, "unit": "mg/L"},
                    {"symbol": "perlen", "name": "Simulation Time", "value": perlen.value, "unit": "day"},
                    {"symbol": "CD", "name": "Electron Donor", "value": cd.value, "unit": "mg/L"},
                    {"symbol": "CA", "name": "Electron Acceptor", "value": ca.value, "unit": "mg/L"},
                    {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma.value, "unit": "-"},
                ],
                "outputs": [
                    {"label": "Horizontal Numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"},
                    {"label": "Domain Length Lx", "value": f"{lx.value:.2f}", "unit": "m"},
                ],
                "plot_data": {
                    "labels": ["Horizontal numerical"],
                    "values": [result.plume_length],
                    "ylabel": "Plume Length (m)",
                    "title": "Horizontal Numerical",
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
        pn.Row(lx, ly, source, sizing_mode="stretch_width"),
        pn.Row(nrow, ncol, prsity, sizing_mode="stretch_width"),
        pn.Row(alpha_l, at, hk, sizing_mode="stretch_width"),
        pn.Row(h1, h2, gamma, sizing_mode="stretch_width"),
        pn.Row(cd, ca, c0, perlen, sizing_mode="stretch_width"),
        run_btn,
        result_pane,
        graph_pane,
        comparison_pane,
        optional_views.panel,
        export_btn,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
