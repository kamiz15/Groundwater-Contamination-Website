# site_routes.py

import csv
import io
import logging

from flask import Blueprint, Response, abort, redirect, render_template, request, jsonify, url_for
from flask_login import current_user, login_required

from data_queries import delete_site, get_user_sites, get_user_sites_rows, insert_site, insert_sites_bulk, SITE_FIELDS
from pdf_report import CASTReport
from plot_functions import create_bargraph, create_histogram, create_boxplot
from security import csrf_protect, form_data_or_400, json_object_or_400

site_bp = Blueprint("site_bp", __name__)
logger = logging.getLogger(__name__)

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

TABLE_FIELD_DEFS = [
    ("id", "ID"),
    ("site_unit", "Site unit"),
    ("compound", "Compound"),
    ("aquifer_thickness", "Aquifer thickness [m]"),
    ("plume_length", "Plume length [m]"),
    ("plume_width", "Plume width [m]"),
    ("hydraulic_conductivity", "Hydraulic conductivity [m/s]"),
    ("electron_donor", "Electron donor [mg/L]"),
    ("electron_acceptor_o2", "Electron acceptor O2 [mg/L]"),
    ("electron_acceptor_no3", "Electron acceptor NO3 [mg/L]"),
]


def _get_column_index(label: str):
    for col_label, idx in COLUMN_DEFS:
        if col_label == label:
            return idx
    return None


def _current_email():
    return current_user.email


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


def _site_filters_from_request():
    filters = {}
    for field, _label in TABLE_FIELD_DEFS:
        value = (request.args.get(field) or "").strip()
        if value:
            filters[field] = value
    return filters


def _filter_sites(rows, filters):
    if not filters:
        return rows

    filtered = []
    for row in rows:
        include = True
        for field, needle in filters.items():
            value = row.get(field, "")
            haystack = "" if value is None else str(value)
            if needle.lower() not in haystack.lower():
                include = False
                break
        if include:
            filtered.append(row)
    return filtered


def _site_sort_from_request():
    sort_field = (request.args.get("sort_by") or "").strip()
    sort_dir = (request.args.get("sort_dir") or "asc").strip().lower()
    valid_fields = {field for field, _label in TABLE_FIELD_DEFS}
    if sort_field not in valid_fields:
        return "", "asc"
    if sort_dir not in {"asc", "desc"}:
        sort_dir = "asc"
    return sort_field, sort_dir


def _sort_sites(rows, sort_field, sort_dir):
    if not sort_field:
        return rows

    reverse = sort_dir == "desc"

    def _sort_key(row):
        value = row.get(sort_field)
        if value is None or value == "":
            return (1, "")
        try:
            return (0, float(value))
        except (TypeError, ValueError):
            return (0, str(value).lower())

    return sorted(rows, key=_sort_key, reverse=reverse)


# -----------------------------
# MAIN TABLE VIEWS
# -----------------------------

@site_bp.route("/sites", methods=["GET", "POST"])
@login_required
@csrf_protect
def site_database():
    """
    Explicit URL for the same view as index().
    Templates use url_for('site_bp.site_database').
    """
    email = _current_email()
    message = None
    error = None

    if request.method == "POST":
        form = form_data_or_400()
        action = form.get("action", "").strip().lower()
        try:
            if action == "manual":
                payload = {field: form.get(field) for field in SITE_FIELDS}
                if not payload.get("site_unit") or not payload.get("compound"):
                    raise ValueError("Site Unit and Compound are required.")
                insert_site(email, payload)
                message = "Site added successfully."

            elif action == "upload_csv":
                file = request.files.get("csv_file")
                if not file or not file.filename:
                    raise ValueError("Please choose a CSV file before uploading.")

                try:
                    text = file.stream.read().decode("utf-8-sig")
                except UnicodeDecodeError:
                    raise ValueError("The file is not UTF-8 text. Please upload a plain CSV file.")
                reader = csv.DictReader(io.StringIO(text))
                if not reader.fieldnames:
                    raise ValueError("CSV appears empty or missing a header row.")

                # Flexible CSV: map any recognized headers to fixed DB columns
                # (as before), but do NOT reject CSVs lacking the 9 fixed
                # columns. Every header that does not map to a fixed field is
                # routed into payload["extra_data"], keyed by its trimmed
                # original name, so model pages can autofill from it later.
                header_map = _build_field_to_header_map(reader.fieldnames)
                mapped_originals = set(header_map.values())
                extra_headers = [
                    h
                    for h in reader.fieldnames
                    if h and h.strip() and h not in mapped_originals
                ]

                payloads = []
                row_number = 0
                for row in reader:
                    if not row:
                        continue
                    row_number += 1
                    payload = {
                        field: (row.get(header_map[field], "") or "").strip()
                        for field in header_map
                    }
                    # Unmapped columns -> extra_data, dropping empty values.
                    extra = {}
                    for h in extra_headers:
                        value = (row.get(h, "") or "").strip()
                        if value:
                            extra[h.strip()] = value
                    payload["extra_data"] = extra

                    site_unit = payload.get("site_unit", "")
                    compound = payload.get("compound", "")
                    # Synthesis rule: only skip a row that carries no identifying
                    # value at all (no site_unit, no compound, no extra data).
                    # Otherwise, if site_unit is blank, synthesize one from the
                    # 1-based row position so the row is still importable;
                    # a blank compound is left as "".
                    if not site_unit and not compound and not extra:
                        continue
                    if not site_unit:
                        payload["site_unit"] = f"Imported row {row_number}"
                    payloads.append(payload)

                if not payloads:
                    raise ValueError("No valid data rows found in CSV.")

                inserted = insert_sites_bulk(email, payloads)
                message = f"Uploaded {inserted} site row(s) successfully."

            else:
                raise ValueError("Unsupported form action.")
        except ValueError as exc:
            error = str(exc)
        except Exception:
            logger.exception("Database error while updating site data")
            error = "Unable to save site data. Please try again later."

    # Single query: the template renders from `sites`; the old second query
    # (get_user_sites -> table_data) produced a variable the template never used.
    sites = get_user_sites_rows(email)
    active_filters = _site_filters_from_request()
    sort_field, sort_dir = _site_sort_from_request()
    filtered_sites = _filter_sites(sites, active_filters)
    filtered_sites = _sort_sites(filtered_sites, sort_field, sort_dir)
    return render_template(
        "site_database.html",
        sites=filtered_sites,
        table_field_defs=TABLE_FIELD_DEFS,
        active_filters=active_filters,
        sort_field=sort_field,
        sort_dir=sort_dir,
        total_site_count=len(sites),
        message=message,
        error=error,
    )


