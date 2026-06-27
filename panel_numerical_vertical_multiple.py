import base64
import html
import json
import logging

import pandas as pd
import panel as pn

from numerical_jobs import fetch_result, job_status, submit_job
from panel_analytical_common import error_card, info_card, query_float, query_int, query_str, summary_card
from panel_theme import report_bridge_html
from panel_numerical_animation import play_growth_once, stop_growth

pn.extension("tabulator", sizing_mode="stretch_width")

logger = logging.getLogger(__name__)


def _result_extent(result, attr, grid):
    value = getattr(result, attr, None)
    if value is not None:
        return float(value)
    try:
        return float(max(grid))
    except (TypeError, ValueError):
        return 0.0


def _post_result_jobs_html(job_ids, rows):
    payload = {
        "type": "numerical-multiple-result",
        "orientation": "vertical",
        "job_ids": list(job_ids),
        "rows": rows,
    }
    encoded = html.escape(json.dumps(payload), quote=True)
    return (
        '<img src="data:," style="display:none" alt="" '
        f'data-payload="{encoded}" '
        "onerror='window.parent.postMessage(JSON.parse(this.dataset.payload), \"*\")'>"
    )


def _external_run_listener_html():
    return """
<img src="data:," style="display:none" alt="" onerror='
if (!window.__castVerticalMultipleRunListener) {
  window.__castVerticalMultipleRunListener = true;
  window.addEventListener("message", function(event) {
    var data = event.data;
    if (!data || data.type !== "run-numerical-multiple" || data.orientation !== "vertical") return;
    var buttons = Array.prototype.slice.call(document.querySelectorAll("button"));
    var button = buttons.find(function(node) {
      return node.textContent && node.textContent.indexOf("Run Vertical Scenarios") !== -1;
    });
    if (button && !button.disabled) button.click();
  });
}
'>
"""


def _rows_from_query():
    raw = query_str("scenario_rows", "")
    if not raw:
        return []
    try:
        rows = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return rows if isinstance(rows, list) else []


def _job_ids_from_query():
    raw = query_str("job_ids", "")
    if not raw:
        return []
    try:
        job_ids = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(job_id) for job_id in job_ids] if isinstance(job_ids, list) else []


