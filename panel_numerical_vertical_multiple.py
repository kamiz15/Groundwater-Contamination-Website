import logging
import sys
import math
import os

import panel as pn

from data_queries import get_user_sites_rows
from numerical_input_validation import user_instruction
from numerical_jobs import fetch_result, job_status, submit_job
from panel_analytical_common import comparison_plot, error_card, info_card, query_int, query_str, summary_card
from panel_auth import authenticated_email
from panel_numerical_multiple_common import (
    numerical_field_specs, numerical_multiple_app,
)
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


# --- the contract panel_numerical_multiple_common builds the page from --------
ORIENTATION = "vertical"
TITLE = "Numerical Vertical Model"
JOB_KIND = "vertical_single"
# First entries are the job payload keys; C_D/C_A are submitted as cd/ca.
SCENARIO_COLUMNS = ("Lz", "grid_size", "al", "atv", "gamma", "C_D", "C_A")
COLUMN_TITLES = {
    "Lz": "Aquifer Thickness L_z [m]",
    "grid_size": "Grid Size [m]",
    "al": "Longitudinal Dispersivity \u03b1_L [m]",
    "atv": "Vertical Transverse Dispersivity \u03b1_Tv [m]",
    "gamma": "Stoichiometric Ratio \u03b3 [-]",
    "C_D": "Donor Concentration at Source C_D^0 [mg/L]",
    "C_A": "Acceptor Concentration at Source C_A^0 [mg/L]",
}
DEFAULT_ROW = {"Lz": 10.0, "grid_size": 1.0, "al": 1.0, "atv": 0.1,
               "gamma": 3.5, "C_D": 5.0, "C_A": 8.0}
SITE_ROW = _vertical_site_row


def VALIDATE_ROWS(rows):
    """Refuse a run the solver cannot grid before it queues anything."""
    issues = _vertical_feasibility_issues(rows)
    if issues:
        raise ValueError("Fix these scenarios, then run again. " + " ".join(issues))


def selected_site_ids():
    """Site ids from ?compare_sites=1,2,3 - a shared link opens on its sites."""
    return _selected_site_ids()


def numerical_vertical_multiple_app():
    return numerical_multiple_app(sys.modules[__name__])


def numerical_field_specs_vertical():
    """What the page's Add-row dialog renders for this orientation."""
    return numerical_field_specs(sys.modules[__name__])
