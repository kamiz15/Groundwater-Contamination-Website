import io
import logging

import numpy as np
import pandas as pd
import panel as pn

from analytical_models import cirpka_domain_length, cirpka_lmax
from numerical_models import run_numerical_model_horizontal
from panel_analytical_common import error_card, info_card, query_float, query_int, summary_card
from panel_numerical_comparison import multiple_comparison_plot
from panel_numerical_optional_views import LazyNumericalViews
from pdf_report import CASTReport
from plot_functions import plot_horizontal_plume_interactive

pn.extension("tabulator", sizing_mode="stretch_width")

logger = logging.getLogger(__name__)


def numerical_horizontal_multiple_app():
    table = pn.widgets.Tabulator(
        pd.DataFrame([
            {
                "Sw": query_float("Sw", 5.0),
                "R_Wu": query_float("R_Wu", 7.5),
                "R_Wb": query_float("R_Wb", 7.5),
                "delta_x": query_float("delta_x", 1.0),
                "delta_y": query_float("delta_y", query_float("delta_z", 0.25)),
                "alpha_L": query_float("al", 5.0),
                "alpha_Th": query_float("alpha_Th", 0.1),
                "K [m/d]": query_float("hk", 1.0),
                "n": query_float("prsity", 0.3),
                "h1": query_float("h1", 10.0),
                "h2": query_float("h2", 9.0),
                "C_D": query_float("C_D", 5.0),
                "C_A": query_float("C_A", 8.0),
                "C0": query_float("C0", 8.0),
                "gamma": query_float("gamma", 3.5),
                "perlen": query_float("perlen", 100.0),
                "L_D_override [m]": query_float("L_D_override", 0.0),
            }
        ]),
        height=300,
        sizing_mode="stretch_width",
        name="Horizontal numerical scenarios",
    )
    run_btn = pn.widgets.Button(name="Run Horizontal Scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Edit the horizontal scenario table and run the simulations."), sizing_mode="stretch_width")
    graph_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
    comparison_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=360)
    state = {}
    optional_views = LazyNumericalViews(lambda: state.get("optional_view"))

    def _pdf_callback():
        if not state:
            return io.BytesIO(b"")
        report = CASTReport("Numerical Horizontal Model - Multiple Simulation", "Numerical Horizontal")
        return io.BytesIO(report.generate(
            state["parameters"],
            state["outputs"],
            plot_data=state.get("plot_data"),
            plot_images=state.get("plot_images"),
        ))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback,
        filename="numerical_horizontal_multiple_report.pdf",
        label="Download PDF Report",
        button_type="primary",
        sizing_mode="stretch_width",
        visible=False,
    )

    def _run(_=None):
        state.pop("optional_view", None)
        optional_views.reset()
        run_btn.disabled = True
        run_btn.name = "Running Horizontal Scenarios..."
        try:
            df = pd.DataFrame(table.value)
            outputs = []
            cirpka_values = []
            numerical_values = []
            first_result = None
            first_meta = None

            for idx, row in df.iterrows():
                sw = float(row["Sw"])
                r_wu = float(row["R_Wu"])
                r_wb = float(row["R_Wb"])
                dx = float(row["delta_x"])
                dy = float(row["delta_y"])
                lmax = cirpka_lmax(sw, float(row["alpha_Th"]), float(row["gamma"]), float(row["C_A"]), float(row["C_D"]))
                ld = cirpka_domain_length(lmax, row.get("L_D_override [m]", 0.0))
                width = r_wb + sw + r_wu
                result = run_numerical_model_horizontal(
                    ld,
                    width,
                    sw,
                    max(int(np.ceil(ld / dx)), 2),
                    max(int(np.ceil(width / dy)), 2),
                    float(row["n"]),
                    float(row["alpha_L"]),
                    float(row["alpha_Th"]),
                    float(row["gamma"]),
                    float(row["C_D"]),
                    float(row["C_A"]),
                    float(row["h1"]),
                    float(row["h2"]),
                    float(row["K [m/d]"]),
                    perlen=float(row["perlen"]),
                    plume_threshold=float(row["C0"]),
                )
                outputs.append({"label": f"Scenario {idx + 1} numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"})
                outputs.append({"label": f"Scenario {idx + 1} Cirpka Lmax", "value": f"{lmax:.2f}", "unit": "m"})
                cirpka_values.append(lmax)
                numerical_values.append(result.plume_length)
                if first_result is None:
                    first_result = result
                    first_meta = (ld, sw, width)
            run_btn.name = "Run Horizontal Scenarios"

            if first_result and first_meta:
                ld, sw, width = first_meta
                graph_pane.object = plot_horizontal_plume_interactive(
                    first_result.concentration,
                    first_result.x_grid,
                    first_result.y_grid,
                    first_result.plume_length,
                    ld,
                    sw,
                    width,
                )
                logger.info("Horizontal multiple graph_pane.object assigned")
            comparison_pane.object = multiple_comparison_plot(
                "Horizontal Numerical vs Cirpka",
                "Cirpka analytical",
                "Horizontal numerical",
                cirpka_values,
                numerical_values,
            )
            result_pane.object = summary_card(
                [(item["label"], f"{item['value']} {item['unit']}") for item in outputs[:6]],
                title=f"{len(df)} Horizontal Scenario(s) Run",
            )
            plot_images = []
            if first_result and first_result.plot_png:
                plot_images.append({
                    "title": "Horizontal Plume Concentration (Scenario 1)",
                    "bytes": first_result.plot_png,
                    "caption": "Simulated contaminant plume — first scenario, plan view (horizontal model).",
                })
            state.update({
                "parameters": [{"symbol": "Rows", "name": "Scenario Count", "value": len(df), "unit": "-"}],
                "outputs": outputs,
                "plot_data": {
                    "labels": [f"Scenario {i + 1} Cirpka" for i in range(len(cirpka_values))] +
                               [f"Scenario {i + 1} Numerical" for i in range(len(numerical_values))],
                    "values": cirpka_values + numerical_values,
                    "ylabel": "Plume Length (m)",
                    "title": "Horizontal Numerical vs Cirpka",
                },
                "plot_images": plot_images,
                "optional_view": {
                    "concentration": first_result.concentration,
                    "x_grid": first_result.x_grid,
                    "cross_grid": first_result.y_grid,
                    "cross_axis_label": "Horizontal Width [m]",
                    "title": "Horizontal Numerical Model - Scenario 1",
                } if first_result else None,
            })
            export_btn.visible = True
        except Exception as exc:
            logger.exception("Horizontal numerical scenario run failed")
            result_pane.object = error_card(exc)
            graph_pane.object = None
            comparison_pane.object = None
            export_btn.visible = False
        finally:
            run_btn.disabled = False
            run_btn.name = "Run Horizontal Scenarios"

    run_btn.on_click(_run)
    if query_int("output_only", 0):
        if query_int("run", 0):
            _run()
        return pn.Column(result_pane, graph_pane, comparison_pane, sizing_mode="stretch_width", styles={"gap": "14px"})
    return pn.Column(
        "## Horizontal Numerical Model - Multiple",
        table,
        run_btn,
        result_pane,
        graph_pane,
        comparison_pane,
        optional_views.panel,
        export_btn,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
