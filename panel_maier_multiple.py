import pandas as pd
import panel as pn

from panel_auth import authenticated_email

from empirical_models import maier_lmax
from panel_empirical_common import comparison_plot, error_card, info_card, query_float, query_int, summary_card
from panel_theme import report_bridge_html
from param_meta import table_titles

pn.extension("tabulator", sizing_mode="stretch_width")


def maier_multiple_app():
    default_df = pd.DataFrame([{
        "M": query_float("M", 5.0), "tv": query_float("tv", 0.01),
        "g": query_float("g", 3.5), "Ca": query_float("Ca", 8.0),
        "Cd": query_float("Cd", 5.0),
    }])

    table = pn.widgets.Tabulator(default_df, titles=table_titles(default_df.columns), height=300, sizing_mode="stretch_width", name="Maier scenarios")
    run_btn = pn.widgets.Button(name="Run Maier scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the Maier scenarios to compare plume lengths."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = authenticated_email()
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}

    report_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")

    def _run(_=None):
        try:
            df = table.value
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)
            if df.empty:
                raise ValueError("No scenarios available.")
            lengths = [maier_lmax(float(row.get("M", 0)), float(row.get("tv", 0)), float(row.get("g", 0)), float(row.get("Ca", 0)), float(row.get("Cd", 0))) for _, row in df.iterrows()]
            result_pane.object = summary_card([("Successful runs", str(len(lengths))), ("Maximum Plume Length L_max", f"{max(lengths):.2f} m")])
            plot_pane.object = comparison_plot("Maier and Grathwohl (2005)", "Maier model plume length", list(range(1, len(lengths) + 1)), lengths, selected_site_id, email, "Scenario Number")
            _state.update({
                "parameters": [{"symbol": f"Sc.{i+1}", "name": f"Scenario {i+1}", "value": f"L={v:.2f}", "unit": "m"} for i, v in enumerate(lengths)],
                "outputs": [
                    {"label": "Scenarios run", "value": str(len(lengths)), "unit": ""},
                    {"label": "Max plume length", "value": f"{max(lengths):.2f}", "unit": "m"},
                    {"label": "Min plume length", "value": f"{min(lengths):.2f}", "unit": "m"},
                ],
                "plot_data": {"labels": [f"Sc.{i+1}" for i in range(len(lengths))], "values": lengths, "ylabel": "Maximum Plume Length L_max [m]", "title": "Scenario Comparison — Maier & Grathwohl"},
            })
            report_bridge.object = report_bridge_html(
                "Maier & Grathwohl — Multiple Simulation", "Maier Empirical",
                "maier_multiple_report.pdf",
                parameters=_state["parameters"], outputs=_state["outputs"],
                plot_data=_state.get("plot_data"),
            )
        except Exception as exc:
            result_pane.object = error_card(exc)
            plot_pane.object = None
            report_bridge.object = report_bridge_html(clear=True)

    run_btn.on_click(_run)
    if query_int("output_only", 0):
        if query_int("run", 0):
            _run()
        return pn.Column(result_pane, plot_pane, sizing_mode="stretch_width", styles={"gap": "14px"})

    controls = pn.Column("## Maier & Grathwohl - Multiple Simulation", "### Manual scenario inputs", table, sizing_mode="stretch_width", styles={"flex": "1 1 380px", "min-width": "300px"})
    outputs_col = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs_col, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, report_bridge, sizing_mode="stretch_both", styles={"gap": "14px"})
