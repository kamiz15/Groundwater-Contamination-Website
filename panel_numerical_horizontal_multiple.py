import logging
import sys
import math

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


def _horizontal_site_row(site):
    """Map one database site to a scenario row, the same resilient way the single
    page reads it (db_to_model): fill only the values the site carries, default
    the rest. Source thickness follows the single-page priority - the dedicated
    source thickness wins, falling back to plume width. Returns (row, ready,
    status)."""
    canonical = db_to_model(site, "numerical")
    issues = []
    source, issue = _num(canonical, "S_T", None)
    if source is None and issue is None:
        source, issue = _num(canonical, "S_w", 5.0)
    elif source is None:
        source = 5.0
    if issue:
        issues.append(issue)
    at, issue = _num(canonical, "alpha_Th", 0.2)
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
        "source_thickness": source,
        "grid_size": 1.0,
        "al": 1.0,
        "at": at,
        "gamma": gamma,
        "C_D": cd,
        "C_A": ca,
    }
    has_source = ("S_T" in canonical) or ("S_w" in canonical)
    if issues:
        status = "; ".join(issues)
        ready = False
    elif not has_source:
        status = "No source thickness - will use defaults"
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
ORIENTATION = "horizontal"
TITLE = "Numerical Horizontal Model"
JOB_KIND = "horizontal_single"
# First entries are the job payload keys; C_D/C_A are submitted as cd/ca.
SCENARIO_COLUMNS = ("source_thickness", "grid_size", "al", "at", "gamma", "C_D", "C_A")
COLUMN_TITLES = {
    "source_thickness": "Source Thickness T_s [m]",
    "grid_size": "Grid Size [m]",
    "al": "Longitudinal Dispersivity \u03b1_L [m]",
    "at": "Horizontal Transverse Dispersivity \u03b1_Th [m]",
    "gamma": "Stoichiometric Ratio \u03b3 [-]",
    "C_D": "Donor Concentration at Source C_D^0 [mg/L]",
    "C_A": "Acceptor Concentration at Source C_A^0 [mg/L]",
}
DEFAULT_ROW = {"source_thickness": 5.0, "grid_size": 1.0, "al": 1.0, "at": 0.2,
               "gamma": 3.5, "C_D": 5.0, "C_A": 8.0}
SITE_ROW = _horizontal_site_row


def selected_site_ids():
    """Site ids from ?compare_sites=1,2,3 - a shared link opens on its sites."""
    return _selected_site_ids()


def numerical_horizontal_multiple_app():
    return numerical_multiple_app(sys.modules[__name__])


def numerical_field_specs_horizontal():
    """What the page's Add-row dialog renders for this orientation."""
    return numerical_field_specs(sys.modules[__name__])
