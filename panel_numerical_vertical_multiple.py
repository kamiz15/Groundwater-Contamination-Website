import io
import logging

import numpy as np
import pandas as pd
import panel as pn

from analytical_models import liedl_domain_length, liedl_lmax
from numerical_models import balanced_source_buffers, run_numerical_model
from panel_analytical_common import error_card, info_card, query_float, query_int, summary_card
from panel_numerical_comparison import multiple_comparison_plot
from panel_numerical_optional_views import LazyNumericalViews
from pdf_report import CASTReport
from plot_functions import plot_vertical_plume_interactive

pn.extension("tabulator", sizing_mode="stretch_width")

logger = logging.getLogger(__name__)


def numerical_vertical_multiple_app():
    m_default = query_float("M", 5.0)
    s_t_default = query_float("S_T", min(1.0, m_default))
    try:
        s_ta_default, s_tb_default = balanced_source_buffers(m_default, s_t_default)
    except ValueError:
        s_ta_default, s_tb_default = 0.0, 0.0
    table = pn.widgets.Tabulator(
        pd.DataFrame([
            {
                "M": m_default,
                "S_T": s_t_default,
                "S_Ta": query_float("S_Ta", s_ta_default),
                "S_Tb": query_float("S_Tb", s_tb_default),
                "delta_x": query_float("delta_x", 1.0),
                "delta_z": query_float("delta_z", 0.25),
                "alpha_L": query_float("al", 5.0),
                "alpha_Th": query_float("alpha_Th", query_float("at", 0.2)),
                "alpha_Tv": query_float("alpha_Tv", 0.5),
                "K_h [m/d]": query_float("hk", 1.0),
                "K_v [m/d]": query_float("vk", query_float("K_v", query_float("hk", 1.0))),
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
        name="Vertical numerical scenarios",
    )
    run_btn = pn.widgets.Button(name="Run Vertical Scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Edit the vertical scenario table and run the simulations."), sizing_mode="stretch_width")
    graph_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
    comparison_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=360)
    state = {}
    optional_views = LazyNumericalViews(lambda: state.get("optional_view"))

    def _pdf_callback():
        if not state:
            return io.BytesIO(b"")
        report = CASTReport("Numerical Vertical Model - Multiple Simulation", "Numerical Vertical")
        return io.BytesIO(report.generate(
            state["parameters"],
            state["outputs"],
            plot_data=state.get("plot_data"),
            plot_images=state.get("plot_images"),
        ))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback,
        filename="numerical_vertical_multiple_report.pdf",
        label="Download PDF Report",
        button_type="primary",
        sizing_mode="stretch_width",
        visible=False,
    )

    def _run(_=None):
        state.pop("optional_view", None)
        optional_views.reset()
        run_btn.disabled = True
        run_btn.name = "Running Vertical Scenarios..."
        try:
            df = pd.DataFrame(table.value)
            outputs = []
            liedl_values = []
            numerical_values = []
            first_result = None
            first_meta = None

            for idx, row in df.iterrows():
                m = float(row["M"])
                s_t = float(row["S_T"])
                s_ta = float(row["S_Ta"])
                s_tb = float(row["S_Tb"])
                if s_ta + s_t + s_tb > m:
                    raise ValueError(f"Scenario {idx + 1}: STa + ST + STb must fit within M.")
                dx = float(row["delta_x"])
                dz = float(row["delta_z"])
                lmax = liedl_lmax(m, float(row["alpha_Tv"]), float(row["gamma"]), float(row["C_A"]), float(row["C_D"]))
                ld = liedl_domain_length(lmax, row.get("L_D_override [m]", 0.0))
                result = run_numerical_model(
                    ld,
                    m,
                    max(int(np.ceil(ld / dx)), 2),
                    max(int(np.ceil(m / dz)), 2),
                    float(row["n"]),
                    float(row["alpha_L"]),
                    float(row["alpha_Tv"]),
                    float(row["gamma"]),
                    float(row["C_D"]),
                    float(row["C_A"]),
                    float(row["h1"]),
                    float(row["h2"]),
                    float(row["K_h [m/d]"]),
                    float(row["K_v [m/d]"]),
                    source_thickness=s_t,
                    source_bottom_buffer=s_tb,
                    perlen=float(row["perlen"]),
                    plume_threshold=float(row["C0"]),
                    ath=float(row["alpha_Th"]),
                )
                outputs.append({"label": f"Scenario {idx + 1} numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"})
                outputs.append({"label": f"Scenario {idx + 1} Liedl Lmax", "value": f"{lmax:.2f}", "unit": "m"})
                liedl_values.append(lmax)
                numerical_values.append(result.plume_length)
                if first_result is None:
                    first_result = result
                    first_meta = (ld, s_t, s_ta, s_tb, m)
            run_btn.name = "Run Vertical Scenarios"

            if first_result and first_meta:
                ld, s_t, s_ta, s_tb, m = first_meta
                graph_pane.object = plot_vertical_plume_interactive(
                    first_result.concentration,
                    first_result.x_grid,
                    first_result.z_grid,
                    first_result.plume_length,
                    ld,
                    s_t,
                    s_ta,
                    s_tb,
                    m,
                )
                logger.info("Vertical multiple graph_pane.object assigned")
            comparison_pane.object = multiple_comparison_plot(
                "Vertical Numerical vs Liedl",
                "Liedl analytical",
                "Vertical numerical",
                liedl_values,
                numerical_values,
            )
            result_pane.object = summary_card(
                [(item["label"], f"{item['value']} {item['unit']}") for item in outputs[:6]],
                title=f"{len(df)} Vertical Scenario(s) Run",
            )
            plot_images = []
            if first_result and first_result.plot_png:
                plot_images.append({
                    "title": "Vertical Plume Concentration (Scenario 1)",
                    "bytes": first_result.plot_png,
                    "caption": "Simulated contaminant plume — first scenario, vertical cross-section.",
                })
            state.update({
                "parameters": [{"symbol": "Rows", "name": "Scenario Count", "value": len(df), "unit": "-"}],
                "outputs": outputs,
                "plot_data": {
                    "labels": [f"Scenario {i + 1} Liedl" for i in range(len(liedl_values))] +
                               [f"Scenario {i + 1} Numerical" for i in range(len(numerical_values))],
                    "values": liedl_values + numerical_values,
                    "ylabel": "Plume Length (m)",
                    "title": "Vertical Numerical vs Liedl",
                },
                "plot_images": plot_images,
                "optional_view": {
                    "concentration": first_result.concentration,
                    "x_grid": first_result.x_grid,
                    "cross_grid": first_result.z_grid,
                    "cross_axis_label": "Aquifer Thickness [m]",
                    "title": "Vertical Numerical Model - Scenario 1",
                } if first_result else None,
            })
            export_btn.visible = True
        except Exception as exc:
            logger.exception("Vertical numerical scenario run failed")
            result_pane.object = error_card(exc)
            graph_pane.object = None
            comparison_pane.object = None
            export_btn.visible = False
        finally:
            run_btn.disabled = False
            run_btn.name = "Run Vertical Scenarios"

    run_btn.on_click(_run)
    if query_int("output_only", 0):
        if query_int("run", 0):
            _run()
        return pn.Column(result_pane, graph_pane, comparison_pane, sizing_mode="stretch_width", styles={"gap": "14px"})
    return pn.Column(
        "## Vertical Numerical Model - Multiple",
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
