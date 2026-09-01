# empirical_routes.py
from urllib.parse import urlencode

from flask import Blueprint, Response, render_template, request

from data_queries import get_user_sites_rows
from model_site_validation import filter_valid_sites_for_model
from route_guards import compare_site_ids, guard_model_errors, request_finite_float
from empirical_models import birla_lmax, maier_lmax
from panel_empirical_common import comparison_plot_data
from param_meta import attach_meta
from pdf_report import CASTReport
from security import current_email
from settings import PANEL_PUBLIC_BASE
from symbol_registry import db_to_model

empirical_bp = Blueprint("empirical_bp", __name__)

EMPIRICAL_INPUT_SPECS = {
    "panel_maier_single": [
        ("M", "Aquifer Thickness [m]", 5.0, "0.1", "0.000001"),
        ("tv", "Vertical Transverse Dispersivity [m]", 0.01, "0.001", "0.000001"),
        ("g", "Stoichiometry Coefficient [-]", 3.5, "0.1", None),
        ("Ca", "Contaminant Concentration [mg/L]", 8.0, "0.5", "0.000001"),
        ("Cd", "Reactant Concentration [mg/L]", 5.0, "0.5", "0.000001"),
    ],
    "panel_maier_multiple": [
        ("M", "Aquifer Thickness [m]", 5.0, "0.1", "0.000001"),
        ("tv", "Vertical Transverse Dispersivity [m]", 0.01, "0.001", "0.000001"),
        ("g", "Stoichiometry Coefficient [-]", 3.5, "0.1", None),
        ("Ca", "Contaminant Concentration [mg/L]", 8.0, "0.5", "0.000001"),
        ("Cd", "Reactant Concentration [mg/L]", 5.0, "0.5", "0.000001"),
    ],
    "panel_birla_single": [
        ("M", "Aquifer Thickness [m]", 2.0, "0.1", "0.000001"),
        ("tv", "Vertical Transverse Dispersivity [m]", 0.001, "0.0005", "0.000001"),
        ("g", "Stoichiometry Coefficient [-]", 3.5, "0.1", None),
        ("Ca", "Contaminant Concentration [mg/L]", 8.0, "0.5", "0.000001"),
        ("Cd", "Reactant Concentration [mg/L]", 5.0, "0.5", "0.000001"),
        ("R", "Recharge Rate [m/yr]", 1.0, "0.1", "0.000001"),
    ],
    "panel_birla_multiple": [
        ("M", "Aquifer Thickness [m]", 2.0, "0.1", "0.000001"),
        ("tv", "Vertical Transverse Dispersivity [m]", 0.001, "0.0005", "0.000001"),
        ("g", "Stoichiometry Coefficient [-]", 3.5, "0.1", None),
        ("Ca", "Contaminant Concentration [mg/L]", 8.0, "0.5", "0.000001"),
        ("Cd", "Reactant Concentration [mg/L]", 5.0, "0.5", "0.000001"),
        ("R", "Recharge Rate [m/yr]", 1.0, "0.1", "0.000001"),
    ],
}


def _render_multiple(model):
    """Multiple page: one full-width Panel frame carrying the site picker, the
    graph, the toolbar and the scenario table, with the report card under it.

    The panel reads the ticked sites from its own query string, so they are
    appended after _panel_src (which only carries single-valued arguments).
    """
    # Imported here rather than at module scope - see analytical_routes.
    from panel_model_scenarios import scenario_field_specs

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
        show_site_loader=False,
        # The page keeps only the Add-row dialog, which needs the field list.
        scenario_fields=scenario_field_specs(model),
        panel_min_height=800,
    )


def _current_email():
    return current_email()


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


def _model_from_path(path):
    return "maier" if "maier" in path else "birla"


# Canonical symbol -> empirical panel input name. db_to_model only returns the
# symbols each model consumes, so unrelated symbols are simply absent.
_EMPIRICAL_SYMBOL_TO_PARAM = {
    "M": "M",
    "alpha_Tv": "tv",
    "gamma": "g",
    "C_A": "Ca",
    "C_D": "Cd",
    "R": "R",
}


def _input_fields(path, site):
    db_query = _build_panel_query(site, _model_from_path(path))
    fields = []
    for name, label, default, step, minimum in EMPIRICAL_INPUT_SPECS.get(path, []):
        fields.append(attach_meta({
            "name": name,
            "label": label,
            "value": _request_float(name, db_query.get(name, default)),
            "step": step,
            "min": minimum,
            "from_db": name in db_query,
        }, context=path))
    return fields