def numerical_vertical_multiple_app():
    input_only = bool(query_int("input_only", 0))
    table = pn.widgets.Tabulator(
        pd.DataFrame([
            {
                "Lz": query_float("Lz", query_float("M", 10.0)),
                "grid_size": query_float("grid_size", 1.0),
                "al": query_float("al", 1.0),
                "atv": query_float("atv", query_float("alpha_Tv", 0.1)),
                "gamma": query_float("gamma", 3.5),
                "C_D": query_float("C_D", 5.0),
                "C_A": query_float("C_A", 8.0),
            }
        ]),
        height=95,
        sizing_mode="stretch_width",
        name="Vertical numerical scenarios",
    )
    run_btn = pn.widgets.Button(name="Run Vertical Scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Edit the vertical scenario table and run the simulations."), sizing_mode="stretch_width")
    graphs_column = pn.Column(sizing_mode="stretch_width")
    comparison_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=360)
    state = {}
    poller = {"callback": None}
    anims = []  # list of one-shot growth holders for active scenario animations

    report_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")
    job_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")
    run_listener = pn.pane.HTML(_external_run_listener_html(), height=0, margin=0, sizing_mode="fixed")

    def _reset_anims():
        for holder in anims:
            stop_growth(holder)
        anims.clear()

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

        _reset_anims()
        new_graphs = []
        plot_images = []
        scenario_rows = list(df.to_dict("records"))
        for idx, result in enumerate(results):
            row = scenario_rows[idx]
            new_graphs.append(pn.pane.Markdown(
                f"**Scenario {idx + 1}** - Lmax {result.plume_length:.2f} m",
                sizing_mode="stretch_width",
            ))
            scenario_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
            dom_len = _result_extent(result, "domain_length", result.x_grid)
            # porosity / K / gradient are model defaults for the multiple run (not
            # exposed in the scenario table), so the footer reflects those.
            footer_meta = (
                f"L_D = {dom_len:.2f} m  |  Δx=Δz = {float(row['grid_size']):.2f} m  |  "
                f"porosity = 0.30  |  K = 8.64 m/d  |  gradient = 0.0125  |  "
                f"Péclet = {getattr(result, 'peclet', 0.0):.2f}  |  Courant target = 5"
            )
            holder = play_growth_once(
                scenario_pane,
                dict(
                    concentration=result.concentration,
                    x_grid=result.x_grid,
                    cross_grid=result.z_grid,
                    ca=float(row["C_A"]),
                    cd=float(row["C_D"]),
                    gamma=float(row["gamma"]),
                    plume_length=result.plume_length,
                    domain_length=dom_len,
                    cross_extent=_result_extent(result, "aquifer_thickness", result.z_grid),
                    orientation="vertical",
                    footer_meta=footer_meta,
                ),
            )
            anims.append(holder)
            new_graphs.append(scenario_pane)
            if result.plot_png:
                plot_images.append({
                    "title": f"Vertical Plume Concentration (Scenario {idx + 1})",
                    "bytes": result.plot_png,
                    "max_height_mm": 52,
                    "caption": f"Simulated contaminant plume - scenario {idx + 1}, vertical cross-section.",
                })
        graphs_column.objects = new_graphs
        logger.info("Vertical multiple graphs_column populated with %d scenario(s)", len(results))

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
        })
        report_bridge.object = report_bridge_html(
            "Numerical Vertical Model - Multiple Simulation", "Numerical Vertical",
            "numerical_vertical_multiple_report.pdf",
            parameters=state["parameters"], outputs=state["outputs"],
            plot_data=state.get("plot_data"),
            plot_images_b64=[
                {
                    "title": img["title"],
                    "caption": img.get("caption", ""),
                    "b64": base64.b64encode(img["bytes"]).decode(),
                    "max_height_mm": img.get("max_height_mm", 52),
                }
                for img in (state.get("plot_images") or [])
            ],
        )

    def _run(_=None):
        _reset_anims()
        run_btn.disabled = True
        run_btn.name = "Running Vertical Scenarios..."
        graphs_column.objects = []
        comparison_pane.object = None
        report_bridge.object = report_bridge_html(clear=True)
        try:
            df = pd.DataFrame(table.value)
            scenario_rows = [
                {
                    "Lz": float(row["Lz"]),
                    "grid_size": float(row["grid_size"]),
                    "al": float(row["al"]),
                    "atv": float(row["atv"]),
                    "gamma": float(row["gamma"]),
                    "C_D": float(row["C_D"]),
                    "C_A": float(row["C_A"]),
                }
                for _idx, row in df.iterrows()
            ]
            job_ids = [
                submit_job("vertical_single", {
                    "Lz": row["Lz"],
                    "grid_size": row["grid_size"],
                    "al": row["al"],
                    "atv": row["atv"],
                    "gamma": row["gamma"],
                    "cd": row["C_D"],
                    "ca": row["C_A"],
                })
                for row in scenario_rows
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
                    if input_only:
                        result_pane.object = summary_card(
                            [("Completed scenarios", str(len(job_ids)))],
                            title="Vertical Scenario Jobs Complete",
                        )
                        job_bridge.object = _post_result_jobs_html(job_ids, scenario_rows)
                    else:
                        _render_completed_results(df, [fetch_result(job_id) for job_id in job_ids])
                    _stop_polling()

            poller["callback"] = pn.state.add_periodic_callback(_poll, 2000, start=True)
            _poll()
        except Exception as exc:
            logger.exception("Vertical numerical scenario run failed")
            result_pane.object = error_card(exc)
            graphs_column.objects = []
            comparison_pane.object = None
            report_bridge.object = report_bridge_html(clear=True)
            _stop_polling()

    run_btn.on_click(_run)
    if input_only:
        run_btn.height = 0
        run_btn.margin = 0
        run_btn.styles = {
            "height": "0",
            "min-height": "0",
            "overflow": "hidden",
            "opacity": "0",
            "pointer-events": "none",
            "position": "absolute",
            "left": "-9999px",
        }
        return pn.Column(
            "## Vertical Numerical Model - Multiple",
            table,
            run_btn,
            job_bridge,
            run_listener,
            sizing_mode="stretch_width",
            styles={"gap": "8px"},
        )

    if query_int("output_only", 0):
        job_ids = _job_ids_from_query()
        rows = _rows_from_query()
        if job_ids:
            try:
                results = [fetch_result(job_id) for job_id in job_ids]
                _render_completed_results(pd.DataFrame(rows), results)
            except Exception as exc:
                logger.exception("Vertical numerical scenario results could not be loaded")
                result_pane.object = error_card(exc)
        elif query_int("run", 0):
            _run()
        else:
            result_pane.object = info_card("Run vertical scenarios to display the generated graphs.")
        return pn.Column(result_pane, graphs_column, report_bridge, sizing_mode="stretch_width", styles={"gap": "14px"})
    return pn.Column(
        "## Vertical Numerical Model - Multiple",
        table,
        run_btn,
        result_pane,
        graphs_column,
        report_bridge,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
