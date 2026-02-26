# analytical_routes.py
from urllib.parse import urlencode

from flask import Blueprint, render_template, request, session

from data_queries import get_user_sites_rows

analytical_bp = Blueprint("analytical_bp", __name__)

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


def _build_panel_query(path, site):
    if not site:
        return {}

    aquifer = _to_float(site.get("aquifer_thickness"))
    plume_length = _to_float(site.get("plume_length"))
    plume_width = _to_float(site.get("plume_width"))
    conductivity = _to_float(site.get("hydraulic_conductivity"))
    donor = _to_float(site.get("electron_donor"))
    o2 = _to_float(site.get("electron_acceptor_o2"))
    no3 = _to_float(site.get("electron_acceptor_no3"))

    query = {}
    if aquifer is not None:
        query["M"] = aquifer
        query["H"] = aquifer
    if plume_length is not None:
        query["Q"] = plume_length
    if plume_width is not None:
        query["W"] = plume_width
    if conductivity is not None:
        query["alpha_Tv"] = conductivity
        query["alpha_Th"] = conductivity
        query["alpha"] = conductivity
        query["alpha_T"] = conductivity
        query["v"] = conductivity
    if donor is not None:
        query["C_ED0"] = donor
        query["c0"] = donor
    if o2 is not None:
        query["C_EA0"] = o2
    if no3 is not None:
        query["epsilon"] = no3
        query["k"] = no3
    if site.get("id") is not None:
        query["site_id"] = int(site.get("id"))
    query["email"] = _current_email()

    # model defaults
    if "bioscreen" in path:
        query.setdefault("gamma", 0.0)
        query.setdefault("time", 20)
        query.setdefault("Cthres", 5e-5)
        query.setdefault("Df", 0.0)
        query.setdefault("R", 1.0)
        query.setdefault("lam", 0.1)
        query.setdefault("ng", 60)
    else:
        query.setdefault("gamma", 3.5)
        query.setdefault("time", 20)
        query.setdefault("Cthres", 0.05)
        query.setdefault("Df", 0.0)
        query.setdefault("R", 1.0)
        query.setdefault("lam", 0.1)
        query.setdefault("ng", 60)
    return query


def _panel_src(path, site):
    query = _build_panel_query(path, site)
    if not query:
        return f"{PANEL_BASE}/{path}"
    return f"{PANEL_BASE}/{path}?{urlencode(query)}"


# ---------- LANDING (All models page) ----------
@analytical_bp.route("/analytical")
def analytical_landing():
    return render_template("analytical_landing.html")


# ---------- LIEDL ----------
@analytical_bp.route("/liedl/single")
def liedl_single():
    sites, selected_site = _selected_site()
    return render_template(
        "liedl_single.html",
        panel_src=_panel_src("panel_liedl_single", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )


@analytical_bp.route("/liedl/multiple")
def liedl_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_liedl_multiple.html",
        panel_src=_panel_src("panel_liedl_multiple", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )


# ---------- CHU ----------
@analytical_bp.route("/chu/single")
def chu_single():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_chu_single.html",
        panel_src=_panel_src("panel_chu_single", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )

@analytical_bp.route("/chu/multiple")
def chu_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_chu_multiple.html",
        panel_src=_panel_src("panel_chu_multiple", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )


# ---------- HAM ----------
@analytical_bp.route("/ham/single")
def ham_single():
    sites, selected_site = _selected_site()
    return render_template(
        "ham_single.html",
        panel_src=_panel_src("panel_ham_single", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )

@analytical_bp.route("/ham/multiple")
def ham_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_ham_multiple.html",
        panel_src=_panel_src("panel_ham_multiple", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )

#----------Bioscreen-------------

@analytical_bp.route("/bioscreen/single")
def bioscreen_single():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_bioscreen_single.html",
        panel_src=_panel_src("panel_bioscreen_single", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )

@analytical_bp.route("/bioscreen/multiple")
def bioscreen_multiple():
    sites, selected_site = _selected_site()
    return render_template(
        "panel_bioscreen_multiple.html",
        panel_src=_panel_src("panel_bioscreen_multiple", selected_site),
        sites=sites,
        selected_site_id=selected_site.get("id") if selected_site else None,
    )