def _export_href(input_fields):
    query = {f["name"]: f["value"] for f in input_fields}
    site_id = request.args.get("site_id", type=int)
    if site_id:
        query["site_id"] = site_id
    return f"{request.path}/export?{urlencode(query)}"


def _build_panel_query(site, model_name):
    if not site:
        return {}
    query = {}
    for symbol, value in db_to_model(site, model_name).items():
        param = _EMPIRICAL_SYMBOL_TO_PARAM.get(symbol)
        if param is None:
            continue
        number = _to_float(value)
        if number is not None:
            query[param] = number
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
    query.update(_build_panel_query(site, _model_from_path(path)))
    for key, value in request.args.items():
        # compare_sites is multi-valued; _render_multiple passes it explicitly.
        if key not in {"site_id", "output_only", "compare_sites"} and value != "":
            query[key] = value
    query["email"] = _current_email()
    query["run"] = 1
    if output_only:
        query["output_only"] = 1
    return f"{_panel_base_url()}/{path}?{urlencode(query)}"


@empirical_bp.route("/empirical")
def empirical_landing():
    return render_template("empirical_landing.html")


@empirical_bp.route("/empirical/maier/single")
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
@guard_model_errors
def maier_single_export():
    m = _request_float("M", 5.0)
    tv = _request_float("tv", 0.01)
    g = _request_float("g", 3.5)
    ca = _request_float("Ca", 8.0)
    cd = _request_float("Cd", 5.0)
    lmax = maier_lmax(m, tv, g, ca, cd)
    selected_site_id = request.args.get("site_id", default=0, type=int)
    report = CASTReport("Maier & Grathwohl (2006) — Single Simulation", "Maier & Grathwohl (2006)")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "T_s", "name": "Source Thickness", "value": m, "unit": "m"},
            {"symbol": "alpha_Tv", "name": "Vertical Transverse Dispersivity", "value": tv, "unit": "m"},
            {"symbol": "gamma", "name": "Stoichiometry Ratio", "value": g, "unit": "-"},
            {"symbol": "C_A0", "name": "Acceptor Concentration at Source", "value": ca, "unit": "mg/L"},
            {"symbol": "C_D0", "name": "Donor Concentration at Source", "value": cd, "unit": "mg/L"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data=comparison_plot_data(
            "Maier & Grathwohl (2006)", "Maier model plume length",
            [selected_site_id or 1], [lmax],
            selected_site_id, _current_email(), "Run Number",
        ),
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=maier_single_report.pdf"},
    )


@empirical_bp.route("/empirical/maier/multiple")
def maier_multiple():
    return _render_multiple("maier")


@empirical_bp.route("/empirical/birla/single")
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
@guard_model_errors
def birla_single_export():
    m = _request_float("M", 2.0)
    tv = _request_float("tv", 0.001)
    g = _request_float("g", 3.5)
    ca = _request_float("Ca", 8.0)
    cd = _request_float("Cd", 5.0)
    r = _request_float("R", 1.0)
    lmax = birla_lmax(m, tv, g, ca, cd, r)
    selected_site_id = request.args.get("site_id", default=0, type=int)
    report = CASTReport("Birla et al. (2020) — Single Simulation", "Birla et al. (2020)")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "T_s", "name": "Source Thickness", "value": m, "unit": "m"},
            {"symbol": "alpha_Tv", "name": "Vertical Transverse Dispersivity", "value": tv, "unit": "m"},
            {"symbol": "R_c", "name": "Recharge Rate", "value": r, "unit": "m/yr"},
            {"symbol": "gamma", "name": "Stoichiometry Ratio", "value": g, "unit": "-"},
            {"symbol": "C_A0", "name": "Acceptor Concentration at Source", "value": ca, "unit": "mg/L"},
            {"symbol": "C_D0", "name": "Donor Concentration at Source", "value": cd, "unit": "mg/L"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": f"{lmax:.2f}", "unit": "m"}],
        plot_data=comparison_plot_data(
            "Birla et al. (2020)", "Birla model plume length",
            [selected_site_id or 1], [lmax],
            selected_site_id, _current_email(), "Run Number",
        ),
    )
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": "attachment; filename=birla_single_report.pdf"},
    )


@empirical_bp.route("/empirical/birla/multiple")
def birla_multiple():
    return _render_multiple("birla")
