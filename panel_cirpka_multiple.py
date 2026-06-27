import pandas as pd
import panel as pn

from panel_auth import authenticated_email

from analytical_models import compute_cirpka_multiple
from panel_analytical_common import (
    comparison_plot, error_card, info_card, query_float, query_int, summary_card,
)
from panel_theme import report_bridge_html

pn.extension("tabulator", sizing_mode="stretch_width")


def cirpka_multiple_app():
    init_df = pd.DataFrame([
        {
            "Sw": query_float("Sw", 10.0),
            "alpha_Th": query_float("alpha_Th", 0.1),
            "gamma": query_float("gamma", 3.5),
            "C_A": query_float("C_A", 8.0),
            "C_D": query_float("C_D", 5.0),
        }
    ])

    table = pn.widgets.Tabulator(init_df, height=300, sizing_mode="stretch_width", name="Cirpka scenarios")
    run_btn = pn.widgets.Button(name="Run Cirpka scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Add rows and click Run to compare plume lengths."), sizing_mode="stretch_width")
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

            entries = [
                [
                    float(row.get("Sw", 0.0)),
                    float(row.get("alpha_Th", 0.0)),
                    float(row.get("gamma", 0.0)),
                    float(row.get("C_A", 0.0)),
                    float(row.get("C_D", 0.0)),
                ]
                for _, row in df.iterrows()
            ]

            results = compute_cirpka_multiple(entries)
            lmax_vals = [r["Lmax"] for r in results]

            result_pane.object = summary_card(
                [
                    ("Successful runs", str(len(lmax_vals))),
                    ("Max plume length", f"{max(lmax_vals):.2f} m"),
                    ("Min plume length", f"{min(lmax_vals):.2f} m"),
                ],
                title="Cirpka et al. (2005) Summary",
            )
            plot_pane.object = comparison_plot(
                "Cirpka et al. (2005)",
                "Cirpka L\u2098\u2090\u2093",
                list(range(1, len(lmax_vals) + 1)),
                lmax_vals,
                selected_site_id,
                email,
                "Scenario Number",
            )
            _state.update({
                "parameters": [{"symbol": f"Sc.{i+1}", "name": f"Scenario {i+1}", "value": f"L={v:.2f}", "unit": "m"} for i, v in enumerate(lmax_vals)],
                "outputs": [
                    {"label": "Scenarios run", "value": str(len(lmax_vals)), "unit": ""},
                    {"label": "Max plume length", "value": f"{max(lmax_vals):.2f}", "unit": "m"},
                    {"label": "Min plume length", "value": f"{min(lmax_vals):.2f}", "unit": "m"},
                ],
                "plot_data": {"labels": [f"Sc.{i+1}" for i in range(len(lmax_vals))], "values": lmax_vals, "ylabel": "Plume Length (m)", "title": "Scenario Comparison — Cirpka et al. (2005)"},
            })
            report_bridge.object = report_bridge_html(
                "Cirpka et al. (2005) — Multiple Simulation", "Cirpka Analytical",
                "cirpka_multiple_report.pdf",
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

    controls = pn.Column(
        "## Cirpka et al. (2005) \u2014 Multiple Simulation",
        "### Scenario inputs (one row per scenario)",
        table,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 380px", "min-width": "300px"},
    )
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, report_bridge, sizing_mode="stretch_both", styles={"gap": "14px"})
