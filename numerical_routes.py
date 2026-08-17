import logging
from urllib.parse import urlencode

from flask import Blueprint, Response, jsonify, redirect, render_template, request, url_for

from data_queries import get_user_sites_rows
from numerical_jobs import (
    cancel_job,
    fetch_result,
    job_status,
    load_job_meta,
    queue_counts,
    save_job_meta,
    submit_job,
)
from security import csrf_protect, current_email, rate_limit
from route_guards import compare_site_ids, guard_model_errors, request_finite_float
from numerical_input_validation import format_issues, vertical_inputs_from_site
from param_meta import GRID_SIZE_VERTICAL_SYMBOL, attach_meta
from pdf_report import CASTReport
from settings import NUMERICAL_MULTIPLE_MAX_RUNS, PANEL_PUBLIC_BASE
from symbol_registry import db_hydraulic_conductivity_to_numerical_hk, db_to_model

numerical_bp = Blueprint("numerical_bp", __name__)
logger = logging.getLogger(__name__)

NUMERICAL_INPUT_SPECS = {
    "horizontal": [
        ("source_thickness", "Source Width [m]", 5.0, "0.1", "0.000001"),
        ("grid_size", "Grid Spacing [m]", 1.0, "0.1", "0.000001"),
        ("al", "Longitudinal Dispersivity [m]", 1.0, "0.1", "0.000001"),
        ("at", "Horizontal Transverse Dispersivity [m]", 0.2, "0.01", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 3.5, "0.1", None),
        ("C_D", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
        ("C_A", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("prsity", "Porosity [-]", 0.3, "0.01", "0.000001"),
        ("hk", "Hydraulic Conductivity [m/d]", 8.64, "0.1", "0.000001"),
        ("gradient", "Hydraulic Gradient [-]", 0.0125, "0.001", "0.000001"),
    ],
    "vertical": [
        ("Lz", "Aquifer Thickness [m]", 10.0, "0.1", "0.000001"),
        ("grid_size", "Grid Spacing [m]", 1.0, "0.1", "0.000001"),
        ("al", "Longitudinal Dispersivity [m]", 1.0, "0.1", "0.000001"),
        ("atv", "Vertical Transverse Dispersivity [m]", 0.1, "0.01", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 3.5, "0.1", None),
        ("C_D", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
        ("C_A", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("prsity", "Porosity [-]", 0.3, "0.01", "0.000001"),
        ("hk", "Hydraulic Conductivity [m/d]", 8.64, "0.1", "0.000001"),
        ("gradient", "Hydraulic Gradient [-]", 0.0125, "0.001", "0.000001"),
    ],
}

NUMERICAL_ADVANCED_INPUT_SPECS = {
    "horizontal": [],
    "vertical": [],
}

# Which semantic group each numerical input belongs to. The form renders these
# as four grouped cards (chemical / physical / standard / numerical) in two columns.
#   chemical  — reaction stoichiometry + donor/acceptor concentrations
#   physical  — source/aquifer geometry + dispersivity
#   standard  — flow / hydraulic properties (porosity, K, gradient)
#   numerical — grid discretisation (not a physical property)
NUMERICAL_FIELD_COLUMN = {
    "gamma": "chemical", "C_D": "chemical", "C_A": "chemical",
    "source_thickness": "physical", "Lz": "physical",
    "al": "physical", "at": "physical", "atv": "physical",
    "prsity": "standard", "hk": "standard", "gradient": "standard",
    "grid_size": "numerical",
}


def _numerical_analytical_fields(orientation, input_fields):
    """Compute the read-only Analytical column (domain length/width) from the current
    input values, server-side, so the 3-column form can show them before a run."""
    vals = {fld["name"]: fld["value"] for fld in input_fields}
    try:
        if orientation == "horizontal":
            from analytical_models import cirpka_2005
            sw = float(vals["source_thickness"])
            lmax = cirpka_2005(Sw=sw, Ath=float(vals["at"]), Ca=float(vals["C_A"]),
                               Cd=float(vals["C_D"]), Ga=float(vals["gamma"]))
            return [
                {"label": "Domain Length L_D [m]", "value": 1.5 * lmax},
                {"label": "Domain Width W_D [m]", "value": 10.0 * sw},
            ]
        import numpy as _np
        lz = float(vals["Lz"])
        lmax = 1.5 * (4.0 * lz ** 2) / (_np.pi ** 2 * float(vals["atv"])) * _np.log(
            (4.0 * float(vals["gamma"]) * float(vals["C_D"]) + float(vals["C_A"]))
            / (_np.pi * float(vals["C_A"])))
        # Aquifer thickness Lz is already shown in the editable Input column, so
        # only surface the derived Domain Length here (avoid the duplicate Lz).
        return [
            {"label": "Domain Length L_D [m]", "value": float(lmax)},
        ]
    except Exception:
        return []



def _current_email():
    return current_email()


def _panel_base_url():
    return PANEL_PUBLIC_BASE


def _default_query(orientation):
    return {
        name: default
        for name, _label, default, _step, _minimum in (
            NUMERICAL_INPUT_SPECS.get(orientation, [])
            + NUMERICAL_ADVANCED_INPUT_SPECS.get(orientation, [])
        )
        if default is not None
    }


_request_float = request_finite_float


def _input_fields(orientation, site):
    try:
        db_query = _build_panel_query(site, orientation=orientation)
    except ValueError:
        db_query = {}
    fields = []
    for name, label, default, step, minimum in NUMERICAL_INPUT_SPECS.get(orientation, []):
        field = attach_meta({
            "name": name,
            "label": label,
            "value": _request_float(name, db_query.get(name, default)),
            "step": step,
            "min": minimum,
            "from_db": name in db_query,
            "advanced": False,
            "column": NUMERICAL_FIELD_COLUMN.get(name, "physical"),
        })
        if name == "grid_size" and orientation == "vertical":
            field["symbol"] = GRID_SIZE_VERTICAL_SYMBOL
        fields.append(field)
    for name, label, default, step, minimum in NUMERICAL_ADVANCED_INPUT_SPECS.get(orientation, []):
        fields.append(attach_meta({
            "name": name,
            "label": label,
            "value": _request_float(name, default),
            "step": step,
            "min": minimum,
            "from_db": False,
            "advanced": True,
        }))
    return fields


def _export_href(input_fields):
    query = {f["name"]: f["value"] for f in input_fields if f["value"] is not None}
    return f"{request.path}/export?{urlencode(query)}"


def _selected_site(orientation=None):
    sites = get_user_sites_rows(_current_email())
    invalid_message = None
    invalid_sites = {}
    if not sites:
        selected_id = request.args.get("site_id", type=int)
        if selected_id is not None and selected_id in invalid_sites:
            invalid_message = f"This site can't be modelled: {format_issues(invalid_sites[selected_id])}"
        return sites, None, invalid_message
    selected_id = request.args.get("site_id", type=int)
    if selected_id is None:
        return sites, None, None
    if selected_id in invalid_sites:
        invalid_message = f"This site can't be modelled: {format_issues(invalid_sites[selected_id])}"
        return sites, None, invalid_message
    for site in sites:
        if site.get("id") == selected_id:
            return sites, site, None
    return sites, None, None


def _build_panel_query(site, orientation=None):
    """Build the autofill query for a selected site.

    The database fills only the inputs it actually carries; every other field
    keeps its default (or is supplied by the user / analytical calculation).
    Autofill is resilient per-field: a missing or out-of-range value (e.g. a
    hydraulic conductivity outside the solver band) is simply skipped, never
    discarding the values the site does provide. Validation of a complete input
    set still happens at run/submit time.
    """
    if not site:
        return {}

    query = {"email": _current_email()}
    if orientation:
        query["orientation"] = orientation
    if site.get("id") is not None:
        query["site_id"] = int(site.get("id"))

    canonical = db_to_model(site, "numerical")
    for symbol, value in canonical.items():
        if symbol == "M":
            # Aquifer thickness -> vertical aquifer thickness Lz.
            query["M"] = value
            query["Lz"] = value
        elif symbol == "S_T":
            # Dedicated source thickness wins the source_thickness field.
            query["source_thickness"] = value
            query["source"] = value
        elif symbol == "S_w":
            query["S_w"] = value
            query["Sw"] = value
            query.setdefault("source", value)
            query.setdefault("source_thickness", value)
        elif symbol == "K":
            try:
                numerical_hk = db_hydraulic_conductivity_to_numerical_hk(value)
            except ValueError:
                continue  # out of solver band -> leave hk default, keep the rest
            query["K"] = numerical_hk
            query["hk"] = numerical_hk
        elif symbol == "K_v":
            query["vk"] = value
            query["K_v"] = value
        elif symbol == "C_D":
            query["C_D"] = value
            query["Cd"] = value
            query["C_ED0"] = value
            query["c0"] = value
        elif symbol == "C_A":
            query["C_A"] = value
            query["Ca"] = value
            query["C_EA0"] = value
        elif symbol == "gamma":
            query["gamma"] = value
        elif symbol == "alpha_Th":
            # Horizontal transverse dispersivity: form field is named "at".
            query["at"] = value
            query["alpha_Th"] = value
        elif symbol == "alpha_Tv":
            # Vertical transverse dispersivity: form field is named "atv".
            query["atv"] = value
            query["alpha_Tv"] = value
        else:
            query[symbol] = value
    for field, value in _numerical_extra_data_fields(site, orientation).items():
        query.setdefault(field, value)
    return query


def _normalise_numerical_extra_key(value):
    return "".join(ch.lower() for ch in (value or "") if ch.isalnum())


def _numerical_extra_data_fields(site, orientation=None):
    extra = site.get("extra_data") or {}
    if not isinstance(extra, dict):
        return {}

    aliases = {
        "grid_size": {"gridsize", "dx", "dxdy", "dxdz", "cellsize"},
        "al": {"al", "alphal", "longitudinaldispersivity", "longitudinaldispersivityal"},
    }
    if orientation == "vertical":
        aliases["Lz"] = {"lz", "aquiferthicknesslz", "domainthicknesslz"}
    elif orientation == "horizontal":
        aliases["at"] = {"at", "alphat", "transversedispersivity", "transversedispersivityat"}

    by_alias = {
        alias: field
        for field, field_aliases in aliases.items()
        for alias in field_aliases
    }
    fields = {}
    for header, raw_value in extra.items():
        field = by_alias.get(_normalise_numerical_extra_key(header))
        if not field or field in fields:
            continue
        try:
            fields[field] = float(raw_value)
        except (TypeError, ValueError):
            continue
    return fields


def _panel_src(path, site, orientation=None, auto_run=False, output_only=True):
    query = _default_query(orientation)
    try:
        query.update(_build_panel_query(site, orientation=orientation))
    except ValueError:
        logger.exception("Selected site could not be mapped to numerical panel inputs; using defaults.")
    for key, value in request.args.items():
        # compare_sites is multi-valued; the multiple routes pass it explicitly.
        if key not in {"site_id", "output_only", "compare_sites"} and value != "":
            query[key] = value
    query["email"] = _current_email()
    if request.args.get("run") == "1":
        query["run"] = 1
    else:
        query.pop("run", None)
    if output_only:
        query["output_only"] = 1
    return f"{_panel_base_url()}/{path}?{urlencode(query)}"


def _parameters_from_input_fields(input_fields):
    return [
        {
            "symbol": f["name"],
            "name": f["label"].split(" [")[0],
            "value": f["value"],
            "unit": f["label"].split("[")[-1].rstrip("]") if "[" in f["label"] else "-",
        }
        for f in input_fields
    ]


def _field_values(input_fields):
    return {f["name"]: f["value"] for f in input_fields}


def _simulation_pdf(parameters, outputs, plot_data, title, model_name, filename, plot_images=None):
    report = CASTReport(title, model_name)
    pdf_bytes = report.generate(
        parameters=parameters,
        outputs=outputs,
        plot_data=plot_data,
        plot_images=plot_images,
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _submit_export_job(kind, job_params, input_fields, report_meta):
    """Queue a numerical run and persist the context needed to build its PDF later."""
    job_id = submit_job(kind, job_params)
    save_job_meta(job_id, {
        "email": _current_email(),
        "parameters": _parameters_from_input_fields(input_fields),
        **report_meta,
    })
    return jsonify({
        "job_id": job_id,
        "status_url": url_for("numerical_bp.numerical_job_status", job_id=job_id),
        "report_url": url_for("numerical_bp.numerical_job_report", job_id=job_id),
    }), 202


def _horizontal_pdf(input_fields):
    values = _field_values(input_fields)
    return _submit_export_job(
        "horizontal_single",
        {
            "source_thickness": values["source_thickness"],
            "grid_size": values["grid_size"],
            "al": values["al"],
            "at": values["at"],
            "gamma": values["gamma"],
            "cd": values["C_D"],
            "ca": values["C_A"],
            "prsity": values["prsity"],
            "hk": values["hk"],
            "gradient": values["gradient"],
        },
        input_fields,
        {
            "lmax_label": "Horizontal Numerical Lmax",
            "plot_label": "Horizontal numerical",
            "plot_title": "Horizontal Numerical",
            "plot_image_title": "Horizontal Plume Concentration",
            "plot_image_caption": "Simulated contaminant plume — plan view (horizontal model).",
            "title": "Numerical Horizontal Model - Single Simulation",
            "model_name": "Numerical Horizontal",
            "filename": "numerical_horizontal_single_report.pdf",
        },
    )


def _vertical_pdf(input_fields):
    values = _field_values(input_fields)
    return _submit_export_job(
        "vertical_single",
        {
            "Lz": values["Lz"],
            "grid_size": values["grid_size"],
            "al": values["al"],
            "atv": values["atv"],
            "gamma": values["gamma"],
            "cd": values["C_D"],
            "ca": values["C_A"],
            "prsity": values["prsity"],
            "hk": values["hk"],
            "gradient": values["gradient"],
        },
        input_fields,
        {
            "lmax_label": "Vertical Numerical Lmax",
            "plot_label": "Vertical numerical",
            "plot_title": "Vertical Numerical",
            "plot_image_title": "Vertical Plume Concentration",
            "plot_image_caption": "Simulated contaminant plume — vertical cross-section.",
            "title": "Numerical Vertical Model - Single Simulation",
            "model_name": "Numerical Vertical",
            "filename": "numerical_vertical_single_report.pdf",
        },
    )


@numerical_bp.route("/numerical/jobs")
def numerical_jobs_summary():
    return jsonify(queue_counts())


def _owned_job_meta(job_id):
    """Return the job's metadata only if it belongs to the current user."""
    meta = load_job_meta(job_id)
    if meta is None or meta.get("email") != _current_email():
        return None
    return meta


def _job_not_found():
    return jsonify({"success": False, "message": "Unknown numerical job."}), 404


@numerical_bp.route("/numerical/jobs/<job_id>")
def numerical_job_status(job_id):
    if _owned_job_meta(job_id) is None:
        return _job_not_found()
    status = job_status(job_id)
    if status is None:
        return _job_not_found()
    payload = {
        "job_id": job_id,
        "status": status["status"],
        "queue_position": status.get("queue_position"),
        "plume_length": status.get("plume_length"),
        # The raw worker error can contain tracebacks/paths; never expose it.
        "error": (
            "Simulation failed. Please check your inputs and try again."
            if status["status"] == "failed"
            else None
        ),
    }
    if status["status"] == "done":
        payload["report_url"] = url_for("numerical_bp.numerical_job_report", job_id=job_id)
    return jsonify(payload)


@numerical_bp.route("/numerical/jobs/<job_id>/cancel", methods=["POST"])
@csrf_protect
def numerical_job_cancel(job_id):
    if _owned_job_meta(job_id) is None:
        return _job_not_found()
    return jsonify({"job_id": job_id, "cancelled": cancel_job(job_id)})


@numerical_bp.route("/numerical/jobs/<job_id>/report")
def numerical_job_report(job_id):
    meta = _owned_job_meta(job_id)
    if meta is None:
        return _job_not_found()
    status = job_status(job_id)
    if status is None:
        return _job_not_found()
    if status["status"] != "done":
        return jsonify({
            "success": False,
            "message": f"Report is not ready: job is {status['status']}.",
            "status": status["status"],
        }), 409
    try:
        result = fetch_result(job_id)
    except Exception:
        logger.exception("Numerical job result could not be loaded")
        return jsonify({
            "success": False,
            "message": "The result for this job is no longer available. Please run the simulation again.",
        }), 410
    plot_images = []
    if getattr(result, "plot_png", None):
        plot_images.append({
            "title": meta["plot_image_title"],
            "bytes": result.plot_png,
            "caption": meta["plot_image_caption"],
            "max_height_mm": 52,
        })
    cross_label = "Domain Width W_D" if hasattr(result, "domain_width") else "Aquifer Thickness T_A"
    cross_value = getattr(result, "domain_width", getattr(result, "aquifer_thickness", 0.0))
    return _simulation_pdf(
        meta["parameters"],
        [
            {"label": meta["lmax_label"], "value": f"{result.plume_length:.2f}", "unit": "m"},
            {"label": "Domain Length L_D", "value": f"{getattr(result, 'domain_length', 0.0):.2f}", "unit": "m"},
            {"label": cross_label, "value": f"{cross_value:.2f}", "unit": "m"},
            {"label": "Peclet Number", "value": f"{getattr(result, 'peclet', 0.0):.2f}", "unit": "-"},
            {"label": "Courant Target", "value": f"{getattr(result, 'courant', 5.0):.2f}", "unit": "-"},
        ],
        {
            "labels": [meta["plot_label"]],
            "values": [result.plume_length],
            "ylabel": "Maximum Plume Length L_max [m]",
            "title": meta["plot_title"],
        },
        meta["title"],
        meta["model_name"],
        meta["filename"],
        plot_images=plot_images or None,
    )


@numerical_bp.route("/numerical/jobs/<job_id>/download/<kind>")
def numerical_job_download(job_id, kind):
    """Download the raw MODFLOW head (.hds) or concentration (.ucn) file for a finished
    job (N8). Ownership-checked via the job meta."""
    meta = _owned_job_meta(job_id)
    if meta is None:
        return _job_not_found()
    status = job_status(job_id)
    if status is None or status.get("status") != "done":
        return _job_not_found()
    try:
        result = fetch_result(job_id)
    except Exception:
        logger.exception("Numerical job result could not be loaded for download")
        return _job_not_found()
    files = {
        "head": (getattr(result, "head_file", b""), "head.hds"),
        "concentration": (getattr(result, "concentration_file", b""), "concentration.ucn"),
    }
    if kind not in files or not files[kind][0]:
        return _job_not_found()
    data, suffix = files[kind]
    return Response(
        data,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={job_id}_{suffix}"},
    )


@numerical_bp.route("/numerical")
def numerical_landing():
    return render_template("numerical_landing.html")


@numerical_bp.route("/numerical/single")
def numerical_single():
    return redirect(url_for("numerical_bp.numerical_vertical_single", **request.args))


@numerical_bp.route("/numerical/multiple")
def numerical_multiple():
    return redirect(url_for("numerical_bp.numerical_vertical_multiple", **request.args))


@numerical_bp.route("/numerical/horizontal/single")
def numerical_horizontal_single():
    sites, selected_site, invalid_site_message = _selected_site("horizontal")
    orientation = "horizontal"
    input_fields = _input_fields("horizontal", selected_site)
    return render_template(
        "panel_numerical_horizontal_single.html",
        panel_src=_panel_src("panel_numerical_horizontal_single", selected_site, orientation="horizontal"),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        invalid_site_message=invalid_site_message,
        input_fields=input_fields,
        analytical_fields=_numerical_analytical_fields(orientation, input_fields),
        export_href=_export_href(input_fields),
        export_async=True,
    )


@numerical_bp.route("/numerical/horizontal/single/export")
@rate_limit(limit=6, window_seconds=60)
@guard_model_errors
def numerical_horizontal_single_export():
    input_fields = _input_fields("horizontal", None)
    return _horizontal_pdf(input_fields)


@numerical_bp.route("/numerical/horizontal/multiple")
def numerical_horizontal_multiple():
    # One run per site picked in the sidebar. Nothing is picked by default:
    # every selected site queues a full MODFLOW/MT3DMS job.
    sites, _selected, _invalid = _selected_site("horizontal")
    picked = compare_site_ids(sites)
    # Submitting the picker IS the run: the panel autoruns whatever is picked.
    panel_src = _panel_src("panel_numerical_horizontal_multiple", None, orientation="horizontal", output_only=False)
    panel_src += "&" + urlencode({"compare_sites": ",".join(str(i) for i in picked)})
    if picked:
        panel_src += "&run=1"
    return render_template(
        "panel_numerical_horizontal_multiple.html",
        panel_src=panel_src,
        sites=sites,
        compare_site_ids=picked,
        max_runs=NUMERICAL_MULTIPLE_MAX_RUNS,
        show_site_loader=False,
    )


@numerical_bp.route("/numerical/vertical/single")
def numerical_vertical_single():
    sites, selected_site, invalid_site_message = _selected_site("vertical")
    orientation = "vertical"
    input_fields = _input_fields("vertical", selected_site)
    return render_template(
        "panel_numerical_vertical_single.html",
        panel_src=_panel_src("panel_numerical_vertical_single", selected_site, orientation="vertical"),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        invalid_site_message=invalid_site_message,
        input_fields=input_fields,
        analytical_fields=_numerical_analytical_fields(orientation, input_fields),
        export_href=_export_href(input_fields),
        export_async=True,
    )


@numerical_bp.route("/numerical/vertical/single/export")
@rate_limit(limit=6, window_seconds=60)
@guard_model_errors
def numerical_vertical_single_export():
    input_fields = _input_fields("vertical", None)
    return _vertical_pdf(input_fields)


@numerical_bp.route("/numerical/vertical/multiple")
def numerical_vertical_multiple():
    # One run per site picked in the sidebar. Nothing is picked by default:
    # every selected site queues a full MODFLOW/MT3DMS job.
    sites, _selected, _invalid = _selected_site("vertical")
    picked = compare_site_ids(sites)
    # Submitting the picker IS the run: the panel autoruns whatever is picked.
    panel_src = _panel_src("panel_numerical_vertical_multiple", None, orientation="vertical", output_only=False)
    panel_src += "&" + urlencode({"compare_sites": ",".join(str(i) for i in picked)})
    if picked:
        panel_src += "&run=1"
    return render_template(
        "panel_numerical_vertical_multiple.html",
        panel_src=panel_src,
        sites=sites,
        compare_site_ids=picked,
        max_runs=NUMERICAL_MULTIPLE_MAX_RUNS,
        show_site_loader=False,
    )
