"""Multiple-simulation panel, shared by every analytical and empirical model.

All these pages are the same page: the workbench sidebar picks sites, the model
runs once per selected site using that site's database parameters, and the graph
puts the modelled plume length next to the measured one. Only MODEL_SPECS below
differs per model, so there is one panel body instead of eight near-copies.

Parameters a site leaves NULL fall back to the values in the panel URL - the
model defaults, or the values of a site loaded in the Site Data card.
"""
from __future__ import annotations

import panel as pn

from analytical_models import chu_lmax, cirpka_lmax, ham_lmax, liedl_lmax, liedl3d_lmax
from bioscreen_model import bio
from data_queries import get_user_sites_rows
from empirical_models import birla_lmax, maier_lmax
from model_site_validation import filter_valid_sites_for_model
from panel_analytical_common import comparison_plot, error_card, query_float, query_str
from panel_auth import authenticated_email
from panel_theme import report_bridge_html
from symbol_registry import db_to_model

pn.extension(sizing_mode="stretch_width")


def _bioscreen_lmax(Cthres, time, M, C_D, S_w, v, ax, ay, az, Df, R, gamma, lam, ng):
    """bio() with the Gauss-point count coerced to the int it requires."""
    return float(bio(Cthres, time, M, C_D, S_w, v, ax, ay, az, Df, R, gamma, lam, int(ng)))


