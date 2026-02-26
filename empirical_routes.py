# empirical_routes.py
from urllib.parse import urlencode

from flask import Blueprint, render_template, request, session

from data_queries import get_user_sites_rows

empirical_bp = Blueprint("empirical_bp", __name__)
PANEL_BASE = "http://localhost:5007"


def _current_email():
    return session.get("email") or "demo@example.com"


def _to_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _build_panel_query(site):
    if not site:
        return {}
    query = {}
    m = _to_float(site.get("aquifer_thickness"))
    ca = _to_float(site.get("electron_acceptor_o2"))
    cd = _to_float(site.get("electron_donor"))
    if m is not None:
        query["M"] = m
    # Do not map hydraulic conductivity -> tv.
    # Model tv is transverse dispersivity, and this CSV does not provide it directly.
    if ca is not None:
        query["Ca"] = ca
    if cd is not None:
        query["Cd"] = cd
    if site.get("id") is not None:
        query["site_id"] = int(site.get("id"))
    # R (recharge rate) is not present in uploaded site schema.
    # Keep a safe model default instead of mapping unrelated columns.
    query["R"] = 1.0
    query["g"] = 3.5
    query["email"] = _current_email()
    return query


def _selected_site():
    sites = get_user_sites_rows(_current_email())
    if not sites:
        return sites, None
    selected_id = request.args.get("site_id", type=int)
    if selected_id is None:
        return sites, sites[0]
    for site in sites:
        if site.get("id") == selected_id:
            return sites, site
    return sites, sites[0]


def _panel_src(path, site):
    query = _build_panel_query(site)
    if not query:
        return f"{PANEL_BASE}/{path}"
    return f"{PANEL_BASE}/{path}?{urlencode(query)}"


@empirical_bp.route("/empirical")
def empirical_landing():
    return render_template("empirical_landing.html")

@empirical_bp.route("/empirical/maier/single")
def maier_single():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_maier_single.html",
        panel_src=_panel_src("panel_maier_single", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )

@empirical_bp.route("/empirical/maier/multiple")
def maier_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_maier_multiple.html",
        panel_src=_panel_src("panel_maier_multiple", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )

@empirical_bp.route("/empirical/birla/single")
def birla_single():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_birla_single.html",
        panel_src=_panel_src("panel_birla_single", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )

@empirical_bp.route("/empirical/birla/multiple")
def birla_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_birla_multiple.html",
        panel_src=_panel_src("panel_birla_multiple", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )
