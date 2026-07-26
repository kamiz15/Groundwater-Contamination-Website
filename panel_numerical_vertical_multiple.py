import html
import json
import logging
import math
import os

import pandas as pd
import panel as pn

from data_queries import get_user_sites_rows
from numerical_jobs import fetch_result, job_status, submit_job
from panel_analytical_common import comparison_plot, error_card, info_card, query_float, query_int, query_str, summary_card
from panel_auth import authenticated_email
from panel_theme import report_bridge_html
from param_meta import table_titles
from symbol_registry import db_to_model

pn.extension("tabulator", sizing_mode="stretch_width")

logger = logging.getLogger(__name__)

# Each row triggers a full MODFLOW run, so cap how many a single comparison can
# queue to keep one user from flooding the job worker.
MAX_MULTIPLE_RUNS = 12

# Scenario table columns (the seven solver inputs; the row index labels each
# scenario). These are the only inputs the vertical multiple run reads;
# everything else (hk, porosity, gradient, ...) is defaulted by the worker,
# exactly like the single page, so a site needs none of those to be modelled.
SCENARIO_COLUMNS = ["Lz", "grid_size", "al", "atv", "gamma", "C_D", "C_A"]


def _max_grid_cells():
    return int(os.getenv("NUMERICAL_MAX_CELLS", os.getenv("MAX_GRID_CELLS", "40000")))


def _vertical_domain_length(row):
    lz = float(row["Lz"])
    atv = float(row["atv"])
    gamma = float(row["gamma"])
    cd = float(row["C_D"])
    ca = float(row["C_A"])
    ratio = (4.0 * gamma * cd + ca) / (math.pi * ca)
    return 1.5 * (4.0 * lz ** 2) / (math.pi ** 2 * atv) * math.log(ratio)


def _vertical_feasibility_issues(rows):
    issues = []
    max_cells = _max_grid_cells()
    for idx, row in enumerate(rows, start=1):
        label = str(row.get("label") or row.get("Site") or f"Scenario {idx}")
        try:
            values = {
                "Lz": float(row["Lz"]),
                "grid_size": float(row["grid_size"]),
                "al": float(row["al"]),
                "atv": float(row["atv"]),
                "gamma": float(row["gamma"]),
                "C_D": float(row["C_D"]),
                "C_A": float(row["C_A"]),
            }
        except (KeyError, TypeError, ValueError):
            issues.append(f"{label}: all scenario inputs must be numeric.")
            continue
        if any(not math.isfinite(value) or value <= 0 for value in values.values()):
            issues.append(f"{label}: all scenario inputs must be positive finite numbers.")
            continue

        lz = values["Lz"]
        grid_size = values["grid_size"]
        nlay = int(lz / grid_size)
        if nlay < 2:
            issues.append(f"{label}: grid_size {grid_size:.3g} m leaves fewer than 2 vertical layers; reduce grid_size.")
            continue

        domain_length = _vertical_domain_length(values)
        if not math.isfinite(domain_length) or domain_length <= 0:
            issues.append(
                f"{label}: chemistry produces an invalid vertical domain length; "
                "increase C_D or gamma, or reduce C_A."
            )
            continue

        ncol = int(domain_length / grid_size)
        if ncol < 2:
            issues.append(f"{label}: grid_size {grid_size:.3g} m leaves fewer than 2 columns; reduce grid_size.")
            continue

        total_cells = ncol * nlay
        if total_cells > max_cells:
            recommended = math.sqrt((domain_length * lz) / max_cells)
            issues.append(
                f"{label}: derived domain is L_D={domain_length:.2f} m by Lz={lz:.2f} m; "
                f"grid_size {grid_size:.3g} m creates {ncol:,} x {nlay:,} = {total_cells:,} cells, "
                f"above the {max_cells:,}-cell limit. Use grid_size >= {recommended:.2f} m."
            )
    return issues


def _num(canonical, key, default):
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


