from urllib.parse import urlencode

from flask import Blueprint, render_template, request, session

from data_queries import get_user_sites_rows
from settings import PANEL_BASE_URL

numerical_bp = Blueprint("numerical_bp", __name__)

PANEL_BASE = PANEL_BASE_URL


def _current_email():
    return session.get("email") or "demo@example.com"


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


def _build_panel_query(site):
    if not site:
        return {}

    aquifer = _to_float(site.get("aquifer_thickness"))
    plume_length = _to_float(site.get("plume_length"))
    plume_width = _to_float(site.get("plume_width"))
    conductivity = _to_float(site.get("hydraulic_conductivity"))
    donor = _to_float(site.get("electron_donor"))
    o2 = _to_float(site.get("electron_acceptor_o2"))

    query = {"email": _current_email()}
    if site.get("id") is not None:
        query["site_id"] = int(site.get("id"))
    if plume_length is not None:
        query["Lx"] = max(plume_length * 1.5, 40.0)
    if plume_width is not None:
        query["Ly"] = max(plume_width * 2.0, 10.0)
    if aquifer is not None:
        query["nrow"] = max(int(round(aquifer * 5)), 10)
    if conductivity is not None:
        query["hk"] = max(conductivity, 0.01)
    if donor is not None:
        query["Cd"] = donor
    if o2 is not None:
        query["Ca"] = o2
    query.setdefault("ncol", 60)
    query.setdefault("prsity", 0.3)
    query.setdefault("al", 5.0)
    query.setdefault("av", 0.5)
    query.setdefault("gamma", 3.5)
    query.setdefault("h1", 10.0)
    query.setdefault("h2", 9.0)
    return query


def _panel_src(path, site):
    query = _build_panel_query(site)
    if not query:
        return f"{PANEL_BASE}/{path}"
    return f"{PANEL_BASE}/{path}?{urlencode(query)}"


@numerical_bp.route("/numerical")
def numerical_landing():
    return render_template("numerical_landing.html")


@numerical_bp.route("/numerical/single")
def numerical_single():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_numerical_single.html",
        panel_src=_panel_src("panel_numerical_single", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )


@numerical_bp.route("/numerical/multiple")
def numerical_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_numerical_multiple.html",
        panel_src=_panel_src("panel_numerical_multiple", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )
