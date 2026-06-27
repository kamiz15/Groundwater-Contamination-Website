# empirical_routes.py
from urllib.parse import urlencode

from flask import Blueprint, Response, render_template, request
from flask_login import current_user, login_required

from data_queries import get_user_sites_rows
from model_site_validation import filter_valid_sites_for_model
from route_guards import guard_model_errors, request_finite_float
from empirical_models import birla_lmax, maier_lmax
from pdf_report import CASTReport
from settings import PANEL_PUBLIC_BASE

empirical_bp = Blueprint("empirical_bp", __name__)

EMPIRICAL_INPUT_SPECS = {
    "panel_maier_single": [
        ("M", "Aquifer Thickness M [m]", 5.0, "0.1", "0.000001"),
        ("tv", "Vertical Transverse Dispersivity tv [m]", 0.01, "0.001", "0.000001"),
        ("g", "Stoichiometry Coefficient g [-]", 3.5, "0.1", None),
        ("Ca", "Contaminant Concentration Ca [mg/L]", 8.0, "0.5", "0.000001"),
        ("Cd", "Reactant Concentration Cd [mg/L]", 5.0, "0.5", "0.000001"),
    ],
    "panel_maier_multiple": [
        ("M", "Aquifer Thickness M [m]", 5.0, "0.1", "0.000001"),
        ("tv", "Vertical Transverse Dispersivity tv [m]", 0.01, "0.001", "0.000001"),
        ("g", "Stoichiometry Coefficient g [-]", 3.5, "0.1", None),
        ("Ca", "Contaminant Concentration Ca [mg/L]", 8.0, "0.5", "0.000001"),
        ("Cd", "Reactant Concentration Cd [mg/L]", 5.0, "0.5", "0.000001"),
    ],
    "panel_birla_single": [
        ("M", "Aquifer Thickness M [m]", 2.0, "0.1", "0.000001"),
        ("tv", "Vertical Transverse Dispersivity tv [m]", 0.001, "0.0005", "0.000001"),
        ("g", "Stoichiometry Coefficient g [-]", 3.5, "0.1", None),
        ("Ca", "Contaminant Concentration Ca [mg/L]", 8.0, "0.5", "0.000001"),
        ("Cd", "Reactant Concentration Cd [mg/L]", 5.0, "0.5", "0.000001"),
        ("R", "Recharge Rate R [m/yr]", 1.0, "0.1", "0.000001"),
    ],
    "panel_birla_multiple": [
        ("M", "Aquifer Thickness M [m]", 2.0, "0.1", "0.000001"),
        ("tv", "Vertical Transverse Dispersivity tv [m]", 0.001, "0.0005", "0.000001"),
        ("g", "Stoichiometry Coefficient g [-]", 3.5, "0.1", None),
        ("Ca", "Contaminant Concentration Ca [mg/L]", 8.0, "0.5", "0.000001"),
        ("Cd", "Reactant Concentration Cd [mg/L]", 5.0, "0.5", "0.000001"),
        ("R", "Recharge Rate R [m/yr]", 1.0, "0.1", "0.000001"),
    ],
}


def _current_email():
    return current_user.email


def _panel_base_url():
    return PANEL_PUBLIC_BASE


def _default_query(path):
    return {
        name: default
        for name, _label, default, _step, _minimum in EMPIRICAL_INPUT_SPECS.get(path, [])
    }


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


_request_float = request_finite_float


def _input_fields(path, site):
    db_query = _build_panel_query(site)
    fields = []
    for name, label, default, step, minimum in EMPIRICAL_INPUT_SPECS.get(path, []):
        fields.append({
            "name": name,
            "label": label,
            "value": _request_float(name, db_query.get(name, default)),
            "step": step,
            "min": minimum,
            "from_db": name in db_query,
        })
    return fields


def _export_href(input_fields):
    query = {f["name"]: f["value"] for f in input_fields}
    return f"{request.path}/export?{urlencode(query)}"


def _build_panel_query(site):
    if not site:
        return {}
    query = {}
    m = _to_float(site.get("aquifer_thickness"))
    ca = _to_float(site.get("electron_acceptor_o2"))
    cd = _to_float(site.get("electron_donor"))
    if m is not None:
        query["M"] = m
    if ca is not None:
        query["Ca"] = ca
    if cd is not None:
        query["Cd"] = cd
    if site.get("id") is not None:
        query["site_id"] = int(site.get("id"))
    query["email"] = _current_email()
    return query


