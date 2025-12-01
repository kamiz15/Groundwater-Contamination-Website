# site_routes.py
"""
Routes for the site shell:
- dashboard / landing with the user's site database
- bar / hist / box plot pages
- optional JSON endpoints for dynamic plots

In this demo version we DO NOT use flask_login.
We just use a dummy email when querying the database.
"""

from flask import Blueprint, render_template, request, jsonify

from data_queries import get_user_sites
from plot_functions import create_bargraph, create_histogram, create_boxplot

site_bp = Blueprint("site_bp", __name__)

# ---- column config ----
COLUMN_DEFS = [
    ("ID", 0),
    ("Site unit", 1),
    ("Compound", 2),
    ("Aquifer thickness [m]", 3),
    ("Plume length [m]", 4),
    ("Plume width [m]", 5),
    ("Hydraulic conductivity [m/s]", 6),
    ("Electron donor [mg/L]", 7),
    ("Electron acceptor O₂ [mg/L]", 8),
    ("Electron acceptor NO₃ [mg/L]", 9),
]


def _get_column_names():
    return [label for (label, _) in COLUMN_DEFS]


def _get_column_index(label: str):
    for col_label, idx in COLUMN_DEFS:
        if col_label == label:
            return idx
    return None


def _demo_email() -> str:
    """Dummy email; change to something that exists in your `sites` table."""
    return "demo@example.com"


# -----------------------------
# MAIN TABLE VIEWS
# -----------------------------
@site_bp.route("/", methods=["GET"])
def index():
    table_data = get_user_sites(_demo_email())
    column_names = _get_column_names()
    return render_template(
        "site_database.html",
        table_data=table_data,
        column_names=column_names,
    )


@site_bp.route("/sites", methods=["GET"])
def site_database():
    """
    Explicit URL for the same view as index().
    Templates use url_for('site_bp.site_database').
    """
    table_data = get_user_sites(_demo_email())
    column_names = _get_column_names()
    return render_template(
        "site_database.html",
        table_data=table_data,
        column_names=column_names,
    )


# -----------------------------
# FULL-PAGE PLOTS (match template endpoints)
# -----------------------------

@site_bp.route("/plot_bar", methods=["GET"])
def plot_bar():
    """
    Endpoint used in base.html: url_for('site_bp.plot_bar')
    Renders a bar graph page.
    """
    table_data = get_user_sites(_demo_email())
    script, div = create_bargraph(table_data)
    return render_template(
        "plot_bar.html",   # we'll create this template if it doesn't exist
        plot_script=script,
        plot_div=div,
    )


@site_bp.route("/plot_hist", methods=["GET"])
def plot_hist():
    """
    Endpoint used in base.html: url_for('site_bp.plot_hist')
    Shows a histogram for a default parameter (Plume length [m]).
    """
    table_data = get_user_sites(_demo_email())
    parameter = "Plume length [m]"
    idx = _get_column_index(parameter)
    script, div = create_histogram("Gaussian", table_data, idx, parameter)
    return render_template(
        "plot_hist.html",
        plot_script=script,
        plot_div=div,
        parameter=parameter,
    )


@site_bp.route("/plot_box", methods=["GET"])
def plot_box():
    """
    Endpoint used in base.html: url_for('site_bp.plot_box')
    Shows a boxplot for a default parameter (Plume length [m]).
    """
    table_data = get_user_sites(_demo_email())
    parameter = "Plume length [m]"
    idx = _get_column_index(parameter)
    script, div = create_boxplot(parameter, table_data, idx)
    return render_template(
        "plot_box.html",
        plot_script=script,
        plot_div=div,
        parameter=parameter,
    )


# -----------------------------
# OPTIONAL JSON ENDPOINTS (keep if you want AJAX later)
# -----------------------------
@site_bp.route("/plots/histogram", methods=["POST"])
def histogram_json():
    if request.is_json:
        data = request.get_json()
        feature = data.get("feature", "Gaussian")
        parameter = data.get("parameter")
    else:
        feature = request.form.get("feature", "Gaussian")
        parameter = request.form.get("parameter")

    if not parameter:
        return jsonify({"error": "No parameter provided"}), 400

    col_index = _get_column_index(parameter)
    if col_index is None:
        return jsonify({"error": f"Unknown parameter '{parameter}'"}), 400

    table_data = get_user_sites(_demo_email())
    script, div = create_histogram(feature, table_data, col_index, parameter)

    return jsonify(
        {
            "plot_script": script,
            "plot_div": div,
            "parameter": parameter,
            "feature": feature,
        }
    )


@site_bp.route("/plots/boxplot", methods=["POST"])
def boxplot_json():
    if request.is_json:
        data = request.get_json()
        parameter = data.get("parameter")
    else:
        parameter = request.form.get("parameter")

    if not parameter:
        return jsonify({"error": "No parameter provided"}), 400

    col_index = _get_column_index(parameter)
    if col_index is None:
        return jsonify({"error": f"Unknown parameter '{parameter}'"}), 400

    table_data = get_user_sites(_demo_email())
    script, div = create_boxplot(parameter, table_data, col_index)

    return jsonify(
        {
            "plot_script": script,
            "plot_div": div,
            "parameter": parameter,
        }
    )