# model -> how to run it per site and how to describe it.
#   fn       callable taking `args` positionally
#   args     canonical symbols (as returned by db_to_model) in fn's argument order
#   defaults fallback value per symbol, also the name looked up in the panel URL
#   report   (symbol, display symbol, name, unit) rows for the PDF
MODEL_SPECS = {
    "liedl": {
        "title": "Liedl et al. (2005)",
        "fn": liedl_lmax,
        "args": ("M", "alpha_Tv", "gamma", "C_A", "C_D"),
        "defaults": {"M": 2.0, "alpha_Tv": 0.001, "gamma": 3.5, "C_A": 8.0, "C_D": 5.0},
        "report": (
            ("M", "S_T", "Source Thickness", "m"),
            ("alpha_Tv", "alpha_Tv", "Vertical Transverse Dispersivity", "m"),
            ("gamma", "gamma", "Stoichiometric Ratio", "-"),
            ("C_D", "C_D0", "Donor Concentration at Source", "mg/L"),
            ("C_A", "C_A0", "Acceptor Concentration at Source", "mg/L"),
        ),
    },
    "liedl3d": {
        "title": "Liedl 3D (2011)",
        "fn": liedl3d_lmax,
        "args": ("M", "alpha_Th", "alpha_Tv", "S_w", "Cthres", "C_A", "C_D", "gamma"),
        "defaults": {"M": 10.0, "alpha_Th": 0.01, "alpha_Tv": 0.01, "S_w": 7.0,
                     "Cthres": 0.5, "C_A": 8.0, "C_D": 5.0, "gamma": 3.0},
        "report": (
            ("M", "S_T", "Source Thickness", "m"),
            ("S_w", "S_W", "Source Width", "m"),
            ("alpha_Th", "alpha_Th", "Horizontal Transverse Dispersivity", "m"),
            ("alpha_Tv", "alpha_Tv", "Vertical Transverse Dispersivity", "m"),
            ("gamma", "gamma", "Stoichiometric Ratio", "-"),
            ("Cthres", "C_thres", "Threshold Donor Concentration", "mg/L"),
            ("C_D", "C_D0", "Donor Concentration at Source", "mg/L"),
            ("C_A", "C_A0", "Acceptor Concentration at Source", "mg/L"),
        ),
    },
    "chu": {
        "title": "Chu et al. (2005)",
        "fn": chu_lmax,
        "args": ("S_w", "alpha_Th", "gamma", "C_A", "C_D", "epsilon"),
        "defaults": {"S_w": 2.0, "alpha_Th": 0.01, "gamma": 1.5, "C_A": 8.0,
                     "C_D": 5.0, "epsilon": 0.0},
        "report": (
            ("S_w", "S_W", "Source Width", "m"),
            ("alpha_Th", "alpha_Th", "Horizontal Transverse Dispersivity", "m"),
            ("gamma", "gamma", "Stoichiometric Ratio", "-"),
            ("C_D", "C_D0", "Donor Concentration at Source", "mg/L"),
            ("C_A", "C_A0", "Acceptor Concentration at Source", "mg/L"),
            ("epsilon", "epsilon", "Biological Concentration Factor", "mg/L"),
        ),
    },
    "ham": {
        "title": "Ham et al. (2004)",
        "fn": ham_lmax,
        "args": ("Q", "alpha_T", "gamma", "C_A", "C_D"),
        "defaults": {"Q": 5.0, "alpha_T": 0.01, "gamma": 3.5, "C_A": 8.0, "C_D": 5.0},
        "report": (
            ("Q", "q", "Source Flux", "m²/yr"),
            ("alpha_T", "alpha_Th", "Horizontal Transverse Dispersivity", "m"),
            ("gamma", "gamma", "Stoichiometric Ratio", "-"),
            ("C_D", "C_D0", "Donor Concentration at Source", "mg/L"),
            ("C_A", "C_A0", "Acceptor Concentration at Source", "mg/L"),
        ),
    },
    "cirpka": {
        "title": "Cirpka et al. (2006)",
        "fn": cirpka_lmax,
        "args": ("S_w", "alpha_Th", "gamma", "C_A", "C_D"),
        "defaults": {"S_w": 10.0, "alpha_Th": 0.1, "gamma": 3.5, "C_A": 8.0, "C_D": 5.0},
        "report": (
            ("S_w", "S_W", "Source Width", "m"),
            ("alpha_Th", "alpha_Th", "Horizontal Transverse Dispersivity", "m"),
            ("gamma", "gamma", "Stoichiometric Ratio", "-"),
            ("C_A", "C_A0", "Acceptor Concentration at Source", "mg/L"),
            ("C_D", "C_D0", "Donor Concentration at Source", "mg/L"),
        ),
    },
    "bioscreen": {
        "title": "BIOSCREEN-AT 3D",
        "fn": _bioscreen_lmax,
        "args": ("Cthres", "time", "M", "C_D", "S_w", "v", "ax", "ay", "az",
                 "Df", "R", "gamma", "lam", "ng"),
        "defaults": {"Cthres": 5e-5, "time": 20.0, "M": 6.1, "C_D": 106.35, "S_w": 20.0,
                     "v": 292.0, "ax": 10.7, "ay": 1.1, "az": 0.11, "Df": 0.0,
                     "R": 1.0, "gamma": 0.0, "lam": 0.445, "ng": 60},
        "report": (
            ("Cthres", "C_thres", "Threshold Contaminant Concentration", "mg/L"),
            ("time", "t", "Simulation Time", "yr"),
            ("M", "S_T", "Source Thickness", "m"),
            ("C_D", "C_D0", "Contamination Concentration", "mg/L"),
            ("S_w", "S_W", "Source Width", "m"),
            ("v", "v", "Groundwater Seepage Velocity", "m/yr"),
            ("ax", "alpha_L", "Longitudinal Dispersivity", "m"),
            ("ay", "alpha_Th", "Horizontal Transverse Dispersivity", "m"),
            ("az", "alpha_Tv", "Vertical Transverse Dispersivity", "m"),
            ("Df", "D_f", "Diffusion Coefficient", "m²/yr"),
            ("R", "R", "Retardation Factor", "-"),
            ("gamma", "Gamma", "Source Decay Coefficient", "1/yr"),
            ("lam", "lambda_e", "First-order Decay Coefficient", "1/yr"),
            ("ng", "n_g", "Number of Gauss Points", "-"),
        ),
    },
    "maier": {
        "title": "Maier & Grathwohl (2006)",
        "fn": maier_lmax,
        "args": ("M", "alpha_Tv", "gamma", "C_A", "C_D"),
        "defaults": {"M": 5.0, "alpha_Tv": 0.01, "gamma": 3.5, "C_A": 8.0, "C_D": 5.0},
        "report": (
            ("M", "S_T", "Source Thickness", "m"),
            ("alpha_Tv", "alpha_Tv", "Vertical Transverse Dispersivity", "m"),
            ("gamma", "gamma", "Stoichiometry Ratio", "-"),
            ("C_A", "C_A0", "Acceptor Concentration at Source", "mg/L"),
            ("C_D", "C_D0", "Donor Concentration at Source", "mg/L"),
        ),
    },
    "birla": {
        "title": "Birla et al. (2020)",
        "fn": birla_lmax,
        "args": ("M", "alpha_Tv", "gamma", "C_A", "C_D", "R"),
        "defaults": {"M": 2.0, "alpha_Tv": 0.001, "gamma": 3.5, "C_A": 8.0,
                     "C_D": 5.0, "R": 1.0},
        "report": (
            ("M", "S_T", "Source Thickness", "m"),
            ("alpha_Tv", "alpha_Tv", "Vertical Transverse Dispersivity", "m"),
            ("R", "R_c", "Recharge Rate", "m/yr"),
            ("gamma", "gamma", "Stoichiometry Ratio", "-"),
            ("C_A", "C_A0", "Acceptor Concentration at Source", "mg/L"),
            ("C_D", "C_D0", "Donor Concentration at Source", "mg/L"),
        ),
    },
}


