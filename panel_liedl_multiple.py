# panel_liedl_multiple.py
import pandas as pd
import panel as pn
from bokeh.plotting import figure

from analytical_models import compute_liedl_multiple

pn.extension("tabulator")


def liedl_multiple_app():
    """
    Panel UI for multiple Liedl simulations.
    """

    # Initial data – one default scenario
    init_df = pd.DataFrame(
        [
            {
                "M": 3.5,
                "alpha_Tv": 0.001,
                "gamma": 3.5,
                "C_EA0": 8.0,
                "C_ED0": 5.0,
            }
        ]
    )

    table = pn.widgets.Tabulator(
        init_df,
        height=260,
        sizing_mode="stretch_width",
        name="Liedl scenarios",
    )

    result_md = pn.pane.Markdown()
    plot_pane = pn.pane.Bokeh(height=320, sizing_mode="stretch_width")

    def recompute(_=None):
        df = table.value
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)

        entries = []
        for _, row in df.iterrows():
            entries.append(
                [
                    float(row.get("M", 0.0)),
                    float(row.get("alpha_Tv", 0.0)),
                    float(row.get("gamma", 0.0)),
                    float(row.get("C_EA0", 0.0)),
                    float(row.get("C_ED0", 0.0)),
                ]
            )

        if not entries:
            result_md.object = "### Results\n\nNo rows in table."
            plot_pane.object = None
            return

        Ls = compute_liedl_multiple(entries)

        # Markdown summary
        lines = ["### Results"]
        for i, L in enumerate(Ls, start=1):
            lines.append(f"- Row {i}: **Lmax ≈ {L:.2f} m**")
        result_md.object = "\n".join(lines)

        # Scatter plot
        p = figure(
            title="Liedl – Lmax for each scenario",
            x_axis_label="Scenario index",
            y_axis_label="Lmax (m)",
            height=320,
            sizing_mode="stretch_width",
        )
        x_vals = list(range(1, len(Ls) + 1))
        p.circle(x=x_vals, y=Ls, size=8)
        plot_pane.object = p

    table.param.watch(recompute, "value")
    recompute()

    return pn.Column(
        "# Liedl et al. (2005) — Multiple Simulation",
        "Edit the parameters in the table below. Each row is a scenario.",
        table,
        result_md,
        plot_pane,
        sizing_mode="stretch_width",
    )
