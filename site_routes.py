# site_routes.py

import csv
import io
import logging
import re
from urllib.parse import urlencode

from flask import Blueprint, Response, abort, redirect, render_template, request, jsonify, url_for
from flask_login import current_user, login_required

from data_queries import (
    delete_site,
    delete_user_sites,
    get_user_sites,
    get_user_sites_rows,
    insert_site,
    insert_sites_bulk,
    NUMERIC_SITE_FIELDS,
    SITE_FIELDS,
    TEXT_SITE_FIELDS,
)
from numerical_jobs import job_status, load_job_meta
from pdf_report import CASTReport
from plot_functions import create_bargraph, create_histogram, create_boxplot
from security import csrf_protect, form_data_or_400, json_object_or_400, rate_limit
from settings import PANEL_PUBLIC_BASE
from symbol_registry import (
    SITE_COLUMN_DEFS,
    TEXT_COLUMN_DEFS,
    header_match,
    header_to_site_column,
    ui_label_markup,
)

site_bp = Blueprint("site_bp", __name__)
logger = logging.getLogger(__name__)

# ---- column config ----
# COLUMN_DEFS maps the legacy 9-column plot labels to their index in the
# list-of-lists returned by get_user_sites (used by the standalone plot pages,
# which keep the original fixed layout). The input table itself is rendered
# dynamically from the catalog (ALL_FIELD_DEFS / visible columns).
COLUMN_DEFS = [
    ("ID", 0),
    ("Site unit", 1),
    ("Compound", 2),
    ("Aquifer Thickness T_A [m]", 3),
    ("Plume Length L_p [m]", 4),
    ("Plume Width W_p [m]", 5),
    ("Hydraulic Conductivity K [m/s]", 6),
    ("Donor Concentration C_D [mg/L]", 7),
    ("Acceptor Concentration C_A (O\u2082) [mg/L]", 8),
    ("Acceptor Concentration C_A (NO\u2083) [mg/L]", 9),
]

# Full ordered (field, label) list for the input table, derived from the
# catalog: identity columns first, then every typed model-parameter column in
# registry order. Filtering/sorting validate against this; display narrows it
# to columns that actually hold data (see _visible_field_defs).
ALL_FIELD_DEFS = (
    [("id", "ID")]
    + [(col, TEXT_COLUMN_DEFS[col]["ui"]) for col in TEXT_SITE_FIELDS]
    + [(db, ui) for db, ui, _unit in SITE_COLUMN_DEFS]
)
_ALL_FIELD_KEYS = {field for field, _label in ALL_FIELD_DEFS}
# Identity columns are always shown even when empty so every row is identifiable.
_ALWAYS_SHOWN = {"id", *TEXT_SITE_FIELDS}

_MANUAL_SITE_FIELDS = {
    "aquifer_thickness",
    "plume_length",
    "plume_width",
    "hydraulic_conductivity",
    "electron_donor",
    "electron_acceptor_o2",
    "electron_acceptor_no3",
}
MANUAL_FIELD_DEFS = [
    (field, label, ui_label_markup(label))
    for field, label, _unit in SITE_COLUMN_DEFS
    if field in _MANUAL_SITE_FIELDS
]
UPLOAD_FIELD_DEFS = [
    (TEXT_COLUMN_DEFS[field]["ui"], TEXT_COLUMN_DEFS[field]["ui"])
    for field in TEXT_SITE_FIELDS
] + [
    (label, ui_label_markup(label)) for _field, label, _unit in SITE_COLUMN_DEFS
]


def _visible_field_defs(rows):
    """Columns to render: identity columns + any column with data in some row."""
    present = set()
    for row in rows:
        for field in _ALL_FIELD_KEYS:
            value = row.get(field)
            if value is not None and value != "":
                present.add(field)
    return [
        (field, label)
        for field, label in ALL_FIELD_DEFS
        if field in _ALWAYS_SHOWN or field in present
    ]


def _get_column_index(label: str):
    for col_label, idx in COLUMN_DEFS:
        if col_label == label:
            return idx
    return None


def _current_email():
    return current_user.email


def _build_field_to_header_map(fieldnames):
    """Map sites columns to the original CSV header that fills them.

    Every header is matched against the catalog (symbol_registry), so any
    recognized model-parameter column — not just the original 9 — is captured.
    Returns { sites_column: original_header }.

    Collisions (two headers mapping to one column) are resolved by precedence:
    a canonical match wins over a soft alias. This keeps "Site Unit" (the name)
    in site_unit even when "Site No." (a row index) appears earlier.
    """
    mapping = {}
    strong = {}
    for header in fieldnames:
        if not header or not header.strip():
            continue
        column, is_strong = header_match(header)
        if not column:
            continue
        if column not in mapping or (is_strong and not strong.get(column)):
            mapping[column] = header
            strong[column] = is_strong
    return mapping


# Detects a power-of-ten scale declared in a header unit, e.g. "10-3", "10^-3"
# or "1e-3" inside "Hydraulic conductivity[10-3 [m/s]]".
_SCALE_RE = re.compile(r"10\s*\^?\s*(-?\d+)|1[eE]\s*(-?\d+)")


