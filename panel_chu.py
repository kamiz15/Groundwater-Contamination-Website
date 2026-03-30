import pandas as pd
import panel as pn

from analytical_models import chu_lmax, compute_chu_multiple
from panel_analytical_common import comparison_plot, error_card, info_card, metric_card, query_float, query_int, query_str, summary_card

pn.extension("tabulator", sizing_mode="stretch_width")


def chu_single_app():
    w = pn.widgets.FloatInput(name="Source width W [m]", value=query_float("W", 2.0), step=0.1)
    alpha_th = pn.widgets.FloatInput(name="Horizontal transverse dispersivity alpha_Th [m]", value=query_float("alpha_Th", 0.01), step=0.001)
    gamma = pn.widgets.FloatInput(name="Stoichiometric ratio gamma [-]", value=query_float("gamma", 1.5), step=0.1)
    c_ea0 = pn.widgets.FloatInput(name="Acceptor concentration C_EA0 [mg/L]", value=query_float("C_EA0", 8.0), step=0.1)
    c_ed0 = pn.widgets.FloatInput(name="Donor concentration C_ED0 [mg/L]", value=query_float("C_ED0", 5.0), step=0.1)
    epsilon = pn.widgets.FloatInput(name="Biological factor epsilon [mg/L]", value=query_float("epsilon", 0.0), step=0.01)
    run_btn = pn.widgets.Button(name="Run Chu simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(info_card("Run the Chu model to compute plume length."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    def _run(_=None):
        try:
            lmax = chu_lmax(w.value, alpha_th.value, gamma.value, c_ea0.value, c_ed0.value, epsilon.value)
            result_pane.object = metric_card("Plume length", f"{lmax:.2f}")
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot_pane.object = comparison_plot(
                "Chu et al.",
                "Chu model plume length",
                user_x,
                [lmax],
                selected_site_id,
                email,
                "Run Number",
            )
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None

    run_btn.on_click(_run)

    controls = pn.Column(
        "## Chu et al. - Single Simulation",
        "### Manual inputs",
        w,
        alpha_th,
        gamma,
        c_ea0,
        c_ed0,
        epsilon,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, sizing_mode="stretch_both", styles={"gap": "14px"})


def chu_multiple_app():
    default_df = pd.DataFrame([
        {
            "W": query_float("W", 2.0),
            "alpha_Th": query_float("alpha_Th", 0.01),
            "gamma": query_float("gamma", 1.5),
            "C_EA0": query_float("C_EA0", 8.0),
            "C_ED0": query_float("C_ED0", 5.0),
            "epsilon": query_float("epsilon", 0.0),
        }
    ])

    table = pn.widgets.Tabulator(default_df, height=300, sizing_mode="stretch_width", name="Chu scenarios")
    run_btn = pn.widgets.Button(name="Run Chu scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the Chu scenarios to compare plume lengths."), sizing_mode="stretch_width")
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
                    float(row.get("W", 0.0)),
                    float(row.get("alpha_Th", 0.0)),
                    float(row.get("gamma", 0.0)),
                    float(row.get("C_EA0", 0.0)),
                    float(row.get("C_ED0", 0.0)),
                    float(row.get("epsilon", 0.0)),
                ])

            l_vals = compute_chu_multiple(entries)
            result_pane.object = summary_card([
                ("Successful runs", str(len(l_vals))),
                ("Max plume length", f"{max(l_vals):.2f} m"),
            ])
            plot_pane.object = comparison_plot(
                "Chu et al.",
                "Chu model plume length",
                list(range(1, len(l_vals) + 1)),
                l_vals,
                selected_site_id,
                email,
                "Scenario Number",
            )
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None

    run_btn.on_click(_run)

    controls = pn.Column(
        "## Chu et al. - Multiple Simulation",
        "### Manual scenario inputs",
        table,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 380px", "min-width": "300px"},
    )
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, sizing_mode="stretch_both", styles={"gap": "14px"})
