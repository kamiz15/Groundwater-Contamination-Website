# empirical_routes.py
"""
Blueprint for empirical models (Maier & Birla and friends).

Right now this is a minimal stub so that:
- app.py can import and register empirical_bp
- The server starts without errors
- You can later add real routes for Maier & Birla

You can extend this later with:
  from empirical_models import maier_lmax, birla_lmax
  and proper routes.
"""

from flask import Blueprint, jsonify

empirical_bp = Blueprint("empirical_bp", __name__, url_prefix="/empirical")


@empirical_bp.route("/ping", methods=["GET"])
def ping_empirical():
    """
    Simple health-check endpoint:
    GET /empirical/ping  ->  {"status": "ok", "message": "Empirical routes loaded"}
    """
    return jsonify({
        "status": "ok",
        "message": "Empirical routes loaded"
    })