def _header_scale(header: str) -> float:
    """Return the power-of-ten factor declared in a header, or 1.0 if none."""
    if not header:
        return 1.0
    match = _SCALE_RE.search(header)
    if not match:
        return 1.0
    exponent = match.group(1) if match.group(1) is not None else match.group(2)
    try:
        return 10.0 ** int(exponent)
    except (ValueError, OverflowError):
        return 1.0


_CSV_DELIMITERS = [",", ";", "\t", "|"]


def _detect_delimiter(text: str) -> str:
    """Pick the delimiter used by the CSV header line.

    Many exported datasets are semicolon- or tab-separated (common in European
    locales and simulation tools). Choosing the candidate that appears most in
    the header row handles those without assuming a comma.
    """
    header_line = ""
    for line in text.splitlines():
        if line.strip():
            header_line = line
            break
    counts = {d: header_line.count(d) for d in _CSV_DELIMITERS}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def _extra_field_keys(rows):
    """First-seen-ordered union of extra_data keys across the given rows.

    These are the uploaded columns that did not match a catalog parameter; each
    becomes its own table column so the whole file is visible and readable.
    """
    keys = []
    seen = set()
    for row in rows:
        extra = row.get("extra_data") or {}
        if isinstance(extra, dict):
            for key in extra.keys():
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
    return keys


def _site_filters_from_request():
    filters = {}
    for field, _label in ALL_FIELD_DEFS:
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
    if sort_field not in _ALL_FIELD_KEYS:
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
@rate_limit(limit=10, window_seconds=60, methods={"POST"})
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
                reader = csv.DictReader(io.StringIO(text), delimiter=_detect_delimiter(text))
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
                # Per-column unit scale (e.g. K header "[10-3 [m/s]]" -> 1e-3),
                # applied only to numeric columns so values are stored in base
                # units the models expect.
                numeric_columns = set(NUMERIC_SITE_FIELDS)
                column_scales = {
                    column: _header_scale(header)
                    for column, header in header_map.items()
                    if column in numeric_columns and _header_scale(header) != 1.0
                }

                payloads = []
                row_number = 0
                for row in reader:
                    if not row:
                        continue
                    row_number += 1
                    payload = {}
                    for field in header_map:
                        raw = (row.get(header_map[field], "") or "").strip()
                        scale = column_scales.get(field)
                        if scale and raw:
                            try:
                                raw = repr(float(raw) * scale)
                            except ValueError:
                                pass  # non-numeric (e.g. "NA"); leave untouched
                        payload[field] = raw
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

                inserted, skipped = insert_sites_bulk(email, payloads)
                if inserted and skipped:
                    message = (
                        f"Uploaded {inserted} site row(s); "
                        f"skipped {skipped} duplicate row(s) already in your database."
                    )
                elif inserted:
                    message = f"Uploaded {inserted} site row(s) successfully."
                else:
                    message = (
                        f"No new rows added: all {skipped} row(s) are already in "
                        "your database."
                    )

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
    for display_id, site in enumerate(sites, start=1):
        site["display_id"] = display_id
    # Columns are formed from the data: every catalog column that any uploaded
    # row populates is shown (identity columns always), so different models'
    # uploads surface their own parameters.
    table_field_defs = _visible_field_defs(sites)
    table_field_markup = {
        label: ui_label_markup(label) for _field, label in table_field_defs
    }
    # Unrecognized uploaded columns each become their own column too, so the
    # whole file is shown (not collapsed into one "Additional fields" cell).
    extra_field_keys = _extra_field_keys(sites)
    active_filters = _site_filters_from_request()
    sort_field, sort_dir = _site_sort_from_request()
    filtered_sites = _filter_sites(sites, active_filters)
    filtered_sites = _sort_sites(filtered_sites, sort_field, sort_dir)
    return render_template(
        "site_database.html",
        sites=filtered_sites,
        table_field_defs=table_field_defs,
        table_field_markup=table_field_markup,
        manual_field_defs=MANUAL_FIELD_DEFS,
        upload_field_defs=UPLOAD_FIELD_DEFS,
        extra_field_keys=extra_field_keys,
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


@site_bp.route("/sites/clear", methods=["POST"])
@login_required
@csrf_protect
def clear_site_database():
    delete_user_sites(_current_email())
    return redirect(url_for("site_bp.site_database"))


@site_bp.route("/data_analysis", methods=["GET"])
@login_required
def data_analysis_workbench():
    panel_src = f"{PANEL_PUBLIC_BASE}/panel_data_analysis"
    job_id = (request.args.get("aem_job") or "").strip()
    if job_id:
        meta = load_job_meta(job_id)
        status = job_status(job_id) if meta else None
        if (
            meta is None
            or meta.get("email") != _current_email()
            or meta.get("kind") not in {"aem_forward", "aem_inverse"}
            or status is None
            or status.get("status") != "done"
        ):
            abort(404, description="Unknown AEM job.")
        panel_src = f"{panel_src}?{urlencode({'aem_job': job_id})}"
    return render_template("panel_data_analysis.html", panel_src=panel_src)


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
    Shows a histogram for a default parameter (Plume Length L_p [m]).
    """
    table_data = get_user_sites(_current_email())
    parameter = "Plume Length L_p [m]"
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
    Shows a boxplot for a default parameter (Plume Length L_p [m]).
    """
    table_data = get_user_sites(_current_email())
    parameter = "Plume Length L_p [m]"
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
@rate_limit(limit=10, window_seconds=60)
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
