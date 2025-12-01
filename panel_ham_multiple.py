# panel_ham_multiple.py
import pandas as pd
import panel as pn
from bokeh.plotting import figure

from analytical_models import compute_ham_multiple

pn.extension("tabulator")


def ham_multiple_app():
    """
    Panel UI for multiple Ham simulations.
    """

    init_df = pd.DataFrame(
        [
            {
                "Q": 1.0,          # flow / discharge
                "alpha_T": 0.01,  # transverse dispersivity
                "v": 1.0,         # velocity
                "C_EA0": 8.0,     # acceptor
                "C_ED0": 5.0,     # donor
            }
        ]
    )

    table = pn.widgets.Tabulator(
        init_df,
        height=260,
        sizing_mode="stretch_width",
        name="Ham scenarios",
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
                    float(row.get("Q", 0.0)),
                    float(row.get("alpha_T", 0.0)),
                    float(row.get("v", 0.0)),
                    float(row.get("C_EA0", 0.0)),
                    float(row.get("C_ED0", 0.0)),
                ]
            )

        if not entries:
            result_md.object = "### Results\n\nNo rows in table."
            plot_pane.object = None
            return

        Ls = compute_ham_multiple(entries)

        lines = ["### Results"]
        for i, L in enumerate(Ls, start=1):
            lines.append(f"- Row {i}: **Lmax ≈ {L:.2f} m**")
        result_md.object = "\n".join(lines)

        p = figure(
            title="Ham – Lmax for each scenario",
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
        "# Ham et al. — Multiple Simulation",
        "Edit the table and see how Lmax changes between scenarios.",
        table,
        result_md,
        plot_pane,
        sizing_mode="stretch_width",
    )
