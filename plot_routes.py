from flask import Blueprint, render_template

plot_bp = Blueprint("plot_bp", __name__, url_prefix="/plots")

@plot_bp.route("/")
def all_plots():
    return render_template("plot_bar.html")  # or make a real "all plots" page later

@plot_bp.route("/bar")
def bar():
    return render_template("plot_bar.html")

@plot_bp.route("/box")
def box():
    return render_template("plot_box.html")

@plot_bp.route("/hist")
def hist():
    return render_template("plot_hist.html")

@plot_bp.route("/scatter")
def scatter():
    return render_template("plot_hist.html")  # placeholder until you make scatter template

@plot_bp.route("/stats")
def stats():
    return render_template("plot_hist.html")  # placeholder
