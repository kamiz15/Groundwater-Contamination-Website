# analytical_routes.py
from flask import Blueprint, render_template

analytical_bp = Blueprint("analytical_bp", __name__)

PANEL_BASE = "http://localhost:5007"


@analytical_bp.route("/liedl/single")
def liedl_single():
    return render_template(
        "liedl_single.html",
        panel_src=f"{PANEL_BASE}/panel_liedl_single",
    )


@analytical_bp.route("/liedl/multiple")
def liedl_multiple_wrapper():
    return render_template(
        "panel_liedl_multiple.html",
        panel_src=f"{PANEL_BASE}/panel_liedl_multiple",
    )


@analytical_bp.route("/chu/single")
def chu_single():
    return render_template(
        "panel_chu_single.html",
        panel_src=f"{PANEL_BASE}/panel_chu_single",
    )


@analytical_bp.route("/chu/multiple")
def chu_multiple_wrapper():
    return render_template(
        "panel_chu_multiple.html",
        panel_src=f"{PANEL_BASE}/panel_chu_multiple",
    )


@analytical_bp.route("/ham/single")
def ham_single():
    # still just the placeholder template
    return render_template("ham_single.html")


@analytical_bp.route("/ham/multiple")
def ham_multiple_wrapper():
    return render_template(
        "panel_ham_multiple.html",
        panel_src=f"{PANEL_BASE}/panel_ham_multiple",
    )
