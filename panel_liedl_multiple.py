import pandas as pd
import panel as pn

from panel_auth import authenticated_email

from analytical_models import compute_liedl_multiple
from panel_analytical_common import comparison_plot, error_card, info_card, query_float, query_int, summary_card
from panel_theme import report_bridge_html

pn.extension("tabulator", sizing_mode="stretch_width")


def liedl_multiple_app():
    init_df = pd.DataFrame([{
        "M": query_float("M", 3.5), "alpha_Tv": query_float("alpha_Tv", 0.001),
        "gamma": query_float("gamma", 3.5), "C_EA0": query_float("C_EA0", 8.0),
        "C_ED0": query_float("C_ED0", 5.0),
    }])

    table = pn.widgets.Tabulator(init_df, height=300, sizing_mode="stretch_width", name="Liedl scenarios")
    run_btn = pn.widgets.Button(name="Run Liedl scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the Liedl scenarios to compare plume lengths."), sizing_mode="stretch_width")
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
            entries = [[float(row.get(k, 0)) for k in ("M", "alpha_Tv", "gamma", "C_EA0", "C_ED0")] for _, row in df.iterrows()]
            l_vals = compute_liedl_multiple(entries)
            result_pane.object = summary_card([("Successful runs", str(len(l_vals))), ("Max plume length", f"{max(l_vals):.2f} m")])
            plot_pane.object = comparison_plot("Liedl et al. (2005)", "Liedl model plume length", list(range(1, len(l_vals) + 1)), l_vals, selected_site_id, email, "Scenario Number")
            _state.update({
                "parameters": [{"symbol": f"Sc.{i+1}", "name": f"Scenario {i+1}", "value": f"L={v:.2f}", "unit": "m"} for i, v in enumerate(l_vals)],
                "outputs": [
                    {"label": "Scenarios run", "value": str(len(l_vals)), "unit": ""},
                    {"label": "Max plume length", "value": f"{max(l_vals):.2f}", "unit": "m"},
                    {"label": "Min plume length", "value": f"{min(l_vals):.2f}", "unit": "m"},
                ],
                "plot_data": {"labels": [f"Sc.{i+1}" for i in range(len(l_vals))], "values": l_vals, "ylabel": "Plume Length (m)", "title": "Scenario Comparison — Liedl et al. (2005)"},
            })
            report_bridge.object = report_bridge_html(
                "Liedl et al. (2005) — Multiple Simulation", "Liedl Analytical",
                "liedl_multiple_report.pdf",
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

    controls = pn.Column("## Liedl et al. (2005) - Multiple Simulation", "### Manual scenario inputs", table, sizing_mode="stretch_width", styles={"flex": "1 1 380px", "min-width": "300px"})
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, report_bridge, sizing_mode="stretch_both", styles={"gap": "14px"})
