from urllib.parse import urlencode

from flask import Blueprint, render_template, request
from flask_login import current_user, login_required

from settings import PANEL_PUBLIC_BASE

source_geometry_bp = Blueprint("source_geometry_bp", __name__)


def _panel_src() -> str:
    """Build the Panel iframe URL, forwarding any query-string overrides."""
    base = PANEL_PUBLIC_BASE
    # Defaults; overridden by anything already in request.args
    params: dict = {
        "shape":     "circle",
        "cx":        0.0,
        "cy":        0.0,
        "radius":    10.0,
        "semi_a":    15.0,
        "semi_b":    8.0,
        "angle_deg": 0.0,
        "x1":        -20.0,
        "y1":        -10.0,
        "x2":        20.0,
        "y2":        10.0,
        "n_pts":     0,
        "alpha_Tv":  0.001,
        "gamma":     3.5,
        "C_EA0":     8.0,
        "C_ED0":     5.0,
    }
    for key, val in request.args.items():
        if val != "":
            params[key] = val
    if current_user.is_authenticated:
        params["email"] = current_user.email
    return f"{base}/panel_source_geometry?{urlencode(params)}"


@source_geometry_bp.route("/source/geometry")
@login_required
def source_geometry():
    return render_template(
        "panel_source_geometry.html",
        panel_src=_panel_src(),
    )