def selected_site_ids() -> set[int]:
    """Site ids from ?compare_sites=1,2,3. Nothing picked means nothing plotted."""
    ids = set()
    for part in query_str("compare_sites").split(","):
        try:
            ids.add(int(part))
        except ValueError:
            continue
    return ids


def site_label(site) -> str:
    """Sites are identified by their unit, not their row number."""
    return str(site.get("site_unit") or f"Site {site.get('display_id') or site.get('id')}")


def run_sites(model: str, sites, fallback):
    """Run `model` once per site. Returns (labels, lmax values, parameter sets)."""
    spec = MODEL_SPECS[model]
    labels, lengths, param_sets = [], [], []
    for site in sites:
        params = dict(fallback)
        params.update({k: float(v) for k, v in db_to_model(site, model).items()})
        labels.append(site_label(site))
        lengths.append(float(spec["fn"](*(params[a] for a in spec["args"]))))
        param_sets.append(params)
    return labels, lengths, param_sets


def site_comparison_app(model: str):
    spec = MODEL_SPECS[model]
    email = authenticated_email()
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    status = pn.pane.HTML("", sizing_mode="stretch_width", margin=0)
    report_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")

    try:
        fallback = {k: query_float(k, v) for k, v in spec["defaults"].items()}

        sites, _invalid = filter_valid_sites_for_model(get_user_sites_rows(email), model)
        wanted = selected_site_ids()
        sites = [s for s in sites if int(s["id"]) in wanted]
        if not sites:
            raise ValueError("No sites selected. Pick sites in the Compare Sites list.")

        labels, lengths, param_sets = run_sites(model, sites, fallback)

        # Model results only - the measured plume lengths are not plotted here.
        plot, plot_data = comparison_plot(
            spec["title"], f"{spec['title']} model plume length",
            list(range(1, len(sites) + 1)), lengths,
            0, email, "Site Number", return_data=True,
        )
        plot_pane.object = plot
        report_bridge.object = report_bridge_html(
            f"{spec['title']} - Multiple Simulation", spec["title"],
            f"{model}_multiple_report.pdf",
            parameters=[
                {"symbol": symbol, "name": f"{label} - {name}", "value": params[key], "unit": unit}
                for label, params in zip(labels, param_sets)
                for key, symbol, name, unit in spec["report"]
            ],
            outputs=[
                {"label": "Sites simulated", "value": str(len(lengths)), "unit": ""},
                {"label": "Max plume length", "value": f"{max(lengths):.2f}", "unit": "m"},
                {"label": "Min plume length", "value": f"{min(lengths):.2f}", "unit": "m"},
            ],
            plot_data=plot_data,
        )
    except Exception as exc:
        status.object = error_card(exc)
        plot_pane.object = None
        report_bridge.object = report_bridge_html(clear=True)

    return pn.Column(status, plot_pane, report_bridge, sizing_mode="stretch_both", styles={"gap": "14px"})