def _vertical_site_row(site):
    """Map one database site to a scenario row, the same resilient way the single
    page reads it (db_to_model): fill only the values the site carries, default
    the rest. Returns (row, ready, status) where `ready` drives the Ready-first
    ordering and `status` is shown in the picker."""
    canonical = db_to_model(site, "numerical")
    issues = []
    lz, issue = _num(canonical, "M", 10.0)
    if issue:
        issues.append(issue)
    atv, issue = _num(canonical, "alpha_Tv", 0.1)
    if issue:
        issues.append(issue)
    gamma, issue = _num(canonical, "gamma", 3.5)
    if issue:
        issues.append(issue)
    cd, issue = _num(canonical, "C_D", 5.0)
    if issue:
        issues.append(issue)
    ca, issue = _num(canonical, "C_A", 8.0)
    if issue:
        issues.append(issue)

    row = {
        "Lz": lz,
        "grid_size": 1.0,
        "al": 1.0,
        "atv": atv,
        "gamma": gamma,
        "C_D": cd,
        "C_A": ca,
    }
    if issues:
        status = "; ".join(issues)
        ready = False
    elif "M" not in canonical:
        status = "No aquifer thickness - will use defaults"
        ready = False
    else:
        status = "Ready"
        ready = True
    return row, ready, status


