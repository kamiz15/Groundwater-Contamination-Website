"""Shared engine for the horizontal/vertical numerical multiple panels.

The two orientation modules are identical except for wording, scenario
columns, DB mapping, job kind, and (vertical only) a feasibility check, so
the whole panel lives here once. Each orientation module passes itself
(``sys.modules[__name__]``) and the engine resolves every dependency through
that module's namespace — tests monkeypatch ``query_*``, ``submit_job``,
``job_status``, ``fetch_result``, ``authenticated_email`` and
``get_user_sites_rows`` on the orientation modules, and late ``mod.*``
lookups keep those seams working.

Required module attributes: ORIENTATION, SCENARIO_COLUMNS (first five are the
job-payload keys; C_D/C_A are submitted as cd/ca), JOB_KIND, PICKER_COLUMN
(header, row key), SITE_ROW, DEFAULT_ROW. Optional: VALIDATE_ROWS(rows).
"""

import html
import json
import logging
import math

import pandas as pd
import panel as pn

from panel_analytical_common import comparison_plot, error_card, info_card, summary_card
from panel_theme import report_bridge_html

pn.extension("tabulator", sizing_mode="stretch_width")

logger = logging.getLogger(__name__)

# Each row triggers a full MODFLOW run, so cap how many a single comparison can
# queue to keep one user from flooding the job worker.
MAX_MULTIPLE_RUNS = 12


def db_num(canonical, key, default):
    """Resolve one DB-mapped value: missing -> default (no issue); present but
    non-positive/non-numeric -> default plus a human-readable issue string."""
    raw = canonical.get(key)
    if raw is None:
        return default, None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default, f"{key} is not numeric"
    if not math.isfinite(value) or value <= 0:
        return default, f"{key} must be > 0"
    return value, None


def _post_result_jobs_html(orientation, job_ids, rows, error=None, seq=0):
    # seq makes every post unique: the HTML pane only re-renders (and so only
    # re-fires the postMessage) when its content actually changes.
    payload = {
        "type": "numerical-multiple-result",
        "orientation": orientation,
        "job_ids": list(job_ids),
        "rows": rows,
        "seq": seq,
    }
    if error is not None:
        payload["error"] = str(error)
    encoded = html.escape(json.dumps(payload), quote=True)
    return (
        '<img src="data:," style="display:none" alt="" '
        f'data-payload="{encoded}" '
        "onerror='window.parent.postMessage(JSON.parse(this.dataset.payload), \"*\")'>"
    )


# Bokeh 3 renders every widget inside shadow roots, so a plain
# document.querySelectorAll never sees the run button - the search has to
# walk into each shadowRoot.
_RUN_LISTENER_HTML = """
<img src="data:," style="display:none" alt="" onerror='
if (!window.__cast__WORD__MultipleRunListener) {
  window.__cast__WORD__MultipleRunListener = true;
  window.addEventListener("message", function(event) {
    var data = event.data;
    if (!data || data.type !== "run-numerical-multiple" || data.orientation !== "__ORIENT__") return;
    var stack = [document];
    while (stack.length) {
      var root = stack.pop();
      var nodes = root.querySelectorAll("*");
      for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        if (node.shadowRoot) stack.push(node.shadowRoot);
        if (node.tagName !== "BUTTON") continue;
        if (!node.textContent || node.textContent.indexOf("Run __WORD__ Scenarios") === -1) continue;
        if (!node.disabled) node.click();
        return;
      }
    }
  });
}
'>
"""


def external_run_listener_html(orientation):
    return _RUN_LISTENER_HTML.replace("__ORIENT__", orientation).replace(
        "__WORD__", orientation.capitalize()
    )


def _json_list_from_query(mod, name):
    raw = mod.query_str(name, "")
    if not raw:
        return []
    try:
        values = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return values if isinstance(values, list) else []


