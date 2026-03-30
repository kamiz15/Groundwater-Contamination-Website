import pandas as pd
import panel as pn

from empirical_models import maier_lmax
from panel_empirical_common import comparison_plot, error_card, info_card, query_float, query_int, query_str, summary_card

pn.extension("tabulator", sizing_mode="stretch_width")


def maier_multiple_app():
    default_df = pd.DataFrame([
        {
            "M": query_float("M", 5.0),
            "tv": query_float("tv", 0.01),
            "g": query_float("g", 3.5),
            "Ca": query_float("Ca", 8.0),
            "Cd": query_float("Cd", 5.0),
        }
    ])

    table = pn.widgets.Tabulator(default_df, height=300, sizing_mode="stretch_width", name="Maier scenarios")
    run_btn = pn.widgets.Button(name="Run Maier scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the Maier scenarios to compare plume lengths."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    def _run(_=None):
        try:
            df = table.value
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)
            if df.empty:
                raise ValueError("No scenarios available.")

            lengths = []
            for _, row in df.iterrows():
                lengths.append(
                    maier_lmax(
                        float(row.get("M", 0.0)),
                        float(row.get("tv", 0.0)),
                        float(row.get("g", 0.0)),
                        float(row.get("Ca", 0.0)),
                        float(row.get("Cd", 0.0)),
                    )
                )

            result_pane.object = summary_card([
                ("Successful runs", str(len(lengths))),
                ("Max plume length", f"{max(lengths):.2f} m"),
            ])
            plot_pane.object = comparison_plot(
                "Maier and Grathwohl (2005)",
                "Maier model plume length",
                list(range(1, len(lengths) + 1)),
                lengths,
                selected_site_id,
                email,
                "Scenario Number",
            )
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None

    run_btn.on_click(_run)

    controls = pn.Column(
        "## Maier & Grathwohl - Multiple Simulation",
        "### Manual scenario inputs",
        table,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 380px", "min-width": "300px"},
    )
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, sizing_mode="stretch_both", styles={"gap": "14px"})
