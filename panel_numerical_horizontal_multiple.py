import io
import logging

import pandas as pd
import panel as pn

from numerical_jobs import fetch_result, job_status, submit_job
from panel_analytical_common import error_card, info_card, query_float, query_int, summary_card
from panel_numerical_optional_views import LazyNumericalViews
from pdf_report import CASTReport
from plot_functions import plot_horizontal_plume_interactive

pn.extension("tabulator", sizing_mode="stretch_width")

logger = logging.getLogger(__name__)


def numerical_horizontal_multiple_app():
    table = pn.widgets.Tabulator(
        pd.DataFrame([
            {
                "Lx": query_float("Lx", 100.0),
                "Ly": query_float("Ly", 20.0),
                "nrow": query_int("nrow", 40),
                "ncol": query_int("ncol", 100),
                "source": query_float("source", query_float("Sw", 5.0)),
                "alpha_L": query_float("al", 5.0),
                "at": query_float("at", query_float("alpha_Th", 0.1)),
                "K [m/d]": query_float("hk", 1.0),
                "n": query_float("prsity", 0.3),
                "h1": query_float("h1", 10.0),
                "h2": query_float("h2", 9.0),
                "C_D": query_float("C_D", 5.0),
                "C_A": query_float("C_A", 8.0),
                "C0": query_float("C0", 8.0),
                "gamma": query_float("gamma", 3.5),
                "perlen": query_float("perlen", 100.0),
            }
        ]),
        height=300,
        sizing_mode="stretch_width",
        name="Horizontal numerical scenarios",
    )
    run_btn = pn.widgets.Button(name="Run Horizontal Scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Edit the horizontal scenario table and run the simulations."), sizing_mode="stretch_width")
    graphs_column = pn.Column(sizing_mode="stretch_width")
    comparison_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=360)
    state = {}
    poller = {"callback": None}
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
        graphs_column.objects = []
        comparison_pane.object = None
        export_btn.visible = False
        try:
            df = pd.DataFrame(table.value)
            job_ids = [
                submit_job("horizontal_single", {
                    "Lx": float(row["Lx"]),
                    "A_W": float(row["Ly"]),
                    "Sw": float(row["source"]),
                    "ncol": int(row["ncol"]),
                    "nrow": int(row["nrow"]),
                    "prsity": float(row["n"]),
                    "al": float(row["alpha_L"]),
                    "alpha_Th": float(row["at"]),
                    "gamma": float(row["gamma"]),
                    "cd": float(row["C_D"]),
                    "ca": float(row["C_A"]),
                    "h1": float(row["h1"]),
                    "h2": float(row["h2"]),
                    "hk": float(row["K [m/d]"]),
                    "perlen": float(row["perlen"]),
                    "plume_threshold": float(row["C0"]),
                })
                for _idx, row in df.iterrows()
            ]

            def _stop_polling():
                run_btn.disabled = False
                run_btn.name = "Run Horizontal Scenarios"
                if poller["callback"] is not None:
                    poller["callback"].stop()
                    poller["callback"] = None

            def _poll():
                statuses = [job_status(job_id) for job_id in job_ids]
                counts = {}
                for status in statuses:
                    counts[status["status"]] = counts.get(status["status"], 0) + 1
                result_pane.object = summary_card(
                    [(key, str(value)) for key, value in sorted(counts.items())],
                    title=f"{len(job_ids)} Horizontal Scenario Job(s)",
                )
                if any(status["status"] == "failed" for status in statuses):
                    failed = next(status for status in statuses if status["status"] == "failed")
                    result_pane.object = error_card(failed.get("error") or "A numerical scenario failed.")
                    _stop_polling()
                elif all(status["status"] == "done" for status in statuses):
                    results = [fetch_result(job_id) for job_id in job_ids]
                    outputs = [
                        {"label": f"Scenario {idx + 1} numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"}
                        for idx, result in enumerate(results)
                    ]
                    result_pane.object = summary_card(
                        [(item["label"], f"{item['value']} {item['unit']}") for item in outputs],
                        title=f"{len(df)} Horizontal Scenario(s) Complete",
                    )
                    new_graphs = []
                    plot_images = []
                    for idx, result in enumerate(results):
                        row = df.iloc[idx]
                        fig = plot_horizontal_plume_interactive(
                            result.concentration,
                            result.x_grid,
                            result.y_grid,
                            result.plume_length,
                            float(row["Lx"]),
                            float(row["source"]),
                            float(row["Ly"]),
                        )
                        new_graphs.append(pn.pane.Markdown(
                            f"**Scenario {idx + 1}** — Lmax {result.plume_length:.2f} m",
                            sizing_mode="stretch_width",
                        ))
                        new_graphs.append(pn.pane.Bokeh(fig, sizing_mode="stretch_width", min_height=430))
                        if result.plot_png:
                            plot_images.append({
                                "title": f"Horizontal Plume Concentration (Scenario {idx + 1})",
                                "bytes": result.plot_png,
                                "caption": f"Simulated contaminant plume — scenario {idx + 1}, plan view (horizontal model).",
                            })
                    graphs_column.objects = new_graphs
                    logger.info("Horizontal multiple graphs_column populated with %d scenario(s)", len(results))
                    first_result = results[0]
                    state.update({
                        "parameters": [{"symbol": "Rows", "name": "Scenario Count", "value": len(df), "unit": "-"}],
                        "outputs": outputs,
                        "plot_data": {
                            "labels": [f"Scenario {i + 1} Numerical" for i in range(len(results))],
                            "values": [r.plume_length for r in results],
                            "ylabel": "Plume Length (m)",
                            "title": "Horizontal Numerical",
                        },
                        "plot_images": plot_images,
                        "optional_view": {
                            "concentration": first_result.concentration,
                            "x_grid": first_result.x_grid,
                            "cross_grid": first_result.y_grid,
                            "cross_axis_label": "Horizontal Width [m]",
                            "title": "Horizontal Numerical Model - Scenario 1",
                        },
                    })
                    export_btn.visible = True
                    _stop_polling()

            poller["callback"] = pn.state.add_periodic_callback(_poll, 2000, start=True)
            _poll()
        except Exception as exc:
            logger.exception("Horizontal numerical scenario run failed")
            result_pane.object = error_card(exc)
            graphs_column.objects = []
            comparison_pane.object = None
            export_btn.visible = False
            run_btn.disabled = False
            run_btn.name = "Run Horizontal Scenarios"

    run_btn.on_click(_run)
    if query_int("output_only", 0):
        if query_int("run", 0):
            _run()
        return pn.Column(result_pane, graphs_column, comparison_pane, sizing_mode="stretch_width", styles={"gap": "14px"})
    return pn.Column(
        "## Horizontal Numerical Model - Multiple",
        table,
        run_btn,
        result_pane,
        graphs_column,
        comparison_pane,
        optional_views.panel,
        export_btn,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
