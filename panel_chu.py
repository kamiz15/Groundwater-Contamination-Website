# panel_chu.py
import pandas as pd
import panel as pn
from bokeh.plotting import figure

from analytical_models import chu_lmax, compute_chu_multiple

pn.extension("tabulator")


# ----------------- SINGLE -----------------

def chu_single_app():
    """
    Panel UI for a single Chu et al. simulation.
    """

    W = pn.widgets.FloatInput(name="Source width W [m]", value=2.0, step=0.1)
    alpha_Th = pn.widgets.FloatInput(
        name="Horizontal transverse dispersivity α_Th [m]",
        value=0.01,
        step=0.001,
    )
    gamma = pn.widgets.FloatInput(name="Stoichiometric ratio γ [-]", value=1.5, step=0.1)
    C_EA0 = pn.widgets.FloatInput(
        name="Acceptor concentration C_EA0 [mg/L]", value=8.0, step=0.1
    )
    C_ED0 = pn.widgets.FloatInput(
        name="Donor concentration C_ED0 [mg/L]", value=5.0, step=0.1
    )
    epsilon = pn.widgets.FloatInput(
        name="Biological factor ε [mg/L]", value=0.0, step=0.01
    )

    result_md = pn.pane.Markdown()
    plot_pane = pn.pane.Bokeh(height=320, sizing_mode="stretch_width")

    def update(_=None):
        L = chu_lmax(
            W.value,
            alpha_Th.value,
            gamma.value,
            C_EA0.value,
            C_ED0.value,
            epsilon.value,
        )

        result_md.object = f"### Result\n\n- **Lmax ≈ {L:.2f} m**"

        p = figure(
            title="Chu – Lmax (single scenario)",
            x_axis_label="Scenario index",
            y_axis_label="Lmax (m)",
            height=320,
            sizing_mode="stretch_width",
        )
        p.circle(x=[0], y=[L], size=12)
        plot_pane.object = p

    for w in (W, alpha_Th, gamma, C_EA0, C_ED0, epsilon):
        w.param.watch(update, "value")

    update()

    return pn.Column(
        "# Chu et al. — Single Simulation",
        W,
        alpha_Th,
        gamma,
        C_EA0,
        C_ED0,
        epsilon,
        result_md,
        plot_pane,
        sizing_mode="stretch_width",
    )


# ----------------- MULTIPLE -----------------

def chu_multiple_app():
    """
    Panel UI for multiple Chu simulations.
    """

    default_df = pd.DataFrame(
        [
            {
                "W": 2.0,
                "alpha_Th": 0.01,
                "gamma": 1.5,
                "C_EA0": 8.0,
                "C_ED0": 5.0,
                "epsilon": 0.0,
            }
        ]
    )

    table = pn.widgets.Tabulator(
        default_df,
        height=260,
        sizing_mode="stretch_width",
        name="Chu scenarios",
    )

    result_md = pn.pane.Markdown()
    plot_pane = pn.pane.Bokeh(height=320, sizing_mode="stretch_width")

    def run(_=None):
        df = table.value
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)

        entries = []
        for _, row in df.iterrows():
            entries.append(
                [
                    float(row.get("W", 0.0)),
                    float(row.get("alpha_Th", 0.0)),
                    float(row.get("gamma", 0.0)),
                    float(row.get("C_EA0", 0.0)),
                    float(row.get("C_ED0", 0.0)),
                    float(row.get("epsilon", 0.0)),
                ]
            )

        if not entries:
            result_md.object = "### Results\n\nNo rows in table."
            plot_pane.object = None
            return

        Ls = compute_chu_multiple(entries)

        lines = ["### Results"]
        for i, L in enumerate(Ls, start=1):
            lines.append(f"- Row {i}: **Lmax ≈ {L:.2f} m**")
        result_md.object = "\n".join(lines)

        p = figure(
            title="Chu – Lmax for each scenario",
            x_axis_label="Scenario index",
            y_axis_label="Lmax (m)",
            height=320,
            sizing_mode="stretch_width",
        )
        x_vals = list(range(1, len(Ls) + 1))
        p.circle(x=x_vals, y=Ls, size=8)
        plot_pane.object = p

    table.param.watch(run, "value")
    run()

    return pn.Column(
        "# Chu et al. — Multiple Simulation",
        "Edit the table and the plot will update automatically.",
        table,
        result_md,
        plot_pane,
        sizing_mode="stretch_width",
    )
