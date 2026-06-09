import io
import logging

import numpy as np
import panel as pn

from numerical_models import run_numerical_model
from panel_analytical_common import error_card, info_card, query_float, query_int, summary_card
from panel_numerical_optional_views import LazyNumericalViews
from pdf_report import CASTReport
from plot_functions import plot_vertical_plume_interactive

pn.extension(sizing_mode="stretch_width")

logger = logging.getLogger(__name__)


def numerical_vertical_single_app():
    lx = pn.widgets.FloatInput(name="Domain Length Lx [m]", value=query_float("Lx", 200.0), step=1.0)
    lz = pn.widgets.FloatInput(name="Domain Thickness Lz [m]", value=query_float("Lz", query_float("M", 10.0)), step=0.1)
    ncol = pn.widgets.IntInput(name="Columns ncol [-]", value=query_int("ncol", 200), step=1)
    nlay = pn.widgets.IntInput(name="Layers nlay [-]", value=query_int("nlay", 20), step=1)
    alpha_l = pn.widgets.FloatInput(name="Longitudinal Dispersivity alpha L [m]", value=query_float("al", 5.0), step=0.1)
    at = pn.widgets.FloatInput(name="Transverse Dispersivity at [m]", value=query_float("at", query_float("alpha_Th", 0.2)), step=0.01)
    atv = pn.widgets.FloatInput(name="Vertical Transverse Dispersivity atv [m]", value=query_float("atv", query_float("alpha_Tv", 0.1)), step=0.01)
    prsity = pn.widgets.FloatInput(name="Porosity n [-]", value=query_float("prsity", 0.3), step=0.01)
    hk = pn.widgets.FloatInput(name="Hydraulic Conductivity K [m/d]", value=query_float("hk", 1.0), step=0.1)
    h1 = pn.widgets.FloatInput(name="Head at Left Domain H_L [m]", value=query_float("h1", 10.0), step=0.1)
    h2 = pn.widgets.FloatInput(name="Head at Right Domain H_R [m]", value=query_float("h2", 9.0), step=0.1)
    cd = pn.widgets.FloatInput(name="Electron Donor CD [mg/L]", value=query_float("Cd", query_float("C_D", 5.0)), step=0.1)
    ca = pn.widgets.FloatInput(name="Electron Acceptor CA [mg/L]", value=query_float("Ca", query_float("C_A", 8.0)), step=0.1)
    c0 = pn.widgets.FloatInput(name="Plume Contour Threshold C0 [mg/L]", value=query_float("C0", 8.0), step=0.1)
    gamma = pn.widgets.FloatInput(name="Stoichiometric Ratio gamma [-]", value=query_float("gamma", 3.5), step=0.1)
    perlen = pn.widgets.FloatInput(name="Simulation Time [day]", value=query_float("perlen", 100.0), step=1.0)

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
            if min(lx.value, lz.value, prsity.value, alpha_l.value, at.value, atv.value, hk.value, c0.value, perlen.value) <= 0:
                raise ValueError("Lx, Lz, porosity, dispersivity, K, C0, and simulation time must be positive.")
            if ncol.value < 6 or nlay.value < 2:
                raise ValueError("ncol must be at least 6 and nlay must be at least 2 for Orlando's source column.")
            if h1.value <= h2.value:
                raise ValueError("Head H_L must be greater than H_R.")

            result = run_numerical_model(
                lx.value,
                lz.value,
                ncol.value,
                nlay.value,
                prsity.value,
                alpha_l.value,
                atv.value,
                gamma.value,
                cd.value,
                ca.value,
                h1.value,
                h2.value,
                hk.value,
                perlen=perlen.value,
                plume_threshold=c0.value,
                ath=at.value,
            )
            run_btn.name = "Run Vertical Simulation"

            graph_pane.object = plot_vertical_plume_interactive(
                result.concentration,
                result.x_grid,
                result.z_grid,
                result.plume_length,
                lx.value,
                max(lz.value - (lz.value / nlay.value), 0.0),
                0.0,
                0.0,
                lz.value,
            )
            logger.info("Vertical single graph_pane.object assigned")
            comparison_pane.object = None
            result_pane.object = summary_card(
                [
                    ("Numerical Lmax", f"{result.plume_length:.2f} m"),
                    ("Domain Length Lx", f"{lx.value:.2f} m"),
                ],
                title="Vertical Simulation Results",
            )
            state.update({
                "parameters": [
                    {"symbol": "Lx", "name": "Domain Length", "value": lx.value, "unit": "m"},
                    {"symbol": "Lz", "name": "Domain Thickness", "value": lz.value, "unit": "m"},
                    {"symbol": "ncol", "name": "Columns", "value": ncol.value, "unit": "-"},
                    {"symbol": "nlay", "name": "Layers", "value": nlay.value, "unit": "-"},
                    {"symbol": "alpha L", "name": "Longitudinal Dispersivity", "value": alpha_l.value, "unit": "m"},
                    {"symbol": "at", "name": "Transverse Dispersivity", "value": at.value, "unit": "m"},
                    {"symbol": "atv", "name": "Vertical Transverse Dispersivity", "value": atv.value, "unit": "m"},
                    {"symbol": "K", "name": "Hydraulic Conductivity", "value": hk.value, "unit": "m/d"},
                    {"symbol": "C0", "name": "Plume Contour Threshold", "value": c0.value, "unit": "mg/L"},
                    {"symbol": "perlen", "name": "Simulation Time", "value": perlen.value, "unit": "day"},
                    {"symbol": "CD", "name": "Electron Donor", "value": cd.value, "unit": "mg/L"},
                    {"symbol": "CA", "name": "Electron Acceptor", "value": ca.value, "unit": "mg/L"},
                    {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma.value, "unit": "-"},
                ],
                "outputs": [
                    {"label": "Vertical Numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"},
                    {"label": "Domain Length Lx", "value": f"{lx.value:.2f}", "unit": "m"},
                ],
                "plot_data": {
                    "labels": ["Vertical numerical"],
                    "values": [result.plume_length],
                    "ylabel": "Plume Length (m)",
                    "title": "Vertical Numerical",
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
        pn.Row(lx, lz, ncol, nlay, sizing_mode="stretch_width"),
        pn.Row(alpha_l, at, atv, prsity, sizing_mode="stretch_width"),
        pn.Row(hk, sizing_mode="stretch_width"),
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