def build_site_picker(mod, table):
    """Build the click-to-add uploaded-site picker.

    Returns (widget, note). The widget is a read-only Tabulator listing the
    user's sites with Ready ones first; clicking a row appends that site's mapped
    scenario row to `table`. When the user has no sites the widget is None and a
    note explains there is nothing to add.
    """
    try:
        email = mod.authenticated_email()
        sites = mod.get_user_sites_rows(email) if email else []
    except Exception:
        logger.exception("Could not load uploaded sites for the %s multiple picker", mod.ORIENTATION)
        sites = []

    entries = []
    for site in sites:
        row, ready, status = mod.SITE_ROW(site)
        entries.append({
            "id": site.get("display_id", site.get("id")),
            "name": site.get("site_unit") or "",
            "compound": site.get("compound") or "",
            "row": row,
            "ready": ready,
            "status": status,
        })
    # Ready sites first, then the rest; stable within each group.
    entries.sort(key=lambda e: 0 if e["ready"] else 1)

    if not entries:
        return None, info_card("No uploaded sites yet - edit the table above or upload sites first.")

    header, row_key = mod.PICKER_COLUMN
    table_rows = [{
        "ID": entry["id"],
        "Site": entry["name"],
        "Compound": entry["compound"],
        header: entry["row"][row_key],
        "Status": entry["status"],
    } for entry in entries]

    widget = pn.widgets.Tabulator(
        pd.DataFrame(table_rows),
        name="Uploaded sites",
        disabled=True,
        show_index=False,
        selectable=True,
        sizing_mode="stretch_width",
        height=260,
    )

    guard = {"busy": False}

    def _on_select(event):
        if guard["busy"]:
            return
        selected = list(event.new or [])
        new_rows = [entries[i]["row"] for i in selected if 0 <= i < len(entries)]
        if new_rows:
            current = pd.DataFrame(table.value)
            combined = pd.concat([current, pd.DataFrame(new_rows)], ignore_index=True)
            table.value = combined[mod.SCENARIO_COLUMNS]
        guard["busy"] = True
        try:
            widget.selection = []
        finally:
            guard["busy"] = False

    widget.param.watch(_on_select, "selection")
    return widget, None


