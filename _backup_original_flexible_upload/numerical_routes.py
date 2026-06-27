import logging
from urllib.parse import urlencode

from flask import Blueprint, Response, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

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
from security import csrf_protect, rate_limit
from route_guards import guard_model_errors, request_finite_float
from numerical_input_validation import format_issues, vertical_inputs_from_site
from pdf_report import CASTReport
from settings import PANEL_PUBLIC_BASE
from symbol_registry import db_hydraulic_conductivity_to_numerical_hk, db_to_model

numerical_bp = Blueprint("numerical_bp", __name__)
logger = logging.getLogger(__name__)

NUMERICAL_INPUT_SPECS = {
    "horizontal": [
        ("source_thickness", "Source Thickness Sw [m]", 5.0, "0.1", "0.000001"),
        ("grid_size", "Grid Size dx=dy [m]", 1.0, "0.1", "0.000001"),
        ("al", "Longitudinal Dispersivity aL [m]", 1.0, "0.1", "0.000001"),
        ("at", "Transverse Dispersivity aT [m]", 0.2, "0.01", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.5, "0.1", None),
        ("C_D", "Electron Donor Cd [mg/L]", 5.0, "0.1", "0.000001"),
        ("C_A", "Electron Acceptor Ca [mg/L]", 8.0, "0.1", "0.000001"),
        ("prsity", "Porosity n [-]", 0.3, "0.01", "0.000001"),
        ("hk", "Hydraulic Conductivity K [m/d]", 8.64, "0.1", "0.000001"),
        ("gradient", "Hydraulic Gradient i [-]", 0.0125, "0.001", "0.000001"),
    ],
    "vertical": [
        ("Lz", "Aquifer Thickness Lz [m]", 10.0, "0.1", "0.000001"),
        ("grid_size", "Grid Size dx=dz [m]", 1.0, "0.1", "0.000001"),
        ("al", "Longitudinal Dispersivity aL [m]", 1.0, "0.1", "0.000001"),
        ("atv", "Vertical Transverse Dispersivity aTv [m]", 0.1, "0.01", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.5, "0.1", None),
        ("C_D", "Electron Donor Cd [mg/L]", 5.0, "0.1", "0.000001"),
        ("C_A", "Electron Acceptor Ca [mg/L]", 8.0, "0.1", "0.000001"),
        ("prsity", "Porosity n [-]", 0.3, "0.01", "0.000001"),
        ("hk", "Hydraulic Conductivity K [m/d]", 8.64, "0.1", "0.000001"),
        ("gradient", "Hydraulic Gradient i [-]", 0.0125, "0.001", "0.000001"),
    ],
}

NUMERICAL_ADVANCED_INPUT_SPECS = {
    "horizontal": [],
    "vertical": [],
}

# Which of the 3 form columns each numerical field belongs to (Issue #4).
NUMERICAL_FIELD_COLUMN = {
    "source_thickness": "input", "Lz": "input", "grid_size": "input",
    "al": "input", "at": "input", "atv": "input", "gamma": "input",
    "C_D": "input", "C_A": "input",
    "prsity": "standard", "hk": "standard", "gradient": "standard",
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
                {"label": "Domain Width [m]", "value": 10.0 * sw},
            ]
        import numpy as _np
        lz = float(vals["Lz"])
        lmax = 1.5 * (4.0 * lz ** 2) / (_np.pi ** 2 * float(vals["atv"])) * _np.log(
            (4.0 * float(vals["gamma"]) * float(vals["C_D"]) + float(vals["C_A"]))
            / (_np.pi * float(vals["C_A"])))
        return [
            {"label": "Domain Length L_D [m]", "value": float(lmax)},
            {"label": "Aquifer Thickness Lz [m]", "value": lz},
        ]
    except Exception:
        return []



def _current_email():
    return current_user.email


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
        fields.append({
            "name": name,
            "label": label,
            "value": _request_float(name, db_query.get(name, default)),
            "step": step,
            "min": minimum,
            "from_db": name in db_query,
            "advanced": False,
            "column": NUMERICAL_FIELD_COLUMN.get(name, "input"),
        })
    for name, label, default, step, minimum in NUMERICAL_ADVANCED_INPUT_SPECS.get(orientation, []):
        fields.append({
            "name": name,
            "label": label,
            "value": _request_float(name, default),
            "step": step,
            "min": minimum,
            "from_db": False,
            "advanced": True,
        })
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
    if not site:
        return {}

    if orientation == "vertical":
        vertical_inputs, issues = vertical_inputs_from_site(site)
        if issues:
            raise ValueError(format_issues(issues))
        query = {"email": _current_email()}
        query["orientation"] = "vertical"
        if site.get("id") is not None:
            query["site_id"] = int(site.get("id"))
        query["M"] = vertical_inputs["Lz"]
        query["Lz"] = vertical_inputs["Lz"]
        query["K"] = vertical_inputs["hk"]
        query["hk"] = vertical_inputs["hk"]
        query["C_D"] = vertical_inputs["C_D"]
        query["Cd"] = vertical_inputs["C_D"]
        query["C_ED0"] = vertical_inputs["C_D"]
        query["c0"] = vertical_inputs["C_D"]
        query["C_A"] = vertical_inputs["C_A"]
        query["Ca"] = vertical_inputs["C_A"]
        query["C_EA0"] = vertical_inputs["C_A"]
        return query

    canonical = db_to_model(site, "numerical")

    query = {"email": _current_email()}
    if orientation:
        query["orientation"] = orientation
    if site.get("id") is not None:
        query["site_id"] = int(site.get("id"))
    for symbol, value in canonical.items():
        if symbol == "M":
            query["M"] = value
            query["Lz"] = value
        elif symbol == "S_w":
            query["S_w"] = value
            query["Sw"] = value
            query["source"] = value
            query["source_thickness"] = value  # new field name (N6)
        elif symbol == "K":
            numerical_hk = db_hydraulic_conductivity_to_numerical_hk(value)
            query["K"] = numerical_hk
            query["hk"] = numerical_hk
            if orientation == "vertical":
                query.setdefault("vk", numerical_hk)
                query.setdefault("K_v", numerical_hk)
        elif symbol == "C_D":
            query["C_D"] = value
            query["Cd"] = value
            query["C_ED0"] = value
            query["c0"] = value
        elif symbol == "C_A":
            query["C_A"] = value
            query["Ca"] = value
            query["C_EA0"] = value
        else:
            query[symbol] = value
    return query