def _selected_site(model_name):
    """Sites usable by this model (others are hidden from its drop-down)."""
    sites = get_user_sites_rows(_current_email())
    sites, _invalid = filter_valid_sites_for_model(sites, model_name)
    if not sites:
        return sites, None
    selected_id = request.args.get("site_id", type=int)
    if selected_id is None:
        return sites, None
    for site in sites:
        if site.get("id") == selected_id:
            return sites, site
    return sites, None


def _panel_src(path, site, auto_run=False, output_only=True):
    query = _default_query(path)
    query.update(_build_panel_query(site))
    for key, value in request.args.items():
        if key not in {"site_id", "output_only"} and value != "":
            query[key] = value
    query["email"] = _current_email()
    query["run"] = 1
    if output_only:
        query["output_only"] = 1
    return f"{_panel_base_url()}/{path}?{urlencode(query)}"


@empirical_bp.route("/empirical")
@login_required
def empirical_landing():
    return render_template("empirical_landing.html")


@empirical_bp.route("/empirical/maier/single")
@login_required
def maier_single():
    sites, selected_site = _selected_site("maier")
    input_fields = _input_fields("panel_maier_single", selected_site)
    return render_template(
        "panel_maier_single.html",
        panel_src=_panel_src("panel_maier_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href(input_fields),
    )


@empirical_bp.route("/empirical/maier/single/export")
@login_required
@guard_model_errors
def maier_single_export():
    m = _request_float("M", 5.0)
    tv = _request_float("tv", 0.01)
    g = _request_float("g", 3.5)
    ca = _request_float("Ca", 8.0)
    cd = _request_float("Cd", 5.0)
    lmax = maier_lmax(m, tv, g, ca, cd)
    report = CASTReport("Maier & Grathwohl — Single Simulation", "Maier Empirical")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "M", "name": "Aquifer Thickness", "value": m, "unit": "m"},
            {"symbol": "tv", "name": "Vert. Trans. Dispersivity", "value": tv, "unit": "m"},
            {"symbol": "g", "name": "Stoichiometry Coefficient", "value": g, "unit": "-"},
            {"symbol": "Ca", "name": "Contaminant Concentration", "value": ca, "unit": "mg/L"},
            {"symbol": "Cd", "name": "Reactant Concentration", "value": cd, "unit": "mg/L"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data={"labels": ["Lmax"], "values": [lmax], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — Maier & Grathwohl"},
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=maier_single_report.pdf"},
    )


@empirical_bp.route("/empirical/maier/multiple")
@login_required
def maier_multiple():
    sites, selected_site = _selected_site("maier")
    return render_template(
        "panel_maier_multiple.html",
        panel_src=_panel_src("panel_maier_multiple", selected_site, output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=_input_fields("panel_maier_multiple", selected_site),
    )


@empirical_bp.route("/empirical/birla/single")
@login_required
def birla_single():
    sites, selected_site = _selected_site("birla")
    input_fields = _input_fields("panel_birla_single", selected_site)
    return render_template(
        "panel_birla_single.html",
        panel_src=_panel_src("panel_birla_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href(input_fields),
    )


@empirical_bp.route("/empirical/birla/single/export")
@login_required
@guard_model_errors
def birla_single_export():
    m = _request_float("M", 2.0)
    tv = _request_float("tv", 0.001)
    g = _request_float("g", 3.5)
    ca = _request_float("Ca", 8.0)
    cd = _request_float("Cd", 5.0)
    r = _request_float("R", 1.0)
    lmax = birla_lmax(m, tv, g, ca, cd, r)
    report = CASTReport("Birla et al. — Single Simulation", "Birla Empirical")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "M", "name": "Aquifer Thickness", "value": m, "unit": "m"},
            {"symbol": "tv", "name": "Vert. Trans. Dispersivity", "value": tv, "unit": "m"},
            {"symbol": "g", "name": "Stoichiometry Coefficient", "value": g, "unit": "-"},
            {"symbol": "Ca", "name": "Contaminant Concentration", "value": ca, "unit": "mg/L"},
            {"symbol": "Cd", "name": "Reactant Concentration", "value": cd, "unit": "mg/L"},
            {"symbol": "R", "name": "Recharge Rate", "value": r, "unit": "m/yr"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data={"labels": ["Lmax"], "values": [lmax], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — Birla et al."},
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=birla_single_report.pdf"},
    )


@empirical_bp.route("/empirical/birla/multiple")
@login_required
def birla_multiple():
    sites, selected_site = _selected_site("birla")
    return render_template(
        "panel_birla_multiple.html",
        panel_src=_panel_src("panel_birla_multiple", selected_site, output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=_input_fields("panel_birla_multiple", selected_site),
    )
