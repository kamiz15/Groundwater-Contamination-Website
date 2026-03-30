import pandas as pd
import panel as pn

from analytical_models import compute_ham_multiple
from panel_analytical_common import comparison_plot, error_card, info_card, query_float, query_int, query_str, summary_card

pn.extension("tabulator", sizing_mode="stretch_width")


def ham_multiple_app():
    init_df = pd.DataFrame([
        {
            "Q": query_float("Q", 5.0),
            "alpha_T": query_float("alpha_T", 0.01),
            "gamma": query_float("gamma", 3.5),
            "C_EA0": query_float("C_EA0", 8.0),
            "C_ED0": query_float("C_ED0", 5.0),
        }
    ])

    table = pn.widgets.Tabulator(init_df, height=300, sizing_mode="stretch_width", name="Ham scenarios")
    run_btn = pn.widgets.Button(name="Run Ham scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the Ham scenarios to compare plume lengths."), sizing_mode="stretch_width")
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

            entries = []
            for _, row in df.iterrows():
                entries.append([
                    float(row.get("Q", 0.0)),
                    float(row.get("alpha_T", 0.0)),
                    float(row.get("gamma", 0.0)),
                    float(row.get("C_EA0", 0.0)),
                    float(row.get("C_ED0", 0.0)),
                ])

            l_vals = compute_ham_multiple(entries)
            result_pane.object = summary_card([("Successful runs", str(len(l_vals))), ("Max plume length", f"{max(l_vals):.2f} m")])
            plot_pane.object = comparison_plot("Ham et al.", "Ham model plume length", list(range(1, len(l_vals) + 1)), l_vals, selected_site_id, email, "Scenario Number")
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None

    run_btn.on_click(_run)

    controls = pn.Column("## Ham et al. - Multiple Simulation", "### Manual scenario inputs", table, sizing_mode="stretch_width", styles={"flex": "1 1 380px", "min-width": "300px"})
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, sizing_mode="stretch_both", styles={"gap": "14px"})
