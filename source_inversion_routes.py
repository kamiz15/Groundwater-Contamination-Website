from urllib.parse import urlencode

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from settings import PANEL_PUBLIC_BASE

source_inversion_bp = Blueprint("source_inversion_bp", __name__)


def _panel_src() -> str:
    base = PANEL_PUBLIC_BASE
    params: dict = {
        "alpha_lo": 1e-7,
        "alpha_hi": 1.0,
        "tol":      1e-9,
        "maxiter":  500,
    }
    for key, val in request.args.items():
        if val != "":
            params[key] = val
    if current_user.is_authenticated:
        params["email"] = current_user.email
    return f"{base}/panel_source_inversion?{urlencode(params)}"


@source_inversion_bp.route("/source/inversion")
@login_required
def source_inversion():
    return render_template(
        "panel_source_inversion.html",
        panel_src=_panel_src(),
    )
