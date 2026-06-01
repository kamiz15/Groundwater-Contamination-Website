# analytical_routes.py
import logging
from urllib.parse import urlencode

from bokeh.embed import components
from flask import Blueprint, Response, render_template, request
from flask_login import current_user, login_required

from analytical_models import (
    chu_lmax,
    cirpka_domain_length,
    cirpka_lmax,
    ham_lmax,
    liedl_lmax,
    liedl3d_lmax,
)
from bioscreen_model import bio
from data_queries import get_user_sites_rows
from panel_analytical_common import comparison_plot
from pdf_report import CASTReport
from security import GENERIC_DATABASE_ERROR_MESSAGE
from settings import PANEL_PUBLIC_BASE
from symbol_registry import db_to_model

analytical_bp = Blueprint("analytical_bp", __name__)
logger = logging.getLogger(__name__)

ANALYTICAL_INPUT_SPECS = {
    "panel_liedl_single": [
        ("M", "Aquifer Thickness M [m]", 3.5, "0.1", "0.000001"),
        ("alpha_Tv", "Transverse Dispersivity alpha Tv [m]", 0.001, "0.0001", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.5, "0.1", None),
        ("C_EA0", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
    ],
    "panel_liedl_multiple": [
        ("M", "Aquifer Thickness M [m]", 3.5, "0.1", "0.000001"),
        ("alpha_Tv", "Transverse Dispersivity alpha Tv [m]", 0.001, "0.0001", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.5, "0.1", None),
        ("C_EA0", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
    ],
    "panel_liedl3d_single": [
        ("M", "Source Thickness M [m]", 10.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity alpha Th [m]", 0.01, "0.001", "0.000001"),
        ("alpha_Tv", "Vertical Transverse Dispersivity alpha Tv [m]", 0.01, "0.001", "0.000001"),
        ("W", "Source Width W [m]", 7.0, "0.1", "0.000001"),
        ("Cthres", "Threshold Concentration [mg/L]", 0.5, "0.01", "0.000001"),
        ("C_EA0", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.0, "0.1", None),
    ],
    "panel_liedl3d_multiple": [
        ("M", "Source Thickness M [m]", 10.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity alpha Th [m]", 0.01, "0.001", "0.000001"),
        ("alpha_Tv", "Vertical Transverse Dispersivity alpha Tv [m]", 0.01, "0.001", "0.000001"),
        ("W", "Source Width W [m]", 7.0, "0.1", "0.000001"),
        ("Cthres", "Threshold Concentration [mg/L]", 0.5, "0.01", "0.000001"),
        ("C_EA0", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.0, "0.1", None),
    ],
    "panel_chu_single": [
        ("W", "Source Width W [m]", 2.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity alpha Th [m]", 0.01, "0.001", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 1.5, "0.1", None),
        ("C_EA0", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
        ("epsilon", "Biological Factor epsilon [mg/L]", 0.0, "0.01", None),
    ],
    "panel_chu_multiple": [
        ("W", "Source Width W [m]", 2.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity alpha Th [m]", 0.01, "0.001", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 1.5, "0.1", None),
        ("C_EA0", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
        ("epsilon", "Biological Factor epsilon [mg/L]", 0.0, "0.01", None),
    ],
    "panel_ham_single": [
        ("Q", "Source Flux Q [m2/yr]", 5.0, "0.1", "0.000001"),
        ("alpha_T", "Transverse Dispersivity alpha T [m]", 0.01, "0.001", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.5, "0.1", None),
        ("C_EA0", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
    ],
    "panel_ham_multiple": [
        ("Q", "Source Flux Q [m2/yr]", 5.0, "0.1", "0.000001"),
        ("alpha_T", "Transverse Dispersivity alpha T [m]", 0.01, "0.001", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.5, "0.1", None),
        ("C_EA0", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
    ],
    "panel_bioscreen_single": [
        ("Cthres", "Threshold Concentration Cthres [mg/L]", 5e-5, "0.00001", "0"),
        ("time", "Simulation Time [yr]", 20, "1", "1"),
        ("H", "Source Thickness H [m]", 5.0, "0.1", "0.000001"),
        ("c0", "Source Concentration c0 [mg/L]", 100.0, "1", "0.000001"),
        ("W", "Source Width W [m]", 10.0, "0.1", "0.000001"),
        ("v", "Groundwater Velocity v [m/yr]", 50.0, "1", "0.000001"),
        ("ax", "Longitudinal Dispersivity ax [m]", 10.0, "0.5", "0.000001"),
        ("ay", "Horizontal Transverse Dispersivity ay [m]", 0.5, "0.1", "0.000001"),
        ("az", "Vertical Transverse Dispersivity az [m]", 0.05, "0.01", "0.000001"),
        ("Df", "Effective Diffusion Coefficient Df [m2/yr]", 0.0, "0.001", "0"),
        ("R", "Retardation Factor R [-]", 1.0, "0.1", "0.01"),
        ("gamma", "Source Decay gamma [1/yr]", 0.0, "0.01", "0"),
        ("lam", "First-order Decay lambda [1/yr]", 0.1, "0.01", "0"),
        ("ng", "Gauss Points ng [-]", 60, "1", "4"),
    ],
    "panel_bioscreen_multiple": [
        ("Cthres", "Threshold Concentration Cthres [mg/L]", 5e-5, "0.00001", "0"),
        ("time", "Simulation Time [yr]", 20, "1", "1"),
        ("H", "Source Thickness H [m]", 5.0, "0.1", "0.000001"),
        ("c0", "Source Concentration c0 [mg/L]", 100.0, "1", "0.000001"),
        ("W", "Source Width W [m]", 10.0, "0.1", "0.000001"),
        ("v", "Groundwater Velocity v [m/yr]", 50.0, "1", "0.000001"),
        ("ax", "Longitudinal Dispersivity ax [m]", 10.0, "0.5", "0.000001"),
        ("ay", "Horizontal Transverse Dispersivity ay [m]", 0.5, "0.1", "0.000001"),
        ("az", "Vertical Transverse Dispersivity az [m]", 0.05, "0.01", "0.000001"),
        ("Df", "Effective Diffusion Coefficient Df [m2/yr]", 0.0, "0.001", "0"),
        ("R", "Retardation Factor R [-]", 1.0, "0.1", "0.01"),
        ("gamma", "Source Decay gamma [1/yr]", 0.0, "0.01", "0"),
        ("lam", "First-order Decay lambda [1/yr]", 0.1, "0.01", "0"),
        ("ng", "Gauss Points ng [-]", 60, "1", "4"),
    ],
    "panel_cirpka_single": [
        ("Sw", "Source Width Sw [m]", 10.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity alpha Th [m]", 0.1, "0.001", "0.000001"),
        ("C_A", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_D", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.5, "0.1", None),
    ],
    "panel_cirpka_multiple": [
        ("Sw", "Source Width Sw [m]", 10.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity alpha Th [m]", 0.1, "0.001", "0.000001"),
        ("C_A", "Electron Acceptor CA [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_D", "Electron Donor CD [mg/L]", 5.0, "0.1", "0.000001"),
        ("gamma", "Stoichiometric Ratio gamma [-]", 3.5, "0.1", None),
    ],
}


def _current_email():
    return current_user.email


def _panel_base_url():
    return PANEL_PUBLIC_BASE


def _default_query(path):
    return {
        name: default
        for name, _label, default, _step, _minimum in ANALYTICAL_INPUT_SPECS.get(path, [])
    }


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _model_name_from_panel_path(path):
    if "cirpka" in path:
        return "cirpka"
    if "liedl3d" in path:
        return "liedl3d"
    if "liedl" in path:
        return "liedl"
    if "chu" in path:
        return "chu"
    if "ham" in path:
        return "ham"
    if "bioscreen" in path:
        return "bioscreen"
    return path.replace("panel_", "").replace("_single", "").replace("_multiple", "")


def _build_panel_query(path, site):
    if not site:
        return {}

    canonical = db_to_model(site, _model_name_from_panel_path(path))

    query = {}
    if "liedl3d" in path:
        query.setdefault("Cthres", 0.5)
    if site.get("id") is not None:
        query["site_id"] = int(site.get("id"))
    query["email"] = _current_email()

    for symbol, value in canonical.items():
        if symbol == "M":
            query["M"] = value
            query["H"] = value
        elif symbol == "S_w":
            query["S_w"] = value
            query["Sw"] = value
            query["W"] = value
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


def _panel_src(path, site, auto_run=False, output_only=True):
    query = _default_query(path)
    query.update(_build_panel_query(path, site))
    for key, value in request.args.items():
        if key not in {"site_id", "output_only"} and value != "":
            query[key] = value
    query["email"] = _current_email()
    query["run"] = 1
    if output_only:
        query["output_only"] = 1
    return f"{_panel_base_url()}/{path}?{urlencode(query)}"


def _request_float(name, default):
    try:
        raw = request.args.get(name)
        if raw in (None, ""):
            return default
        return float(raw)
    except (TypeError, ValueError):
        return default


def _request_int(name, default):
    try:
        raw = request.args.get(name)
        if raw in (None, ""):
            return default
        return int(float(raw))
    except (TypeError, ValueError):
        return default


def _input_fields(path, site):
    db_query = _build_panel_query(path, site)
    fields = []
    for name, label, default, step, minimum in ANALYTICAL_INPUT_SPECS.get(path, []):
        fields.append({
            "name": name,
            "label": label,
            "value": _request_float(name, db_query.get(name, default)),
            "step": step,
            "min": minimum,
            "from_db": name in db_query,
        })
    return fields


def _export_href(path, input_fields):
    query = {f["name"]: f["value"] for f in input_fields}
    return f"{request.path}/export?{urlencode(query)}"


def _cirpka_single_params(site):
    db_query = _build_panel_query("panel_cirpka_single", site)
    return {
        "Sw": _request_float("Sw", db_query.get("Sw", 10.0)),
        "alpha_Th": _request_float("alpha_Th", db_query.get("alpha_Th", 0.1)),
        "C_A": _request_float("C_A", db_query.get("C_A", 8.0)),
        "C_D": _request_float("C_D", db_query.get("C_D", 5.0)),
        "gamma": _request_float("gamma", db_query.get("gamma", 3.5)),
        "site_id": site.get("id") if site else request.args.get("site_id", type=int),
        "email": _current_email(),
        "run": 1,
    }


def _cirpka_single_field_sources(site):
    db_query = _build_panel_query("panel_cirpka_single", site)
    return {
        "Sw": "Sw" in db_query,
        "alpha_Th": "alpha_Th" in db_query,
        "C_A": "C_A" in db_query,
        "C_D": "C_D" in db_query,
        "gamma": "gamma" in db_query,
    }


def _cirpka_panel_src(params):
    query = {
        "Sw": params["Sw"],
        "alpha_Th": params["alpha_Th"],
        "C_A": params["C_A"],
        "C_D": params["C_D"],
        "gamma": params["gamma"],
        "email": params["email"],
        "output_only": 1,
    }
    if params.get("run"):
        query["run"] = 1
    if params.get("site_id"):
        query["site_id"] = params["site_id"]
    return f"{_panel_base_url()}/panel_cirpka_single_output?{urlencode(query)}"


def _cirpka_single_output(params):
    try:
        lmax = cirpka_lmax(params["Sw"], params["alpha_Th"], params["gamma"], params["C_A"], params["C_D"])
        ld = cirpka_domain_length(lmax)
        plot = comparison_plot(
            "Cirpka et al. (2005)",
            "Cirpka Lmax",
            [params["site_id"] if params.get("site_id") else 1],
            [lmax],
            int(params["site_id"] or 0),
            params["email"],
            "Run Number",
        )
        script, div = components(plot)
        return {
            "ok": True,
            "lmax": lmax,
            "ld": ld,
            "plot_script": script,
            "plot_div": div,
            "error": None,
        }
    except Exception as exc:
        logger.exception("Cirpka single output preparation failed")
        return {
            "ok": False,
            "lmax": None,
            "ld": None,
            "plot_script": "",
            "plot_div": "",
            "error": GENERIC_DATABASE_ERROR_MESSAGE,
        }


# ---------- LANDING (All models page) ----------
@analytical_bp.route("/analytical")
@login_required
def analytical_landing():
    return render_template("analytical_landing.html")


# ---------- LIEDL ----------
@analytical_bp.route("/liedl/single")
@login_required
def liedl_single():
    sites, selected_site = _selected_site()
    input_fields = _input_fields("panel_liedl_single", selected_site)
    return render_template(
        "liedl_single.html",
        panel_src=_panel_src("panel_liedl_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href("panel_liedl_single", input_fields),
    )


@analytical_bp.route("/liedl/single/export")
@login_required
def liedl_single_export():
    m = _request_float("M", 3.5)
    alpha_tv = _request_float("alpha_Tv", 0.001)
    gamma = _request_float("gamma", 3.5)
    c_ea0 = _request_float("C_EA0", 8.0)
    c_ed0 = _request_float("C_ED0", 5.0)
    lmax = liedl_lmax(m, alpha_tv, gamma, c_ea0, c_ed0)
    report = CASTReport("Liedl et al. (2005) — Single Simulation", "Liedl Analytical")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "M", "name": "Aquifer Thickness", "value": m, "unit": "m"},
            {"symbol": "αTv", "name": "Transverse Dispersivity", "value": alpha_tv, "unit": "m"},
            {"symbol": "γ", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
            {"symbol": "CA", "name": "Electron Acceptor", "value": c_ea0, "unit": "mg/L"},
            {"symbol": "CD", "name": "Electron Donor", "value": c_ed0, "unit": "mg/L"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data={"labels": ["Lmax"], "values": [lmax], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — Liedl et al. (2005)"},
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=liedl_single_report.pdf"},
    )


@analytical_bp.route("/liedl/multiple")
@login_required
def liedl_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_liedl_multiple.html",
        panel_src=_panel_src("panel_liedl_multiple", selected_site, output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=_input_fields("panel_liedl_multiple", selected_site),
    )


# ---------- CHU ----------
@analytical_bp.route("/chu/single")
@login_required
def chu_single():
    sites, selected_site = _selected_site()
    input_fields = _input_fields("panel_chu_single", selected_site)
    return render_template(
        "panel_chu_single.html",
        panel_src=_panel_src("panel_chu_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href("panel_chu_single", input_fields),
    )


@analytical_bp.route("/chu/single/export")
@login_required
def chu_single_export():
    w = _request_float("W", 2.0)
    alpha_th = _request_float("alpha_Th", 0.01)
    gamma = _request_float("gamma", 1.5)
    c_ea0 = _request_float("C_EA0", 8.0)
    c_ed0 = _request_float("C_ED0", 5.0)
    epsilon = _request_float("epsilon", 0.0)
    lmax = chu_lmax(w, alpha_th, gamma, c_ea0, c_ed0, epsilon)
    report = CASTReport("Chu et al. — Single Simulation", "Chu Analytical")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "W", "name": "Source Width", "value": w, "unit": "m"},
            {"symbol": "αTh", "name": "Horiz. Trans. Dispersivity", "value": alpha_th, "unit": "m"},
            {"symbol": "γ", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
            {"symbol": "CA", "name": "Electron Acceptor", "value": c_ea0, "unit": "mg/L"},
            {"symbol": "CD", "name": "Electron Donor", "value": c_ed0, "unit": "mg/L"},
            {"symbol": "ε", "name": "Biological Factor", "value": epsilon, "unit": "mg/L"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data={"labels": ["Lmax"], "values": [lmax], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — Chu et al."},
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=chu_single_report.pdf"},
    )


@analytical_bp.route("/chu/multiple")
@login_required
def chu_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_chu_multiple.html",
        panel_src=_panel_src("panel_chu_multiple", selected_site, output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=_input_fields("panel_chu_multiple", selected_site),
    )


# ---------- HAM ----------
@analytical_bp.route("/ham/single")
@login_required
def ham_single():
    sites, selected_site = _selected_site()
    input_fields = _input_fields("panel_ham_single", selected_site)
    return render_template(
        "ham_single.html",
        panel_src=_panel_src("panel_ham_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href("panel_ham_single", input_fields),
    )


@analytical_bp.route("/ham/single/export")
@login_required
def ham_single_export():
    q = _request_float("Q", 5.0)
    alpha_t = _request_float("alpha_T", 0.01)
    gamma = _request_float("gamma", 3.5)
    c_ea0 = _request_float("C_EA0", 8.0)
    c_ed0 = _request_float("C_ED0", 5.0)
    lmax = ham_lmax(q, alpha_t, gamma, c_ea0, c_ed0)
    report = CASTReport("Ham et al. — Single Simulation", "Ham Analytical")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "Q", "name": "Source Flux", "value": q, "unit": "m²/yr"},
            {"symbol": "αT", "name": "Transverse Dispersivity", "value": alpha_t, "unit": "m"},
            {"symbol": "γ", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
            {"symbol": "CA", "name": "Electron Acceptor", "value": c_ea0, "unit": "mg/L"},
            {"symbol": "CD", "name": "Electron Donor", "value": c_ed0, "unit": "mg/L"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data={"labels": ["Lmax"], "values": [lmax], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — Ham et al."},
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=ham_single_report.pdf"},
    )


@analytical_bp.route("/ham/multiple")
@login_required
def ham_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_ham_multiple.html",
        panel_src=_panel_src("panel_ham_multiple", selected_site, output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=_input_fields("panel_ham_multiple", selected_site),
    )


# ---------- BIOSCREEN ----------
@analytical_bp.route("/bioscreen/single")
@login_required
def bioscreen_single():
    sites, selected_site = _selected_site()
    input_fields = _input_fields("panel_bioscreen_single", selected_site)
    return render_template(
        "panel_bioscreen_single.html",
        panel_src=_panel_src("panel_bioscreen_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href("panel_bioscreen_single", input_fields),
    )


@analytical_bp.route("/bioscreen/single/export")
@login_required
def bioscreen_single_export():
    cthres = _request_float("Cthres", 5e-5)
    time_val = _request_int("time", 20)
    h = _request_float("H", 5.0)
    c0 = _request_float("c0", 100.0)
    w = _request_float("W", 10.0)
    v = _request_float("v", 50.0)
    ax = _request_float("ax", 10.0)
    ay = _request_float("ay", 0.5)
    az = _request_float("az", 0.05)
    df = _request_float("Df", 0.0)
    r = _request_float("R", 1.0)
    gamma = _request_float("gamma", 0.0)
    lam = _request_float("lam", 0.1)
    ng = _request_int("ng", 60)
    lmax = float(bio(cthres, time_val, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng))
    report = CASTReport("BIOSCREEN-AT — Single Simulation", "BIOSCREEN Analytical")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "Cthres", "name": "Threshold Concentration", "value": cthres, "unit": "mg/L"},
            {"symbol": "t", "name": "Simulation Time", "value": time_val, "unit": "yr"},
            {"symbol": "H", "name": "Source Thickness", "value": h, "unit": "m"},
            {"symbol": "c0", "name": "Source Concentration", "value": c0, "unit": "mg/L"},
            {"symbol": "W", "name": "Source Width", "value": w, "unit": "m"},
            {"symbol": "v", "name": "Groundwater Velocity", "value": v, "unit": "m/yr"},
            {"symbol": "ax", "name": "Long. Dispersivity", "value": ax, "unit": "m"},
            {"symbol": "ay", "name": "Horiz. Trans. Dispersivity", "value": ay, "unit": "m"},
            {"symbol": "az", "name": "Vert. Trans. Dispersivity", "value": az, "unit": "m"},
            {"symbol": "Df", "name": "Effective Diffusion Coeff.", "value": df, "unit": "m²/yr"},
            {"symbol": "R", "name": "Retardation Factor", "value": r, "unit": "-"},
            {"symbol": "γ", "name": "Source Decay", "value": gamma, "unit": "1/yr"},
            {"symbol": "λ", "name": "First-order Decay", "value": lam, "unit": "1/yr"},
            {"symbol": "ng", "name": "Gauss Points", "value": ng, "unit": "-"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data={"labels": ["Lmax"], "values": [lmax], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — BIOSCREEN-AT"},
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=bioscreen_single_report.pdf"},
    )


@analytical_bp.route("/bioscreen/multiple")
@login_required
def bioscreen_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_bioscreen_multiple.html",
        panel_src=_panel_src("panel_bioscreen_multiple", selected_site, output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=_input_fields("panel_bioscreen_multiple", selected_site),
    )


# ---------- LIEDL 3D ----------
@analytical_bp.route("/liedl3d/single")
@login_required
def liedl3d_single():
    sites, selected_site = _selected_site()
    input_fields = _input_fields("panel_liedl3d_single", selected_site)
    return render_template(
        "panel_liedl3d_single.html",
        panel_src=_panel_src("panel_liedl3d_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href("panel_liedl3d_single", input_fields),
    )


@analytical_bp.route("/liedl3d/single/export")
@login_required
def liedl3d_single_export():
    m = _request_float("M", 10.0)
    alpha_th = _request_float("alpha_Th", 0.01)
    alpha_tv = _request_float("alpha_Tv", 0.01)
    w = _request_float("W", 7.0)
    cthres = _request_float("Cthres", 0.5)
    c_ea0 = _request_float("C_EA0", 8.0)
    c_ed0 = _request_float("C_ED0", 5.0)
    gamma = _request_float("gamma", 3.0)
    lmax = liedl3d_lmax(m, alpha_th, alpha_tv, w, cthres, c_ea0, c_ed0, gamma)
    report = CASTReport("Liedl 3D — Single Simulation", "Liedl 3D Analytical")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "M", "name": "Source Thickness", "value": m, "unit": "m"},
            {"symbol": "αTh", "name": "Horiz. Trans. Dispersivity", "value": alpha_th, "unit": "m"},
            {"symbol": "αTv", "name": "Vert. Trans. Dispersivity", "value": alpha_tv, "unit": "m"},
            {"symbol": "W", "name": "Source Width", "value": w, "unit": "m"},
            {"symbol": "Cthres", "name": "Threshold Concentration", "value": cthres, "unit": "mg/L"},
            {"symbol": "CA", "name": "Electron Acceptor", "value": c_ea0, "unit": "mg/L"},
            {"symbol": "CD", "name": "Electron Donor", "value": c_ed0, "unit": "mg/L"},
            {"symbol": "γ", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data={"labels": ["Lmax"], "values": [lmax], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — Liedl 3D"},
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=liedl3d_single_report.pdf"},
    )


@analytical_bp.route("/liedl3d/multiple")
@login_required
def liedl3d_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_liedl3d_multiple.html",
        panel_src=_panel_src("panel_liedl3d_multiple", selected_site, output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=_input_fields("panel_liedl3d_multiple", selected_site),
    )


# ---------- CIRPKA ----------
@analytical_bp.route("/cirpka/single")
@login_required
def cirpka_single():
    sites, selected_site = _selected_site()
    params = _cirpka_single_params(selected_site)
    input_fields = _input_fields("panel_cirpka_single", selected_site)
    output = _cirpka_single_output(params)
    export_query = {
        key: params[key]
        for key in ("Sw", "alpha_Th", "C_A", "C_D", "gamma")
    }
    return render_template(
        "panel_cirpka_single.html",
        panel_src=_cirpka_panel_src(params),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        params=params,
        field_sources=_cirpka_single_field_sources(selected_site),
        input_fields=input_fields,
        output=output,
        export_href=f"{request.path}/export?{urlencode(export_query)}",
    )


@analytical_bp.route("/cirpka/single/export")
@login_required
def cirpka_single_export():
    sw = _request_float("Sw", 10.0)
    alpha_th = _request_float("alpha_Th", 0.1)
    ca = _request_float("C_A", 8.0)
    cd = _request_float("C_D", 5.0)
    gamma = _request_float("gamma", 3.5)
    lmax = cirpka_lmax(sw, alpha_th, gamma, ca, cd)
    ld = cirpka_domain_length(lmax)

    report = CASTReport("Cirpka et al. (2005) - Single Simulation", "Cirpka Analytical")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "Sw", "name": "Source Width", "value": sw, "unit": "m"},
            {"symbol": "alpha Th", "name": "Horizontal Transverse Dispersivity", "value": alpha_th, "unit": "m"},
            {"symbol": "CA", "name": "Electron Acceptor", "value": ca, "unit": "mg/L"},
            {"symbol": "CD", "name": "Electron Donor", "value": cd, "unit": "mg/L"},
            {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
        ],
        outputs=[
            {"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"},
            {"label": "Domain Length LD", "value": f"{ld:.2f}", "unit": "m"},
        ],
        plot_data={"labels": ["Lmax", "Domain LD"], "values": [lmax, ld], "ylabel": "Length (m)", "title": "Cirpka Result"},
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=cirpka_single_report.pdf"},
    )


@analytical_bp.route("/cirpka/multiple")
@login_required
def cirpka_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_cirpka_multiple.html",
        panel_src=_panel_src("panel_cirpka_multiple", selected_site, output_only=False),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=_input_fields("panel_cirpka_multiple", selected_site),
    )