def _post_result_jobs_html(job_ids, rows, error=None, seq=0):
    # seq makes every post unique: the HTML pane only re-renders (and so only
    # re-fires the postMessage) when its content actually changes.
    payload = {
        "type": "numerical-multiple-result",
        "orientation": "vertical",
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


def _external_run_listener_html():
    # Bokeh 3 renders every widget inside shadow roots, so a plain
    # document.querySelectorAll never sees the run button - the search has to
    # walk into each shadowRoot.
    return """
<img src="data:," style="display:none" alt="" onerror='
if (!window.__castVerticalMultipleRunListener) {
  window.__castVerticalMultipleRunListener = true;
  window.addEventListener("message", function(event) {
    var data = event.data;
    if (!data || data.type !== "run-numerical-multiple" || data.orientation !== "vertical") return;
    var stack = [document];
    while (stack.length) {
      var root = stack.pop();
      var nodes = root.querySelectorAll("*");
      for (var i = 0; i < nodes.length; i++) {
        var node = nodes[i];
        if (node.shadowRoot) stack.push(node.shadowRoot);
        if (node.tagName !== "BUTTON") continue;
        if (!node.textContent || node.textContent.indexOf("Run Vertical Scenarios") === -1) continue;
        if (!node.disabled) node.click();
        return;
      }
    }
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


def _build_site_picker(table):
    """Build the click-to-add uploaded-site picker.

    Returns (widget, note). The widget is a read-only Tabulator listing the
    user's sites with Ready ones first; clicking a row appends that site's mapped
    scenario row to `table`. When the user has no sites the widget is None and a
    note explains there is nothing to add.
    """
    try:
        email = authenticated_email()
        sites = get_user_sites_rows(email) if email else []
    except Exception:
        logger.exception("Could not load uploaded sites for the vertical multiple picker")
        sites = []

    entries = []
    for site in sites:
        row, ready, status = _vertical_site_row(site)
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

    table_rows = [{
        "ID": entry["id"],
        "Site": entry["name"],
        "Compound": entry["compound"],
        "Lz": entry["row"]["Lz"],
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
            table.value = combined[SCENARIO_COLUMNS]
        guard["busy"] = True
        try:
            widget.selection = []
        finally:
            guard["busy"] = False

    widget.param.watch(_on_select, "selection")
    return widget, None


def numerical_vertical_multiple_app():
    input_only = bool(query_int("input_only", 0))
    output_only = bool(query_int("output_only", 0))

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
        ], columns=SCENARIO_COLUMNS),
        titles=table_titles(SCENARIO_COLUMNS, "numerical_vertical"),
        height=160,
        sizing_mode="stretch_width",
        name="Vertical numerical scenarios",
    )

    site_table = None
    site_note = None
    if not output_only:
        site_table, site_note = _build_site_picker(table)

    run_btn = pn.widgets.Button(name="Run Vertical Scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Edit the scenario table or click uploaded sites to add them, then run."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    state = {}
    poller = {"callback": None}

    report_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")
    job_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")
    run_listener = pn.pane.HTML(_external_run_listener_html(), height=0, margin=0, sizing_mode="fixed")
    bridge_state = {"posts": 0}

    def _post_to_parent(job_ids, rows, error=None):
        bridge_state["posts"] += 1
        job_bridge.object = _post_result_jobs_html(job_ids, rows, error=error, seq=bridge_state["posts"])

    def _stop_polling():
        run_btn.disabled = False
        if poller["callback"] is not None:
            poller["callback"].stop()
            poller["callback"] = None

    def _collect_scenarios():
        """Every row in the scenario table is one run; the row index labels it."""
        rows = []
        manual_df = pd.DataFrame(table.value)
        for idx, raw in manual_df.iterrows():
            rows.append({
                "label": f"Scenario {idx + 1}",
                "Lz": float(raw["Lz"]),
                "grid_size": float(raw["grid_size"]),
                "al": float(raw["al"]),
                "atv": float(raw["atv"]),
                "gamma": float(raw["gamma"]),
                "C_D": float(raw["C_D"]),
                "C_A": float(raw["C_A"]),
            })
        if not rows:
            raise ValueError("Add at least one scenario row or click an uploaded site.")
        if len(rows) > MAX_MULTIPLE_RUNS:
            raise ValueError(
                f"Too many runs: limit is {MAX_MULTIPLE_RUNS} per comparison (you have {len(rows)})."
            )
        feasibility_issues = _vertical_feasibility_issues(rows)
        if feasibility_issues:
            raise ValueError("Adjust these vertical scenarios before running: " + " ".join(feasibility_issues))
        return rows

    def _render_completed_results(rows, results):
        labels = [row.get("label", f"Run {idx + 1}") for idx, row in enumerate(rows)]
        values = [float(result.plume_length) for result in results]
        outputs = [
            {"label": f"{labels[idx]} L_max", "value": f"{value:.2f}", "unit": "m"}
            for idx, value in enumerate(values)
        ]
        result_pane.object = summary_card(
            [(item["label"], f"{item['value']} {item['unit']}") for item in outputs],
            title=f"{len(values)} Vertical Run(s) Complete",
        )

        plot_pane.object = comparison_plot(
            "Vertical Numerical - L_max by scenario / site",
            "Numerical L_max",
            list(range(1, len(values) + 1)),
            values,
            0,
            "",
            "Scenario / Site",
        )
        logger.info("Vertical multiple Lmax comparison rendered for %d run(s)", len(values))

        state.update({
            "parameters": [{"symbol": "Runs", "name": "Run Count", "value": len(values), "unit": "-"}],
            "outputs": outputs,
            "plot_data": {
                "labels": labels,
                "values": values,
                "ylabel": "Maximum Plume Length L_max [m]",
                "title": "Vertical Numerical - L_max Comparison",
            },
        })
        report_bridge.object = report_bridge_html(
            "Numerical Vertical Model - Multiple Simulation", "Numerical Vertical",
            "numerical_vertical_multiple_report.pdf",
            parameters=state["parameters"], outputs=state["outputs"],
            plot_data=state.get("plot_data"),
        )

    def _run(_=None):
        run_btn.disabled = True
        plot_pane.object = None
        report_bridge.object = report_bridge_html(clear=True)
        try:
            scenario_rows = _collect_scenarios()
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
                # The input panel stays quiet (its status/summary lives in the
                # separate output panel); only surface errors here.
                if not input_only:
                    result_pane.object = summary_card(
                        [(key, str(value)) for key, value in sorted(counts.items())],
                        title=f"{len(job_ids)} Vertical Run(s)",
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
                        _render_completed_results(scenario_rows, [fetch_result(job_id) for job_id in job_ids])
                    _stop_polling()

            poller["callback"] = pn.state.add_periodic_callback(_poll, 2000, start=True)
            _poll()
        except Exception as exc:
            logger.exception("Vertical numerical scenario run failed")
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
            "## Vertical Numerical Model - Multiple",
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
        job_ids = _job_ids_from_query()
        rows = _rows_from_query()
        if job_ids:
            try:
                results = [fetch_result(job_id) for job_id in job_ids]
                _render_completed_results(rows or [{} for _ in job_ids], results)
            except Exception as exc:
                logger.exception("Vertical numerical scenario results could not be loaded")
                result_pane.object = error_card(exc)
        elif query_int("run", 0):
            _run()
        else:
            result_pane.object = info_card("Run vertical scenarios to display the L_max comparison.")
        return pn.Column(result_pane, plot_pane, report_bridge, sizing_mode="stretch_width", styles={"gap": "14px"})

    return pn.Column(
        "## Vertical Numerical Model - Multiple",
        table,
        site_section,
        run_btn,
        result_pane,
        plot_pane,
        report_bridge,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
