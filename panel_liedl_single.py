# panel_liedl_single.py
import panel as pn
from bokeh.plotting import figure

from analytical_models import liedl_lmax

pn.extension()


def liedl_single_app():
    """
    Panel UI for a single Liedl et al. (2005) simulation with
    a scatter plot.
    """

    # Inputs
    M = pn.widgets.FloatInput(name="M (mass per unit width)", value=3.5, step=0.1)
    alpha_Tv = pn.widgets.FloatInput(name="α_Tv (transverse dispersivity)", value=0.001, step=0.0001)
    gamma = pn.widgets.FloatInput(name="γ (stoichiometric factor)", value=3.5, step=0.1)
    C_EA0 = pn.widgets.FloatInput(name="C_EA0 (acceptor) [mg/L]", value=8.0, step=0.1)
    C_ED0 = pn.widgets.FloatInput(name="C_ED0 (donor) [mg/L]", value=5.0, step=0.1)

    result_md = pn.pane.Markdown()
    plot_pane = pn.pane.Bokeh(height=320, sizing_mode="stretch_width")

    def update(_=None):
        L = liedl_lmax(
            M.value,
            alpha_Tv.value,
            gamma.value,
            C_EA0.value,
            C_ED0.value,
        )

        result_md.object = f"### Result\n\n- **Lmax ≈ {L:.2f} m**"

        p = figure(
            title="Liedl – Lmax (single scenario)",
            x_axis_label="Scenario index",
            y_axis_label="Lmax (m)",
            height=320,
            sizing_mode="stretch_width",
        )
        # single-point scatter
        p.circle(x=[0], y=[L], size=12)
        plot_pane.object = p

    for w in (M, alpha_Tv, gamma, C_EA0, C_ED0):
        w.param.watch(update, "value")

    update()

    return pn.Column(
        "# Liedl et al. (2005) — Single Simulation",
        M,
        alpha_Tv,
        gamma,
        C_EA0,
        C_ED0,
        result_md,
        plot_pane,
        sizing_mode="stretch_width",
    )
