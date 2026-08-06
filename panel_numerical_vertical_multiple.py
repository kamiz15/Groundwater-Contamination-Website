import logging
import math
import os

import panel as pn

from data_queries import get_user_sites_rows
from numerical_input_validation import user_instruction
from numerical_jobs import fetch_result, job_status, submit_job
from panel_analytical_common import comparison_plot, error_card, info_card, query_int, query_str, summary_card
from panel_auth import authenticated_email
from panel_theme import report_bridge_html
from symbol_registry import db_to_model

pn.extension("tabulator", sizing_mode="stretch_width")

logger = logging.getLogger(__name__)

from settings import NUMERICAL_MULTIPLE_MAX_RUNS as MAX_MULTIPLE_RUNS



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
            issues.append(f"{label}: enter a number for every input.")
            continue
        if any(not math.isfinite(value) or value <= 0 for value in values.values()):
            issues.append(f"{label}: enter a value greater than zero for every input.")
            continue

        lz = values["Lz"]
        grid_size = values["grid_size"]
        nlay = int(lz / grid_size)
        if nlay < 2:
            issues.append(f"{label}: reduce the grid size.")
            continue

        domain_length = _vertical_domain_length(values)
        if not math.isfinite(domain_length) or domain_length <= 0:
            issues.append(f"{label}: increase C_D or gamma, or reduce C_A.")
            continue

        ncol = int(domain_length / grid_size)
        if ncol < 2:
            issues.append(f"{label}: reduce the grid size.")
            continue

        total_cells = ncol * nlay
        if total_cells > max_cells:
            recommended = math.sqrt((domain_length * lz) / max_cells)
            issues.append(f"{label}: increase the grid size to at least {recommended:.2f} m.")
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


def _selected_site_ids():
    """Site ids from ?compare_sites=1,2,3. Nothing picked means nothing runs -
    on the numerical pages every site is a full MODFLOW/MT3DMS job."""
    ids = []
    for part in query_str("compare_sites", "").split(","):
        try:
            ids.append(int(part))
        except ValueError:
            continue
    return ids


def _scenarios_from_sites():
    """One scenario per site picked in the sidebar, mapped the way the single
    page reads a site. The site unit labels the run."""
    wanted = _selected_site_ids()
    if not wanted:
        raise ValueError("Pick at least one site in the Compare Sites list, then run.")
    try:
        email = authenticated_email()
        sites = get_user_sites_rows(email) if email else []
    except Exception:
        logger.exception("Could not load sites for the vertical multiple run")
        raise ValueError("Your sites could not be loaded. Please try again.")

    by_id = {int(site["id"]): site for site in sites}
    rows = []
    for site_id in wanted:
        site = by_id.get(site_id)
        if site is None:
            continue
        row, _ready, _status = _vertical_site_row(site)
        row["label"] = site.get("site_unit") or f"Site {site.get('display_id') or site_id}"
        rows.append(row)
    if not rows:
        raise ValueError("None of the picked sites could be loaded.")
    if len(rows) > MAX_MULTIPLE_RUNS:
        raise ValueError(
            f"Too many runs: limit is {MAX_MULTIPLE_RUNS} sites per comparison (you picked {len(rows)})."
        )
    return rows


def numerical_vertical_multiple_app():
    result_pane = pn.pane.HTML(info_card("Pick sites in the Compare Sites list, then run the vertical scenarios."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    state = {}
    poller = {"callback": None}

    report_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")

    def _stop_polling():
        if poller["callback"] is not None:
            poller["callback"].stop()
            poller["callback"] = None

    def _collect_scenarios():
        rows = _scenarios_from_sites()
        feasibility_issues = _vertical_feasibility_issues(rows)
        if feasibility_issues:
            raise ValueError("Fix these scenarios, then run again. " + " ".join(feasibility_issues))
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
            "Vertical Numerical - L_max by site",
            "Numerical L_max",
            list(range(1, len(values) + 1)),
            values,
            0,
            "",
            "Site Number",
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
                result_pane.object = summary_card(
                    [(key, str(value)) for key, value in sorted(counts.items())],
                    title=f"{len(job_ids)} Vertical Run(s)",
                )
                if any(status["status"] == "failed" for status in statuses):
                    failed = next(status for status in statuses if status["status"] == "failed")
                    message = user_instruction(failed.get("error"))
                    result_pane.object = error_card(message)
                    _stop_polling()
                elif all(status["status"] == "done" for status in statuses):
                    _render_completed_results(scenario_rows, [fetch_result(job_id) for job_id in job_ids])
                    _stop_polling()

            poller["callback"] = pn.state.add_periodic_callback(_poll, 2000, start=True)
            _poll()
        except Exception as exc:
            logger.exception("Vertical numerical scenario run failed")
            result_pane.object = error_card(user_instruction(exc))
            plot_pane.object = None
            report_bridge.object = report_bridge_html(clear=True)
            _stop_polling()

    if query_int("run", 0):
        _run()
    else:
        result_pane.object = info_card("Pick sites in the Compare Sites list, then press Run.")
    return pn.Column(result_pane, plot_pane, report_bridge, sizing_mode="stretch_width", styles={"gap": "14px"})
