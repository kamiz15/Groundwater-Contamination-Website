# empirical_routes.py
from flask import Blueprint, render_template, request, jsonify
from empirical_models import maier_lmax, birla_lmax

empirical_bp = Blueprint("empirical_bp", __name__, url_prefix="/empirical")

# -----------------------------
# MAIER SINGLE
# -----------------------------
@empirical_bp.route("/maier/single", methods=["POST"])
def maier_single():
    M = float(request.form["Thickness"])
    tv = float(request.form["Dispersivity"])
    g = float(request.form["Stoichiometric"])
    Ca = float(request.form["Acceptor"])
    Cd = float(request.form["Donor"])
    result = maier_lmax(M, tv, g, Ca, Cd)
    return jsonify({"result": result})


# -----------------------------
# BIRLA SINGLE
# -----------------------------
@empirical_bp.route("/birla/single", methods=["POST"])
def birla_single():
    M = float(request.form["Thickness"])
    tv = float(request.form["Dispersivity"])
    g = float(request.form["Stoichiometric"])
    Ca = float(request.form["Acceptor"])
    Cd = float(request.form["Donor"])
    R = float(request.form["Recharge"])

    result = birla_lmax(M, tv, g, Ca, Cd, R)
    return jsonify({"result": result})