@site_bp.route("/sites/<int:site_id>/delete", methods=["POST"])
@login_required
@csrf_protect
def delete_site_row(site_id):
    try:
        deleted = delete_site(_current_email(), site_id)
    except Exception:
        logger.exception("Database error while deleting site row")
        deleted = False
    if not deleted:
        abort(404, description="Site not found.")
    return redirect(url_for("site_bp.site_database"))


# -----------------------------
# FULL-PAGE PLOTS (match template endpoints)
# -----------------------------

@site_bp.route("/plot_bar", methods=["GET"])
@login_required
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
@login_required
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
@login_required
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
@login_required
@csrf_protect
def histogram_json():
    if request.is_json:
        data = json_object_or_400()
        feature = data.get("feature", "Gaussian")
        parameter = data.get("parameter")
    else:
        form = form_data_or_400()
        feature = form.get("feature", "Gaussian")
        parameter = form.get("parameter")

    if not parameter:
        return jsonify({"success": False, "message": "No parameter provided"}), 400

    col_index = _get_column_index(parameter)
    if col_index is None:
        return jsonify({"success": False, "message": f"Unknown parameter '{parameter}'"}), 400

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
@login_required
@csrf_protect
def boxplot_json():
    if request.is_json:
        data = json_object_or_400()
        parameter = data.get("parameter")
    else:
        form = form_data_or_400()
        parameter = form.get("parameter")

    if not parameter:
        return jsonify({"success": False, "message": "No parameter provided"}), 400

    col_index = _get_column_index(parameter)
    if col_index is None:
        return jsonify({"success": False, "message": f"Unknown parameter '{parameter}'"}), 400

    table_data = get_user_sites(_current_email())
    script, div = create_boxplot(parameter, table_data, col_index)

    return jsonify(
        {
            "plot_script": script,
            "plot_div": div,
            "parameter": parameter,
        }
    )


# ---- Generic report export (used by Multiple-simulation pages) ----
# The Panel app posts its latest run results to the parent page via
# postMessage; the page sends them here to build the branded PDF.
@site_bp.route("/report/export", methods=["POST"])
@login_required
@csrf_protect
def report_export():
    data = json_object_or_400()

    title = str(data.get("title") or "CAST Report")[:120]
    subtitle = str(data.get("subtitle") or "CAST Model")[:120]
    filename = str(data.get("filename") or "cast_report.pdf")[:80]
    filename = "".join(c for c in filename if c.isalnum() or c in "._-") or "cast_report.pdf"
    if not filename.endswith(".pdf"):
        filename += ".pdf"

    parameters = data.get("parameters") or []
    outputs = data.get("outputs") or []
    plot_data = data.get("plot_data")
    if not isinstance(parameters, list) or not isinstance(outputs, list):
        abort(400, description="parameters and outputs must be lists.")
    if len(parameters) > 300 or len(outputs) > 100:
        abort(400, description="Report payload too large.")
    if plot_data is not None and not isinstance(plot_data, dict):
        plot_data = None

    plot_images = None
    raw_images = data.get("plot_images")
    if isinstance(raw_images, list) and raw_images:
        import base64

        MAX_PLOT_IMAGE_BYTES = 5 * 1024 * 1024
        PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
        plot_images = []
        for item in raw_images[:20]:
            if not isinstance(item, dict) or not item.get("b64"):
                continue
            try:
                png_bytes = base64.b64decode(item["b64"])
            except Exception:
                continue
            # Cap each image and require a real PNG header before handing the
            # bytes to the PDF renderer (PIL), to bound memory use.
            if len(png_bytes) > MAX_PLOT_IMAGE_BYTES or not png_bytes.startswith(PNG_SIGNATURE):
                continue
            try:
                max_height_mm = float(item.get("max_height_mm", 105))
            except (TypeError, ValueError):
                max_height_mm = 105.0
            plot_images.append({
                "title": str(item.get("title") or "Plot")[:200],
                "bytes": png_bytes,
                "caption": str(item.get("caption") or "")[:400],
                "max_height_mm": max_height_mm,
            })
        plot_images = plot_images or None

    try:
        report = CASTReport(title, subtitle)
        pdf_bytes = report.generate(parameters, outputs, plot_data, plot_images=plot_images)
    except Exception:
        logger.exception("Report export failed")
        abort(400, description="Could not generate the report from the supplied data.")

    return Response(
        pdf_bytes,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
