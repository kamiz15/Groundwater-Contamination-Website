# panel_ham_single.py
import panel as pn
from bokeh.plotting import figure
from analytical_models import ham_lmax

pn.extension()


def ham_single_app():

    M = pn.widgets.FloatInput(name="M", value=1.0, step=0.1)
    alpha = pn.widgets.FloatInput(name="alpha", value=0.01, step=0.001)
    k = pn.widgets.FloatInput(name="k", value=0.1, step=0.01)

    # FIX: add missing parameters required by ham_lmax()
    C_EA0 = pn.widgets.FloatInput(name="EA0 (Electron Acceptor)", value=8.0, step=0.1)
    C_ED0 = pn.widgets.FloatInput(name="ED0 (Electron Donor)", value=5.0, step=0.1)

    result_pane = pn.pane.Markdown("")
    plot_pane = pn.pane.Bokeh(height=350, sizing_mode="stretch_width")

    def update(event=None):
        L = ham_lmax(
            M.value,
            alpha.value,
            k.value,
            C_EA0.value,
            C_ED0.value
        )

        result_pane.object = f"### Result\n- **Lmax ≈ {L:.2f} m**"

        p = figure(
            height=350,
            sizing_mode="stretch_width",
            x_axis_label="Scenario",
            y_axis_label="Lmax (m)",
            title="Ham Model Result (Single Scenario)",
        )
        p.scatter([1], [L], size=12)
        plot_pane.object = p

    for w in (M, alpha, k, C_EA0, C_ED0):
        w.param.watch(update, "value")

    update()

    return pn.Column(
        "# Ham – Single Simulation",
        M, alpha, k, C_EA0, C_ED0,
        result_pane,
        plot_pane,
        sizing_mode="stretch_width",
    )
