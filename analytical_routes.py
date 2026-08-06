# analytical_routes.py
import logging
from math import isfinite
from urllib.parse import urlencode

from bokeh.embed import components
from flask import Blueprint, Response, render_template, request

from analytical_models import (
    chu_lmax,
    cirpka_domain_length,
    cirpka_lmax,
    ham_lmax,
    liedl_lmax,
    liedl3d_lmax,
)
from bioscreen_model import bio
from data_queries import get_user_sites, get_user_sites_rows
from model_site_validation import filter_valid_sites_for_model
from route_guards import compare_site_ids, guard_model_errors, request_finite_float, request_finite_int
from panel_analytical_common import comparison_plot
from param_meta import attach_meta
from pdf_report import CASTReport
from security import GENERIC_DATABASE_ERROR_MESSAGE, current_email
from settings import PANEL_PUBLIC_BASE
from symbol_registry import db_to_model

analytical_bp = Blueprint("analytical_bp", __name__)
logger = logging.getLogger(__name__)

ANALYTICAL_INPUT_SPECS = {
    "panel_liedl_single": [
        ("M", "Aquifer Thickness [m]", 2.0, "0.1", "0.000001"),
        ("alpha_Tv", "Transverse Dispersivity [m]", 0.001, "0.0001", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 3.5, "0.1", None),
        ("C_EA0", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
    ],
    "panel_liedl_multiple": [
        ("M", "Aquifer Thickness [m]", 2.0, "0.1", "0.000001"),
        ("alpha_Tv", "Transverse Dispersivity [m]", 0.001, "0.0001", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 3.5, "0.1", None),
        ("C_EA0", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
    ],
    "panel_liedl3d_single": [
        ("M", "Source Thickness [m]", 10.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity [m]", 0.01, "0.001", "0.000001"),
        ("alpha_Tv", "Vertical Transverse Dispersivity [m]", 0.01, "0.001", "0.000001"),
        ("W", "Source Width [m]", 7.0, "0.1", "0.000001"),
        ("Cthres", "Threshold Concentration [mg/L]", 0.5, "0.01", "0.000001"),
        ("C_EA0", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 3.0, "0.1", None),
    ],
    "panel_liedl3d_multiple": [
        ("M", "Source Thickness [m]", 10.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity [m]", 0.01, "0.001", "0.000001"),
        ("alpha_Tv", "Vertical Transverse Dispersivity [m]", 0.01, "0.001", "0.000001"),
        ("W", "Source Width [m]", 7.0, "0.1", "0.000001"),
        ("Cthres", "Threshold Concentration [mg/L]", 0.5, "0.01", "0.000001"),
        ("C_EA0", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 3.0, "0.1", None),
    ],
    "panel_chu_single": [
        ("W", "Source Width [m]", 2.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity [m]", 0.01, "0.001", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 1.5, "0.1", None),
        ("C_EA0", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
        ("epsilon", "Biological Factor [mg/L]", 0.0, "0.01", None),
    ],
    "panel_chu_multiple": [
        ("W", "Source Width [m]", 2.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity [m]", 0.01, "0.001", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 1.5, "0.1", None),
        ("C_EA0", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
        ("epsilon", "Biological Factor [mg/L]", 0.0, "0.01", None),
    ],
    "panel_ham_single": [
        ("Q", "Source Flux [m2/yr]", 5.0, "0.1", "0.000001"),
        ("alpha_T", "Transverse Dispersivity [m]", 0.01, "0.001", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 3.5, "0.1", None),
        ("C_EA0", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
    ],
    "panel_ham_multiple": [
        ("Q", "Source Flux [m2/yr]", 5.0, "0.1", "0.000001"),
        ("alpha_T", "Transverse Dispersivity [m]", 0.01, "0.001", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 3.5, "0.1", None),
        ("C_EA0", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_ED0", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
    ],
    "panel_bioscreen_single": [
        ("Cthres", "Threshold Concentration [mg/L]", 5e-5, "0.00001", "0"),
        ("time", "Simulation Time [yr]", 20, "1", "1"),
        ("H", "Source Thickness [m]", 6.1, "0.1", "0.000001"),
        ("c0", "Source Concentration [mg/L]", 106.35, "1", "0.000001"),
        ("W", "Source Width [m]", 20.0, "0.1", "0.000001"),
        ("v", "Groundwater Velocity [m/yr]", 292.0, "1", "0.000001"),
        ("ax", "Longitudinal Dispersivity [m]", 10.7, "0.5", "0.000001"),
        ("ay", "Horizontal Transverse Dispersivity [m]", 1.1, "0.1", "0.000001"),
        ("az", "Vertical Transverse Dispersivity [m]", 0.11, "0.01", "0.000001"),
        ("Df", "Effective Diffusion Coefficient [m2/yr]", 0.0, "0.001", "0"),
        ("R", "Retardation Factor [-]", 1.0, "0.1", "0.01"),
        ("gamma", "Source Decay [1/yr]", 0.0, "0.01", "0"),
        ("lam", "First-order Decay [1/yr]", 0.445, "0.01", "0"),
        ("ng", "Gauss Points [-]", 60, "1", "4"),
    ],
    "panel_bioscreen_multiple": [
        ("Cthres", "Threshold Concentration [mg/L]", 5e-5, "0.00001", "0"),
        ("time", "Simulation Time [yr]", 20, "1", "1"),
        ("H", "Source Thickness [m]", 6.1, "0.1", "0.000001"),
        ("c0", "Source Concentration [mg/L]", 106.35, "1", "0.000001"),
        ("W", "Source Width [m]", 20.0, "0.1", "0.000001"),
        ("v", "Groundwater Velocity [m/yr]", 292.0, "1", "0.000001"),
        ("ax", "Longitudinal Dispersivity [m]", 10.7, "0.5", "0.000001"),
        ("ay", "Horizontal Transverse Dispersivity [m]", 1.1, "0.1", "0.000001"),
        ("az", "Vertical Transverse Dispersivity [m]", 0.11, "0.01", "0.000001"),
        ("Df", "Effective Diffusion Coefficient [m2/yr]", 0.0, "0.001", "0"),
        ("R", "Retardation Factor [-]", 1.0, "0.1", "0.01"),
        ("gamma", "Source Decay [1/yr]", 0.0, "0.01", "0"),
        ("lam", "First-order Decay [1/yr]", 0.445, "0.01", "0"),
        ("ng", "Gauss Points [-]", 60, "1", "4"),
    ],
    "panel_cirpka_single": [
        ("Sw", "Source Width [m]", 10.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity [m]", 0.1, "0.001", "0.000001"),
        ("C_A", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_D", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 3.5, "0.1", None),
    ],
    "panel_cirpka_multiple": [
        ("Sw", "Source Width [m]", 10.0, "0.1", "0.000001"),
        ("alpha_Th", "Horizontal Transverse Dispersivity [m]", 0.1, "0.001", "0.000001"),
        ("C_A", "Electron Acceptor [mg/L]", 8.0, "0.1", "0.000001"),
        ("C_D", "Electron Donor [mg/L]", 5.0, "0.1", "0.000001"),
        ("gamma", "Stoichiometric Ratio [-]", 3.5, "0.1", None),
    ],
}


def _current_email():
    return current_email()


def _panel_base_url():
    return PANEL_PUBLIC_BASE


def _default_query(path):
    return {
        name: default
        for name, _label, default, _step, _minimum in ANALYTICAL_INPUT_SPECS.get(path, [])
    }


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


def _render_multiple(model):
    """Every multiple page is the same page: pick sites, run the model per site.

    The panel reads the ticked sites from its own query string, so they are
    appended after _panel_src (which only carries single-valued arguments).
    """
    sites, selected_site = _selected_site(model)
    ticked = compare_site_ids(sites)
    panel_path = f"panel_{model}_multiple"
    panel_src = _panel_src(panel_path, selected_site, output_only=False)
    panel_src += "&" + urlencode({"compare_sites": ",".join(str(i) for i in ticked)})
    return render_template(
        f"{panel_path}.html",
        panel_src=panel_src,
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        compare_site_ids=ticked,
        input_fields=_input_fields(panel_path, selected_site),
    )


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
        # compare_sites is multi-valued; the pages that use it pass it explicitly.
        if key not in {"site_id", "output_only", "compare_sites"} and value != "":
            query[key] = value
    query["email"] = _current_email()
    query["run"] = 1
    if output_only:
        query["output_only"] = 1
    return f"{_panel_base_url()}/{path}?{urlencode(query)}"


_request_float = request_finite_float
_request_int = request_finite_int


def _input_fields(path, site):
    db_query = _build_panel_query(path, site)
    fields = []
    for name, label, default, step, minimum in ANALYTICAL_INPUT_SPECS.get(path, []):
        fields.append(attach_meta({
            "name": name,
            "label": label,
            "value": _request_float(name, db_query.get(name, default)),
            "step": step,
            "min": minimum,
            "from_db": name in db_query,
        }, context=path))
    return fields


def _export_href(path, input_fields, selected_site_id=None):
    query = {f["name"]: f["value"] for f in input_fields}
    if selected_site_id:
        query["site_id"] = selected_site_id
    return f"{request.path}/export?{urlencode(query)}"



def _comparison_plot_data(title, manual_label, manual_y, selected_site_id, email, manual_axis_label):
    # Mirrors panel_analytical_common.comparison_plot_data so the exported report
    # shows the same chart as the page: database points always, the model result
    # parked past the last site when the run is not tied to one.
    field_x, field_y = [], []
    # The axis counts sites by position, not by primary key, so capture where the
    # selected site sits while walking the rows - passing its id through put the
    # model point thousands of ticks off the end of the chart.
    position = None
    try:
        for i, row in enumerate(get_user_sites(email), start=1):
            if selected_site_id > 0 and row[0] == selected_site_id:
                position = i
            try:
                plume = float(row[4])
            except (TypeError, ValueError):
                continue
            field_x.append(i)
            field_y.append(plume)
    except Exception:
        logger.exception("Database comparison points could not be loaded for PDF report")
        field_x, field_y = [], []

    if position is not None:
        manual_x = [position]
    elif selected_site_id > 0:
        manual_x = [selected_site_id]
    elif field_x:
        manual_x = [max(field_x) + 1]
    else:
        manual_x = [1]

    return {
        "type": "comparison_scatter",
        "title": title,
        "x_label": "Site Number" if field_x else manual_axis_label,
        "y_label": "Plume Length (m)",
        "field_label": "Database plume length",
        "field_x": field_x,
        "field_y": field_y,
        "manual_label": manual_label,
        "manual_x": manual_x,
        "manual_y": [manual_y],
        "caption": "Database plume lengths compared with the model result.",
    }

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
            "Cirpka et al. (2006)",
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
def analytical_landing():
    return render_template("analytical_landing.html")


# ---------- LIEDL ----------
@analytical_bp.route("/liedl/single")
def liedl_single():
    sites, selected_site = _selected_site("liedl")
    input_fields = _input_fields("panel_liedl_single", selected_site)
    return render_template(
        "liedl_single.html",
        panel_src=_panel_src("panel_liedl_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href("panel_liedl_single", input_fields, selected_site.get("id") if selected_site else None),
    )


@analytical_bp.route("/liedl/single/export")
@guard_model_errors
def liedl_single_export():
    m = _request_float("M", 2.0)
    alpha_tv = _request_float("alpha_Tv", 0.001)
    gamma = _request_float("gamma", 3.5)
    c_ea0 = _request_float("C_EA0", 8.0)
    c_ed0 = _request_float("C_ED0", 5.0)
    lmax = liedl_lmax(m, alpha_tv, gamma, c_ea0, c_ed0)
    if not isfinite(lmax):
        raise ValueError("Liedl result must be finite.")
    report = CASTReport("Liedl et al. (2005) — Single Simulation", "Liedl et al. (2005)")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "S_T", "name": "Source Thickness", "value": m, "unit": "m"},
            {"symbol": "alpha_Tv", "name": "Vertical Transverse Dispersivity", "value": alpha_tv, "unit": "m"},
            {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
            {"symbol": "C_A0", "name": "Acceptor Concentration at Source", "value": c_ea0, "unit": "mg/L"},
            {"symbol": "C_D0", "name": "Donor Concentration at Source", "value": c_ed0, "unit": "mg/L"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data=_comparison_plot_data(
            "Liedl et al. (2005)",
            "Liedl model plume length",
            lmax,
            _request_int("site_id", 0),
            _current_email(),
            "Run Number",
        ),
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=liedl_single_report.pdf"},
    )


@analytical_bp.route("/liedl/multiple")
def liedl_multiple():
    return _render_multiple("liedl")


# ---------- CHU ----------
@analytical_bp.route("/chu/single")
def chu_single():
    sites, selected_site = _selected_site("chu")
    input_fields = _input_fields("panel_chu_single", selected_site)
    return render_template(
        "panel_chu_single.html",
        panel_src=_panel_src("panel_chu_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href("panel_chu_single", input_fields, selected_site.get("id") if selected_site else None),
    )


@analytical_bp.route("/chu/single/export")
@guard_model_errors
def chu_single_export():
    w = _request_float("W", 2.0)
    alpha_th = _request_float("alpha_Th", 0.01)
    gamma = _request_float("gamma", 1.5)
    c_ea0 = _request_float("C_EA0", 8.0)
    c_ed0 = _request_float("C_ED0", 5.0)
    epsilon = _request_float("epsilon", 0.0)
    lmax = chu_lmax(w, alpha_th, gamma, c_ea0, c_ed0, epsilon)
    report = CASTReport("Chu et al. (2005) — Single Simulation", "Chu et al. (2005)")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "S_W", "name": "Source Width", "value": w, "unit": "m"},
            {"symbol": "alpha_Th", "name": "Horizontal Transverse Dispersivity", "value": alpha_th, "unit": "m"},
            {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
            {"symbol": "C_A0", "name": "Acceptor Concentration at Source", "value": c_ea0, "unit": "mg/L"},
            {"symbol": "C_D0", "name": "Donor Concentration at Source", "value": c_ed0, "unit": "mg/L"},
            {"symbol": "epsilon", "name": "Biological Concentration Factor", "value": epsilon, "unit": "mg/L"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data=_comparison_plot_data(
            "Chu et al. (2005)", "Chu model plume length", lmax,
            _request_int("site_id", 0), _current_email(), "Run Number",
        ),
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=chu_single_report.pdf"},
    )


@analytical_bp.route("/chu/multiple")
def chu_multiple():
    return _render_multiple("chu")


# ---------- HAM ----------
@analytical_bp.route("/ham/single")
def ham_single():
    sites, selected_site = _selected_site("ham")
    input_fields = _input_fields("panel_ham_single", selected_site)
    return render_template(
        "ham_single.html",
        panel_src=_panel_src("panel_ham_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href("panel_ham_single", input_fields, selected_site.get("id") if selected_site else None),
    )


@analytical_bp.route("/ham/single/export")
@guard_model_errors
def ham_single_export():
    q = _request_float("Q", 5.0)
    alpha_t = _request_float("alpha_T", 0.01)
    gamma = _request_float("gamma", 3.5)
    c_ea0 = _request_float("C_EA0", 8.0)
    c_ed0 = _request_float("C_ED0", 5.0)
    lmax = ham_lmax(q, alpha_t, gamma, c_ea0, c_ed0)
    report = CASTReport("Ham et al. (2004) — Single Simulation", "Ham et al. (2004)")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "q", "name": "Source Flux", "value": q, "unit": "m²/yr"},
            {"symbol": "alpha_Th", "name": "Horizontal Transverse Dispersivity", "value": alpha_t, "unit": "m"},
            {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
            {"symbol": "C_A0", "name": "Acceptor Concentration at Source", "value": c_ea0, "unit": "mg/L"},
            {"symbol": "C_D0", "name": "Donor Concentration at Source", "value": c_ed0, "unit": "mg/L"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data=_comparison_plot_data(
            "Ham et al. (2004)", "Ham model plume length", lmax,
            _request_int("site_id", 0), _current_email(), "Run Number",
        ),
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=ham_single_report.pdf"},
    )


@analytical_bp.route("/ham/multiple")
def ham_multiple():
    return _render_multiple("ham")


# ---------- BIOSCREEN ----------
@analytical_bp.route("/bioscreen/single")
def bioscreen_single():
    sites, selected_site = _selected_site("bioscreen")
    input_fields = _input_fields("panel_bioscreen_single", selected_site)
    return render_template(
        "panel_bioscreen_single.html",
        panel_src=_panel_src("panel_bioscreen_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href("panel_bioscreen_single", input_fields, selected_site.get("id") if selected_site else None),
    )


@analytical_bp.route("/bioscreen/single/export")
@guard_model_errors
def bioscreen_single_export():
    cthres = _request_float("Cthres", 5e-5)
    time_val = _request_int("time", 20)
    h = _request_float("H", 6.1)
    c0 = _request_float("c0", 106.35)
    w = _request_float("W", 20.0)
    v = _request_float("v", 292.0)
    ax = _request_float("ax", 10.7)
    ay = _request_float("ay", 1.1)
    az = _request_float("az", 0.11)
    df = _request_float("Df", 0.0)
    r = _request_float("R", 1.0)
    gamma = _request_float("gamma", 0.0)
    lam = _request_float("lam", 0.445)
    ng = _request_int("ng", 60)
    lmax = float(bio(cthres, time_val, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng))
    report = CASTReport("BIOSCREEN-AT 3D — Single Simulation", "BIOSCREEN-AT 3D")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "C_thres", "name": "Threshold Contaminant Concentration", "value": cthres, "unit": "mg/L"},
            {"symbol": "t", "name": "Simulation Time", "value": time_val, "unit": "yr"},
            {"symbol": "S_T", "name": "Source Thickness", "value": h, "unit": "m"},
            {"symbol": "C_D0", "name": "Contamination Concentration", "value": c0, "unit": "mg/L"},
            {"symbol": "S_W", "name": "Source Width", "value": w, "unit": "m"},
            {"symbol": "v", "name": "Groundwater Seepage Velocity", "value": v, "unit": "m/yr"},
            {"symbol": "alpha_L", "name": "Longitudinal Dispersivity", "value": ax, "unit": "m"},
            {"symbol": "alpha_Th", "name": "Horizontal Transverse Dispersivity", "value": ay, "unit": "m"},
            {"symbol": "alpha_Tv", "name": "Vertical Transverse Dispersivity", "value": az, "unit": "m"},
            {"symbol": "D_f", "name": "Diffusion Coefficient", "value": df, "unit": "m²/yr"},
            {"symbol": "R", "name": "Retardation Factor", "value": r, "unit": "-"},
            {"symbol": "Gamma", "name": "Source Decay Coefficient", "value": gamma, "unit": "1/yr"},
            {"symbol": "lambda_e", "name": "First-order Decay Coefficient", "value": lam, "unit": "1/yr"},
            {"symbol": "n_g", "name": "Number of Gauss Points", "value": ng, "unit": "-"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data=_comparison_plot_data(
            "BIOSCREEN-AT 3D", "BIOSCREEN plume length", lmax,
            _request_int("site_id", 0), _current_email(), "Run Number",
        ),
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=bioscreen_single_report.pdf"},
    )


@analytical_bp.route("/bioscreen/multiple")
def bioscreen_multiple():
    return _render_multiple("bioscreen")


# ---------- LIEDL 3D ----------
@analytical_bp.route("/liedl3d/single")
def liedl3d_single():
    sites, selected_site = _selected_site("liedl3d")
    input_fields = _input_fields("panel_liedl3d_single", selected_site)
    return render_template(
        "panel_liedl3d_single.html",
        panel_src=_panel_src("panel_liedl3d_single", selected_site, auto_run=True),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
        input_fields=input_fields,
        export_href=_export_href("panel_liedl3d_single", input_fields, selected_site.get("id") if selected_site else None),
    )


@analytical_bp.route("/liedl3d/single/export")
@guard_model_errors
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
    report = CASTReport("Liedl 3D (2011) — Single Simulation", "Liedl 3D (2011)")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "S_T", "name": "Source Thickness", "value": m, "unit": "m"},
            {"symbol": "alpha_Th", "name": "Horizontal Transverse Dispersivity", "value": alpha_th, "unit": "m"},
            {"symbol": "alpha_Tv", "name": "Vertical Transverse Dispersivity", "value": alpha_tv, "unit": "m"},
            {"symbol": "S_W", "name": "Source Width", "value": w, "unit": "m"},
            {"symbol": "C_thres", "name": "Threshold Donor Concentration", "value": cthres, "unit": "mg/L"},
            {"symbol": "C_A0", "name": "Acceptor Concentration at Source", "value": c_ea0, "unit": "mg/L"},
            {"symbol": "C_D0", "name": "Donor Concentration at Source", "value": c_ed0, "unit": "mg/L"},
            {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data=_comparison_plot_data(
            "Liedl 3D (2011)", "Liedl 3D model plume length", lmax,
            _request_int("site_id", 0), _current_email(), "Run Number",
        ),
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=liedl3d_single_report.pdf"},
    )


@analytical_bp.route("/liedl3d/multiple")
def liedl3d_multiple():
    return _render_multiple("liedl3d")


# ---------- CIRPKA ----------
@analytical_bp.route("/cirpka/single")
def cirpka_single():
    sites, selected_site = _selected_site("cirpka")
    params = _cirpka_single_params(selected_site)
    input_fields = _input_fields("panel_cirpka_single", selected_site)
    output = _cirpka_single_output(params)
    export_query = {
        key: params[key]
        for key in ("Sw", "alpha_Th", "C_A", "C_D", "gamma")
    }
    if params.get("site_id"):
        export_query["site_id"] = params["site_id"]
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
@guard_model_errors
def cirpka_single_export():
    sw = _request_float("Sw", 10.0)
    alpha_th = _request_float("alpha_Th", 0.1)
    ca = _request_float("C_A", 8.0)
    cd = _request_float("C_D", 5.0)
    gamma = _request_float("gamma", 3.5)
    lmax = cirpka_lmax(sw, alpha_th, gamma, ca, cd)
    ld = cirpka_domain_length(lmax)

    report = CASTReport("Cirpka et al. (2006) - Single Simulation", "Cirpka et al. (2006)")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "S_W", "name": "Source Width", "value": sw, "unit": "m"},
            {"symbol": "alpha_Th", "name": "Horizontal Transverse Dispersivity", "value": alpha_th, "unit": "m"},
            {"symbol": "C_A0", "name": "Acceptor Concentration at Source", "value": ca, "unit": "mg/L"},
            {"symbol": "C_D0", "name": "Donor Concentration at Source", "value": cd, "unit": "mg/L"},
            {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma, "unit": "-"},
        ],
        outputs=[
            {"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"},
            {"label": "Domain Length LD", "value": f"{ld:.2f}", "unit": "m"},
        ],
        plot_data=_comparison_plot_data(
            "Cirpka et al. (2006)", "Cirpka model plume length", lmax,
            _request_int("site_id", 0), _current_email(), "Run Number",
        ),
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=cirpka_single_report.pdf"},
    )


@analytical_bp.route("/cirpka/multiple")
def cirpka_multiple():
    return _render_multiple("cirpka")