def _panel_src(path, site, orientation=None, auto_run=False, output_only=True):
    query = _default_query(orientation)
    try:
        query.update(_build_panel_query(site, orientation=orientation))
    except ValueError:
        logger.exception("Selected site could not be mapped to numerical panel inputs; using defaults.")
    for key, value in request.args.items():
        if key not in {"site_id", "output_only"} and value != "":
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
@login_required
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
@login_required
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
@login_required
@csrf_protect
def numerical_job_cancel(job_id):
    if _owned_job_meta(job_id) is None:
        return _job_not_found()
    return jsonify({"job_id": job_id, "cancelled": cancel_job(job_id)})


@numerical_bp.route("/numerical/jobs/<job_id>/report")
@login_required
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
    cross_label = "Domain Width" if hasattr(result, "domain_width") else "Aquifer Thickness"
    cross_value = getattr(result, "domain_width", getattr(result, "aquifer_thickness", 0.0))
    return _simulation_pdf(
        meta["parameters"],
        [
            {"label": meta["lmax_label"], "value": f"{result.plume_length:.2f}", "unit": "m"},
            {"label": "Domain Length LD", "value": f"{getattr(result, 'domain_length', 0.0):.2f}", "unit": "m"},
            {"label": cross_label, "value": f"{cross_value:.2f}", "unit": "m"},
            {"label": "Peclet Number", "value": f"{getattr(result, 'peclet', 0.0):.2f}", "unit": "-"},
            {"label": "Courant Target", "value": f"{getattr(result, 'courant', 5.0):.2f}", "unit": "-"},
        ],
        {
            "labels": [meta["plot_label"]],
            "values": [result.plume_length],
            "ylabel": "Plume Length (m)",
            "title": meta["plot_title"],
        },
        meta["title"],
        meta["model_name"],
        meta["filename"],
        plot_images=plot_images or None,
    )


@numerical_bp.route("/numerical/jobs/<job_id>/download/<kind>")
@login_required
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
@login_required
def numerical_landing():
    return render_template("numerical_landing.html")


@numerical_bp.route("/numerical/single")
@login_required
def numerical_single():
    return redirect(url_for("numerical_bp.numerical_vertical_single", **request.args))


@numerical_bp.route("/numerical/multiple")
@login_required
def numerical_multiple():
    return redirect(url_for("numerical_bp.numerical_vertical_multiple", **request.args))


@numerical_bp.route("/numerical/horizontal/single")
@login_required
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
@login_required
@rate_limit(limit=6, window_seconds=60)
@guard_model_errors
def numerical_horizontal_single_export():
    input_fields = _input_fields("horizontal", None)
    return _horizontal_pdf(input_fields)


@numerical_bp.route("/numerical/horizontal/multiple")
@login_required
def numerical_horizontal_multiple():
    sites, selected_site, invalid_site_message = _selected_site("horizontal")
    input_fields = _input_fields("horizontal", selected_site)
    return render_template(
        "panel_numerical_horizontal_multiple.html",
        panel_src=_panel_src("panel_numerical_horizontal_multiple", selected_site, orientation="horizontal", output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        invalid_site_message=invalid_site_message,
        input_fields=input_fields,
        export_href=_export_href(input_fields),
    )


@numerical_bp.route("/numerical/vertical/single")
@login_required
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
@login_required
@rate_limit(limit=6, window_seconds=60)
@guard_model_errors
def numerical_vertical_single_export():
    input_fields = _input_fields("vertical", None)
    return _vertical_pdf(input_fields)


@numerical_bp.route("/numerical/vertical/multiple")
@login_required
def numerical_vertical_multiple():
    sites, selected_site, invalid_site_message = _selected_site("vertical")
    input_fields = _input_fields("vertical", selected_site)
    return render_template(
        "panel_numerical_vertical_multiple.html",
        panel_src=_panel_src("panel_numerical_vertical_multiple", selected_site, orientation="vertical", output_only=False),
           sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        invalid_site_message=invalid_site_message,
        input_fields=input_fields,
        export_href=_export_href(input_fields),
    )
