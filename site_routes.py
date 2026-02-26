# site_routes.py

import csv
import io

from flask import Blueprint, render_template, request, jsonify, session

from data_queries import get_user_sites, get_user_sites_rows, insert_site, insert_sites_bulk, SITE_FIELDS
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


def _current_email():
    return session.get("email") or _demo_email()


def _normalize_header(name: str) -> str:
    return "".join(ch.lower() for ch in (name or "") if ch.isalnum())


HEADER_ALIASES = {
    "site_unit": [
        "site_unit",
        "site unit",
        "siteno",
        "site no.",
    ],
    "compound": [
        "compound",
    ],
    "aquifer_thickness": [
        "aquifer_thickness",
        "aquifer thickness",
        "aquifer thickness[m]",
    ],
    "plume_length": [
        "plume_length",
        "plume length",
        "plume length[m]",
    ],
    "plume_width": [
        "plume_width",
        "plume width",
        "plume width[m]",
    ],
    "hydraulic_conductivity": [
        "hydraulic_conductivity",
        "hydraulic conductivity",
        "hydraulic conductivity[m/s]",
        "hydraulic conductivity[10-3 [m/s]]",
    ],
    "electron_donor": [
        "electron_donor",
        "electron donor",
        "electron donor[mg/l]",
    ],
    "electron_acceptor_o2": [
        "electron_acceptor_o2",
        "electron acceptor o2",
        "electron acceptors : o2[mg/l]",
        "o2[mg/l]",
    ],
    "electron_acceptor_no3": [
        "electron_acceptor_no3",
        "electron acceptor no3",
        "no3[mg/l]",
    ],
}

NORMALIZED_ALIAS_LOOKUP = {
    field: {_normalize_header(alias) for alias in aliases}
    for field, aliases in HEADER_ALIASES.items()
}


def _build_field_to_header_map(fieldnames):
    normalized_headers = {
        _normalize_header(h): h for h in fieldnames if h and h.strip()
    }
    mapping = {}
    for field in SITE_FIELDS:
        wanted = NORMALIZED_ALIAS_LOOKUP[field]
        for normalized_name, original_name in normalized_headers.items():
            if normalized_name in wanted:
                mapping[field] = original_name
                break
    return mapping


# -----------------------------
# MAIN TABLE VIEWS
# -----------------------------

"""""
@site_bp.route("/", methods=["GET"])
def index():
    table_data = get_user_sites(_demo_email())
    column_names = _get_column_names()
    return render_template(
        "site_database.html",
        table_data=table_data,
        column_names=column_names,
    )
"""

@site_bp.route("/sites", methods=["GET", "POST"])
def site_database():
    """
    Explicit URL for the same view as index().
    Templates use url_for('site_bp.site_database').
    """
    email = _current_email()
    message = None
    error = None

    if request.method == "POST":
        action = request.form.get("action", "").strip().lower()
        try:
            if action == "manual":
                if not session.get("email"):
                    raise ValueError("Please log in before adding site data.")
                payload = {field: request.form.get(field) for field in SITE_FIELDS}
                if not payload.get("site_unit") or not payload.get("compound"):
                    raise ValueError("Site Unit and Compound are required.")
                insert_site(email, payload)
                message = "Site added successfully."

            elif action == "upload_csv":
                if not session.get("email"):
                    raise ValueError("Please log in before uploading CSV data.")
                file = request.files.get("csv_file")
                if not file or not file.filename:
                    raise ValueError("Please choose a CSV file before uploading.")

                text = file.stream.read().decode("utf-8-sig")
                reader = csv.DictReader(io.StringIO(text))
                if not reader.fieldnames:
                    raise ValueError("CSV appears empty or missing a header row.")

                header_map = _build_field_to_header_map(reader.fieldnames)
                missing = [field for field in SITE_FIELDS if field not in header_map]
                if missing:
                    raise ValueError(f"Missing required CSV columns: {', '.join(missing)}")

                payloads = []
                for row in reader:
                    if not row:
                        continue
                    payload = {
                        field: (row.get(header_map[field], "") or "").strip()
                        for field in SITE_FIELDS
                    }
                    if not payload["site_unit"] and not payload["compound"]:
                        continue
                    if not payload["site_unit"] or not payload["compound"]:
                        raise ValueError("Each row must include site_unit and compound.")
                    payloads.append(payload)

                if not payloads:
                    raise ValueError("No valid data rows found in CSV.")

                inserted = insert_sites_bulk(email, payloads)
                message = f"Uploaded {inserted} site row(s) successfully."

            else:
                raise ValueError("Unsupported form action.")
        except Exception as exc:
            error = str(exc)

    table_data = get_user_sites(email)
    sites = get_user_sites_rows(email)
    column_names = _get_column_names()
    return render_template(
        "site_database.html",
        table_data=table_data,
        sites=sites,
        column_names=column_names,
        message=message,
        error=error,
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
    table_data = get_user_sites(_current_email())
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
    table_data = get_user_sites(_current_email())
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
    table_data = get_user_sites(_current_email())
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

    table_data = get_user_sites(_current_email())
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

    table_data = get_user_sites(_current_email())
    script, div = create_boxplot(parameter, table_data, col_index)

    return jsonify(
        {
            "plot_script": script,
            "plot_div": div,
            "parameter": parameter,
        }
    )