def numerical_multiple_app(mod):
    orientation = mod.ORIENTATION
    word = orientation.capitalize()
    columns = mod.SCENARIO_COLUMNS

    input_only = bool(mod.query_int("input_only", 0))
    output_only = bool(mod.query_int("output_only", 0))

    table = pn.widgets.Tabulator(
        pd.DataFrame([mod.DEFAULT_ROW()], columns=columns),
        height=160,
        sizing_mode="stretch_width",
        name=f"{word} numerical scenarios",
    )

    site_table = None
    site_note = None
    if not output_only:
        site_table, site_note = build_site_picker(mod, table)

    run_btn = pn.widgets.Button(name=f"Run {word} Scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Edit the scenario table or click uploaded sites to add them, then run."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    state = {}
    poller = {"callback": None}

    report_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")
    job_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")
    run_listener = pn.pane.HTML(external_run_listener_html(orientation), height=0, margin=0, sizing_mode="fixed")
    bridge_state = {"posts": 0}

    def _post_to_parent(job_ids, rows, error=None):
        bridge_state["posts"] += 1
        job_bridge.object = _post_result_jobs_html(orientation, job_ids, rows, error=error, seq=bridge_state["posts"])

    def _stop_polling():
        run_btn.disabled = False
        run_btn.name = f"Run {word} Scenarios"
        if poller["callback"] is not None:
            poller["callback"].stop()
            poller["callback"] = None

    def _collect_scenarios():
        """Every row in the scenario table is one run; the row index labels it."""
        rows = []
        manual_df = pd.DataFrame(table.value)
        for idx, raw in manual_df.iterrows():
            row = {"label": f"Scenario {idx + 1}"}
            row.update({key: float(raw[key]) for key in columns})
            rows.append(row)
        if not rows:
            raise ValueError("Add at least one scenario row or click an uploaded site.")
        if len(rows) > MAX_MULTIPLE_RUNS:
            raise ValueError(
                f"Too many runs: limit is {MAX_MULTIPLE_RUNS} per comparison (you have {len(rows)})."
            )
        validate = getattr(mod, "VALIDATE_ROWS", None)
        if validate is not None:
            validate(rows)
        return rows

    def _render_completed_results(rows, results):
        labels = [row.get("label", f"Run {idx + 1}") for idx, row in enumerate(rows)]
        values = [float(result.plume_length) for result in results]
        outputs = [
            {"label": f"{labels[idx]} Lmax", "value": f"{value:.2f}", "unit": "m"}
            for idx, value in enumerate(values)
        ]
        result_pane.object = summary_card(
            [(item["label"], f"{item['value']} {item['unit']}") for item in outputs],
            title=f"{len(values)} {word} Run(s) Complete",
        )

        plot_pane.object = comparison_plot(
            f"{word} Numerical - Lmax by scenario / site",
            "Numerical Lmax",
            list(range(1, len(values) + 1)),
            values,
            0,
            "",
            "Scenario / Site",
        )
        logger.info("%s multiple Lmax comparison rendered for %d run(s)", word, len(values))

        state.update({
            "parameters": [{"symbol": "Runs", "name": "Run Count", "value": len(values), "unit": "-"}],
            "outputs": outputs,
            "plot_data": {
                "labels": labels,
                "values": values,
                "ylabel": "Plume Length (m)",
                "title": f"{word} Numerical - Lmax Comparison",
            },
        })
        report_bridge.object = report_bridge_html(
            f"Numerical {word} Model - Multiple Simulation", f"Numerical {word}",
            f"numerical_{orientation}_multiple_report.pdf",
            parameters=state["parameters"], outputs=state["outputs"],
            plot_data=state.get("plot_data"),
        )

    def _run(_=None):
        run_btn.disabled = True
        run_btn.name = f"Running {word} Scenarios..."
        plot_pane.object = None
        report_bridge.object = report_bridge_html(clear=True)
        try:
            scenario_rows = _collect_scenarios()
            job_ids = [
                mod.submit_job(mod.JOB_KIND, {
                    **{key: row[key] for key in columns if key not in ("C_D", "C_A")},
                    "cd": row["C_D"],
                    "ca": row["C_A"],
                })
                for row in scenario_rows
            ]

            def _poll():
                statuses = [mod.job_status(job_id) for job_id in job_ids]
                counts = {}
                for status in statuses:
                    counts[status["status"]] = counts.get(status["status"], 0) + 1
                # The input panel stays quiet (its status/summary lives in the
                # separate output panel); only surface errors here.
                if not input_only:
                    result_pane.object = summary_card(
                        [(key, str(value)) for key, value in sorted(counts.items())],
                        title=f"{len(job_ids)} {word} Run(s)",
                    )
                if any(status["status"] == "failed" for status in statuses):
                    failed = next(status for status in statuses if status["status"] == "failed")
                    message = failed.get("error") or "A numerical scenario failed."
                    result_pane.object = error_card(message)
                    if input_only:
                        _post_to_parent([], [], error=message)
                    _stop_polling()
                elif all(status["status"] == "done" for status in statuses):
                    if input_only:
                        result_pane.object = ""
                        _post_to_parent(job_ids, scenario_rows)
                    else:
                        _render_completed_results(scenario_rows, [mod.fetch_result(job_id) for job_id in job_ids])
                    _stop_polling()

            poller["callback"] = pn.state.add_periodic_callback(_poll, 2000, start=True)
            _poll()
        except Exception as exc:
            logger.exception("%s numerical scenario run failed", word)
            result_pane.object = error_card(exc)
            plot_pane.object = None
            report_bridge.object = report_bridge_html(clear=True)
            if input_only:
                _post_to_parent([], [], error=exc)
            _stop_polling()

    run_btn.on_click(_run)

    site_section = pn.Column(
        "### Uploaded sites (click to add)", site_table, sizing_mode="stretch_width", styles={"gap": "6px"}
    ) if site_table is not None else pn.pane.HTML(site_note or "", sizing_mode="stretch_width")

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
        result_pane.object = ""  # input panel shows no result box, only errors
        return pn.Column(
            f"## {word} Numerical Model - Multiple",
            table,
            site_section,
            result_pane,
            run_btn,
            job_bridge,
            run_listener,
            sizing_mode="stretch_width",
            styles={"gap": "8px"},
        )

    if output_only:
        job_ids = [str(job_id) for job_id in _json_list_from_query(mod, "job_ids")]
        rows = _json_list_from_query(mod, "scenario_rows")
        if job_ids:
            try:
                _render_completed_results(rows or [{} for _ in job_ids], [mod.fetch_result(job_id) for job_id in job_ids])
            except Exception as exc:
                logger.exception("%s numerical scenario results could not be loaded", word)
                result_pane.object = error_card(exc)
        elif mod.query_int("run", 0):
            _run()
        else:
            result_pane.object = info_card(f"Run {orientation} scenarios to display the Lmax comparison.")
        return pn.Column(result_pane, plot_pane, report_bridge, sizing_mode="stretch_width", styles={"gap": "14px"})

    return pn.Column(
        f"## {word} Numerical Model - Multiple",
        table,
        site_section,
        run_btn,
        result_pane,
        plot_pane,
        report_bridge,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
