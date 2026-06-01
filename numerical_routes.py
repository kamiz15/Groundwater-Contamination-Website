from urllib.parse import urlencode

import numpy as np
from flask import Blueprint, Response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from analytical_models import cirpka_domain_length, cirpka_lmax, liedl_domain_length, liedl_lmax
from data_queries import get_user_sites_rows
from numerical_models import balanced_source_buffers, run_numerical_model, run_numerical_model_horizontal
from pdf_report import CASTReport
from settings import PANEL_PUBLIC_BASE
from symbol_registry import db_hydraulic_conductivity_to_numerical_hk, db_to_model

numerical_bp = Blueprint("numerical_bp", __name__)

NUMERICAL_INPUT_SPECS = {
    "horizontal": [
        ("Sw", "Source Width Sw [m]", 5.0, "0.1", "0.000001"),
        ("R_Wu", "Upper Reactant Buffer R_Wu [m]", 7.5, "0.1", "0"),
        ("R_Wb", "Lower Reactant Buffer R_Wb [m]", 7.5, "0.1", "0"),
        ("delta_x", "Grid Spacing dx [m]", 1.0, "0.1", "0.000001"),
        ("delta_y", "Lateral Grid Spacing dy [m]", 0.25, "0.05", "0.000001"),
        ("al", "Longitudinal Dispersivity alpha L [m]", 5.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity alpha Th [m]", 0.1, "0.01", "0.000001"),
        ("prsity", "Porosity n [-]", 0.3, "0.01", "0.000001"),
        ("hk", "Hydraulic Conductivity K [m/d]", 1.0, "0.1", "0.000001"),
        ("h1", "Head at Left Domain H_L [m]", 10.0, "0.1", None),
        ("h2", "Head at Right Domain H_R [m]", 9.0, "0.1", None),
        ("C_D", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
        ("C_A", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C0", "Plume Contour Threshold C0 [mg/L]", 8.0, "0.1", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.5, "0.1", None),
        ("perlen", "Simulation Time [day]", 100.0, "1", "0.000001"),
    ],
    "vertical": [
        ("M", "Aquifer Thickness M [m]", 5.0, "0.1", "0.000001"),
        ("S_T", "Source Thickness ST [m]", 1.0, "0.1", "0.000001"),
        ("S_Ta", "Buffer Above STa [m]", 2.0, "0.1", "0"),
        ("S_Tb", "Buffer Below STb [m]", 2.0, "0.1", "0"),
        ("delta_x", "Grid Spacing dx [m]", 1.0, "0.1", "0.000001"),
        ("delta_z", "Vertical Grid Spacing dz [m]", 0.25, "0.05", "0.000001"),
        ("al", "Longitudinal Dispersivity alpha L [m]", 5.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity alpha Th [m]", 0.2, "0.01", "0.000001"),
        ("alpha_Tv", "Vertical Transverse Dispersivity alpha Tv [m]", 0.5, "0.1", "0.000001"),
        ("prsity", "Porosity n [-]", 0.3, "0.01", "0.000001"),
        ("hk", "Horizontal Hydraulic Conductivity K_h [m/d]", 1.0, "0.1", "0.000001"),
        ("vk", "Vertical Hydraulic Conductivity K_v [m/d]", 1.0, "0.1", "0.000001"),
        ("h1", "Head at Left Domain H_L [m]", 10.0, "0.1", None),
        ("h2", "Head at Right Domain H_R [m]", 9.0, "0.1", None),
        ("C_D", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
        ("C_A", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C0", "Plume Contour Threshold C0 [mg/L]", 8.0, "0.1", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.5, "0.1", None),
        ("perlen", "Simulation Time [day]", 100.0, "1", "0.000001"),
    ],
}

NUMERICAL_ADVANCED_INPUT_SPECS = {
    "horizontal": [
        ("L_D_override", "Domain Length LD Override [m]", None, "1", "0"),
    ],
    "vertical": [
        ("L_D_override", "Domain Length LD Override [m]", None, "1", "0"),
    ],
}


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


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _request_float(name, default):
    try:
        raw = request.args.get(name)
        if raw in (None, ""):
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _input_fields(orientation, site):
    db_query = _build_panel_query(site, orientation=orientation)
    dynamic_defaults = {}
    if orientation == "vertical":
        m = _request_float("M", db_query.get("M", 5.0))
        s_t = _request_float("S_T", min(1.0, m))
        if m > 0 and 0 < s_t <= m:
            s_ta, s_tb = balanced_source_buffers(m, s_t)
            dynamic_defaults = {"M": m, "S_T": s_t, "S_Ta": s_ta, "S_Tb": s_tb}
    fields = []
    for name, label, default, step, minimum in NUMERICAL_INPUT_SPECS.get(orientation, []):
        fields.append({
            "name": name,
            "label": label,
            "value": _request_float(name, db_query.get(name, dynamic_defaults.get(name, default))),
            "step": step,
            "min": minimum,
            "from_db": name in db_query,
            "advanced": False,
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


def _selected_site():
    sites = get_user_sites_rows(_current_email())
    if not sites:
        return sites, None
    selected_id = request.args.get("site_id", type=int)
    if selected_id is None:
        return sites, None
    for site in sites:
        if site.get("id") == selected_id:
            return sites, site
    return sites, None


def _build_panel_query(site, orientation=None):
    if not site:
        return {}

    canonical = db_to_model(site, "numerical")

    query = {"email": _current_email()}
    if orientation:
        query["orientation"] = orientation
    if site.get("id") is not None:
        query["site_id"] = int(site.get("id"))
    for symbol, value in canonical.items():
        if symbol == "M":
            query["M"] = value
        elif symbol == "S_w":
            query["S_w"] = value
            query["Sw"] = value
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
    query.update(_build_panel_query(site, orientation=orientation))
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


def _inputs_only_pdf(input_fields, title, model_name, filename):
    parameters = [
        {"symbol": f["name"], "name": f["label"].split(" [")[0], "value": f["value"], "unit": f["label"].split("[")[-1].rstrip("]") if "[" in f["label"] else "-"}
        for f in input_fields
    ]
    report = CASTReport(title, model_name)
    pdf_bytes = report.generate(
        parameters=parameters,
        outputs=[{"label": "Run simulation to compute outputs", "value": "—", "unit": ""}],
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


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


def _horizontal_pdf(input_fields):
    values = _field_values(input_fields)
    analytical_lmax = cirpka_lmax(values["Sw"], values["alpha_Th"], values["gamma"], values["C_A"], values["C_D"])
    ld = cirpka_domain_length(analytical_lmax, values.get("L_D_override"))
    domain_width = values["R_Wb"] + values["Sw"] + values["R_Wu"]
    ncol = max(int(np.ceil(ld / values["delta_x"])), 2)
    nrow = max(int(np.ceil(domain_width / values["delta_y"])), 2)

    result = run_numerical_model_horizontal(
        ld,
        domain_width,
        values["Sw"],
        ncol,
        nrow,
        values["prsity"],
        values["al"],
        values["alpha_Th"],
        values["gamma"],
        values["C_D"],
        values["C_A"],
        values["h1"],
        values["h2"],
        values["hk"],
        perlen=values["perlen"],
        plume_threshold=values["C0"],
    )
    plot_images = []
    if result.plot_png:
        plot_images.append({
            "title": "Horizontal Plume Concentration",
            "bytes": result.plot_png,
            "caption": "Simulated contaminant plume — plan view (horizontal model).",
        })
    return _simulation_pdf(
        _parameters_from_input_fields(input_fields),
        [
            {"label": "Horizontal Numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"},
            {"label": "Cirpka Lmax", "value": f"{analytical_lmax:.2f}", "unit": "m"},
            {"label": "Domain Length LD", "value": f"{ld:.2f}", "unit": "m"},
        ],
        {
            "labels": ["Cirpka analytical", "Horizontal numerical"],
            "values": [analytical_lmax, result.plume_length],
            "ylabel": "Plume Length (m)",
            "title": "Horizontal Numerical vs Cirpka",
        },
        "Numerical Horizontal Model - Single Simulation",
        "Numerical Horizontal",
        "numerical_horizontal_single_report.pdf",
        plot_images=plot_images,
    )


def _vertical_pdf(input_fields):
    values = _field_values(input_fields)
    analytical_lmax = liedl_lmax(values["M"], values["alpha_Tv"], values["gamma"], values["C_A"], values["C_D"])
    ld = liedl_domain_length(analytical_lmax, values.get("L_D_override"))
    ncol = max(int(np.ceil(ld / values["delta_x"])), 2)
    nrow = max(int(np.ceil(values["M"] / values["delta_z"])), 2)

    result = run_numerical_model(
        ld,
        values["M"],
        ncol,
        nrow,
        values["prsity"],
        values["al"],
        values["alpha_Tv"],
        values["gamma"],
        values["C_D"],
        values["C_A"],
        values["h1"],
        values["h2"],
        values["hk"],
        values["vk"],
        source_thickness=values["S_T"],
        source_bottom_buffer=values["S_Tb"],
        perlen=values["perlen"],
        plume_threshold=values["C0"],
        ath=values["alpha_Th"],
    )
    plot_images = []
    if result.plot_png:
        plot_images.append({
            "title": "Vertical Plume Concentration",
            "bytes": result.plot_png,
            "caption": "Simulated contaminant plume — vertical cross-section.",
        })
    return _simulation_pdf(
        _parameters_from_input_fields(input_fields),
        [
            {"label": "Vertical Numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"},
            {"label": "Liedl Lmax", "value": f"{analytical_lmax:.2f}", "unit": "m"},
            {"label": "Domain Length LD", "value": f"{ld:.2f}", "unit": "m"},
        ],
        {
            "labels": ["Liedl analytical", "Vertical numerical"],
            "values": [analytical_lmax, result.plume_length],
            "ylabel": "Plume Length (m)",
            "title": "Vertical Numerical vs Liedl",
        },
        "Numerical Vertical Model - Single Simulation",
        "Numerical Vertical",
        "numerical_vertical_single_report.pdf",
        plot_images=plot_images,
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
    sites, selected_site = _selected_site()
    input_fields = _input_fields("horizontal", selected_site)
    return render_template(
        "panel_numerical_horizontal_single.html",
        panel_src=_panel_src("panel_numerical_horizontal_single", selected_site, orientation="horizontal"),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href(input_fields),
    )


@numerical_bp.route("/numerical/horizontal/single/export")
@login_required
def numerical_horizontal_single_export():
    input_fields = _input_fields("horizontal", None)
    return _horizontal_pdf(input_fields)


@numerical_bp.route("/numerical/horizontal/multiple")
@login_required
def numerical_horizontal_multiple():
    sites, selected_site = _selected_site()
    input_fields = _input_fields("horizontal", selected_site)
    return render_template(
        "panel_numerical_horizontal_multiple.html",
        panel_src=_panel_src("panel_numerical_horizontal_multiple", selected_site, orientation="horizontal", output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href(input_fields),
    )


@numerical_bp.route("/numerical/vertical/single")
@login_required
def numerical_vertical_single():
    sites, selected_site = _selected_site()
    input_fields = _input_fields("vertical", selected_site)
    return render_template(
        "panel_numerical_vertical_single.html",
        panel_src=_panel_src("panel_numerical_vertical_single", selected_site, orientation="vertical"),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href(input_fields),
    )


@numerical_bp.route("/numerical/vertical/single/export")
@login_required
def numerical_vertical_single_export():
    input_fields = _input_fields("vertical", None)
    return _vertical_pdf(input_fields)


@numerical_bp.route("/numerical/vertical/multiple")
@login_required
def numerical_vertical_multiple():
    sites, selected_site = _selected_site()
    input_fields = _input_fields("vertical", selected_site)
    return render_template(
        "panel_numerical_vertical_multiple.html",
        panel_src=_panel_src("panel_numerical_vertical_multiple", selected_site, orientation="vertical", output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href(input_fields),
    )
