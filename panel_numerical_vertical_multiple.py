import io
import logging

import pandas as pd
import panel as pn

from numerical_jobs import fetch_result, job_status, submit_job
from panel_analytical_common import error_card, info_card, query_float, query_int, summary_card
from panel_numerical_optional_views import LazyNumericalViews
from pdf_report import CASTReport
from plot_functions import plot_vertical_plume_interactive

pn.extension("tabulator", sizing_mode="stretch_width")

logger = logging.getLogger(__name__)


def numerical_vertical_multiple_app():
    table = pn.widgets.Tabulator(
        pd.DataFrame([
            {
                "Lx": query_float("Lx", 200.0),
                "Lz": query_float("Lz", query_float("M", 10.0)),
                "ncol": query_int("ncol", 200),
                "nlay": query_int("nlay", 20),
                "alpha_L": query_float("al", 5.0),
                "at": query_float("at", query_float("alpha_Th", 0.2)),
                "atv": query_float("atv", query_float("alpha_Tv", 0.1)),
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
        name="Vertical numerical scenarios",
    )
    run_btn = pn.widgets.Button(name="Run Vertical Scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Edit the vertical scenario table and run the simulations."), sizing_mode="stretch_width")
    graphs_column = pn.Column(sizing_mode="stretch_width")
    comparison_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=360)
    state = {}
    poller = {"callback": None}
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

    def _stop_polling():
        run_btn.disabled = False
        run_btn.name = "Run Vertical Scenarios"
        if poller["callback"] is not None:
            poller["callback"].stop()
            poller["callback"] = None

    def _render_completed_results(df, results):
        outputs = [
            {"label": f"Scenario {idx + 1} numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"}
            for idx, result in enumerate(results)
        ]
        result_pane.object = summary_card(
            [(item["label"], f"{item['value']} {item['unit']}") for item in outputs],
            title=f"{len(df)} Vertical Scenario(s) Complete",
        )

        new_graphs = []
        plot_images = []
        for idx, result in enumerate(results):
            row = df.iloc[idx]
            lx = float(row["Lx"])
            lz = float(row["Lz"])
            nlay = int(row["nlay"])
            fig = plot_vertical_plume_interactive(
                result.concentration,
                result.x_grid,
                result.z_grid,
                result.plume_length,
                lx,
                max(lz - (lz / nlay), 0.0),
                0.0,
                0.0,
                lz,
            )
            new_graphs.append(pn.pane.Markdown(
                f"**Scenario {idx + 1}** - Lmax {result.plume_length:.2f} m",
                sizing_mode="stretch_width",
            ))
            new_graphs.append(pn.pane.Bokeh(fig, sizing_mode="stretch_width", min_height=430))
            if result.plot_png:
                plot_images.append({
                    "title": f"Vertical Plume Concentration (Scenario {idx + 1})",
                    "bytes": result.plot_png,
                    "caption": f"Simulated contaminant plume - scenario {idx + 1}, vertical cross-section.",
                })
        graphs_column.objects = new_graphs
        logger.info("Vertical multiple graphs_column populated with %d scenario(s)", len(results))

        first_result = results[0]
        state.update({
            "parameters": [{"symbol": "Rows", "name": "Scenario Count", "value": len(df), "unit": "-"}],
            "outputs": outputs,
            "plot_data": {
                "labels": [f"Scenario {i + 1} Numerical" for i in range(len(results))],
                "values": [result.plume_length for result in results],
                "ylabel": "Plume Length (m)",
                "title": "Vertical Numerical",
            },
            "plot_images": plot_images,
            "optional_view": {
                "concentration": first_result.concentration,
                "x_grid": first_result.x_grid,
                "cross_grid": first_result.z_grid,
                "cross_axis_label": "Aquifer Thickness [m]",
                "title": "Vertical Numerical Model - Scenario 1",
            },
        })
        export_btn.visible = True

    def _run(_=None):
        state.pop("optional_view", None)
        optional_views.reset()
        run_btn.disabled = True
        run_btn.name = "Running Vertical Scenarios..."
        graphs_column.objects = []
        comparison_pane.object = None
        export_btn.visible = False
        try:
            df = pd.DataFrame(table.value)
            job_ids = [
                submit_job("vertical_single", {
                    "Lx": float(row["Lx"]),
                    "Ly": float(row["Lz"]),
                    "ncol": int(row["ncol"]),
                    "nrow": int(row["nlay"]),
                    "prsity": float(row["n"]),
                    "al": float(row["alpha_L"]),
                    "av": float(row["atv"]),
                    "gamma": float(row["gamma"]),
                    "cd": float(row["C_D"]),
                    "ca": float(row["C_A"]),
                    "h1": float(row["h1"]),
                    "h2": float(row["h2"]),
                    "hk": float(row["K [m/d]"]),
                    "perlen": float(row["perlen"]),
                    "plume_threshold": float(row["C0"]),
                    "ath": float(row["at"]),
                })
                for _idx, row in df.iterrows()
            ]

            def _poll():
                statuses = [job_status(job_id) for job_id in job_ids]
                counts = {}
                for status in statuses:
                    counts[status["status"]] = counts.get(status["status"], 0) + 1
                result_pane.object = summary_card(
                    [(key, str(value)) for key, value in sorted(counts.items())],
                    title=f"{len(job_ids)} Vertical Scenario Job(s)",
                )
                if any(status["status"] == "failed" for status in statuses):
                    failed = next(status for status in statuses if status["status"] == "failed")
                    result_pane.object = error_card(failed.get("error") or "A numerical scenario failed.")
                    _stop_polling()
                elif all(status["status"] == "done" for status in statuses):
                    _render_completed_results(df, [fetch_result(job_id) for job_id in job_ids])
                    _stop_polling()

            poller["callback"] = pn.state.add_periodic_callback(_poll, 2000, start=True)
            _poll()
        except Exception as exc:
            logger.exception("Vertical numerical scenario run failed")
            result_pane.object = error_card(exc)
            graphs_column.objects = []
            comparison_pane.object = None
            export_btn.visible = False
            _stop_polling()

    run_btn.on_click(_run)
    if query_int("output_only", 0):
        if query_int("run", 0):
            _run()
        return pn.Column(result_pane, graphs_column, comparison_pane, sizing_mode="stretch_width", styles={"gap": "14px"})
    return pn.Column(
        "## Vertical Numerical Model - Multiple",
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
