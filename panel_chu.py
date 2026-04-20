import io

import pandas as pd
import panel as pn

from analytical_models import chu_lmax, compute_chu_multiple
from panel_analytical_common import comparison_plot, error_card, info_card, metric_card, query_float, query_int, query_str, summary_card
from pdf_report import CASTReport

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

    _state: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Chu et al. \u2014 Single Simulation", "Chu Analytical")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="chu_single_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            lmax = chu_lmax(w.value, alpha_th.value, gamma.value, c_ea0.value, c_ed0.value, epsilon.value)
            result_pane.object = metric_card("Plume length", f"{lmax:.2f}")
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot_pane.object = comparison_plot("Chu et al.", "Chu model plume length", user_x, [lmax], selected_site_id, email, "Run Number")
            _state.update({
                "parameters": [
                    {"symbol": "W", "name": "Source Width", "value": w.value, "unit": "m"},
                    {"symbol": "\u03b1Th", "name": "Horiz. Trans. Dispersivity", "value": alpha_th.value, "unit": "m"},
                    {"symbol": "\u03b3", "name": "Stoichiometric Ratio", "value": gamma.value, "unit": "-"},
                    {"symbol": "C_EA0", "name": "Electron Acceptor", "value": c_ea0.value, "unit": "mg/L"},
                    {"symbol": "C_ED0", "name": "Electron Donor", "value": c_ed0.value, "unit": "mg/L"},
                    {"symbol": "\u03b5", "name": "Biological Factor", "value": epsilon.value, "unit": "mg/L"},
                ],
                "outputs": [{"label": "Maximum Plume Length L\u2098\u2090\u2093", "value": f"{lmax:.2f}", "unit": "m"}],
                "plot_data": {"labels": ["Lmax"], "values": [lmax], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — Chu et al."},
            })
            export_btn.visible = True
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None
            export_btn.visible = False

    run_btn.on_click(_run)

    controls = pn.Column(
        "## Chu et al. - Single Simulation", "### Manual inputs",
        w, alpha_th, gamma, c_ea0, c_ed0, epsilon,
        sizing_mode="stretch_width", styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs_col = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs_col, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})


def chu_multiple_app():
    default_df = pd.DataFrame([{
        "W": query_float("W", 2.0), "alpha_Th": query_float("alpha_Th", 0.01),
        "gamma": query_float("gamma", 1.5), "C_EA0": query_float("C_EA0", 8.0),
        "C_ED0": query_float("C_ED0", 5.0), "epsilon": query_float("epsilon", 0.0),
    }])

    table = pn.widgets.Tabulator(default_df, height=300, sizing_mode="stretch_width", name="Chu scenarios")
    run_btn = pn.widgets.Button(name="Run Chu scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the Chu scenarios to compare plume lengths."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Chu et al. \u2014 Multiple Simulation", "Chu Analytical")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="chu_multiple_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            df = table.value
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)
            if df.empty:
                raise ValueError("No scenarios available.")
            entries = [[float(row.get(k, 0)) for k in ("W", "alpha_Th", "gamma", "C_EA0", "C_ED0", "epsilon")] for _, row in df.iterrows()]
            l_vals = compute_chu_multiple(entries)
            result_pane.object = summary_card([("Successful runs", str(len(l_vals))), ("Max plume length", f"{max(l_vals):.2f} m")])
            plot_pane.object = comparison_plot("Chu et al.", "Chu model plume length", list(range(1, len(l_vals) + 1)), l_vals, selected_site_id, email, "Scenario Number")
            _state.update({
                "parameters": [{"symbol": f"Sc.{i+1}", "name": f"Scenario {i+1}", "value": f"L={v:.2f}", "unit": "m"} for i, v in enumerate(l_vals)],
                "outputs": [
                    {"label": "Scenarios run", "value": str(len(l_vals)), "unit": ""},
                    {"label": "Max plume length", "value": f"{max(l_vals):.2f}", "unit": "m"},
                    {"label": "Min plume length", "value": f"{min(l_vals):.2f}", "unit": "m"},
                ],
                "plot_data": {"labels": [f"Sc.{i+1}" for i in range(len(l_vals))], "values": l_vals, "ylabel": "Plume Length (m)", "title": "Scenario Comparison — Chu et al."},
            })
            export_btn.visible = True
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None
            export_btn.visible = False

    run_btn.on_click(_run)

    controls = pn.Column("## Chu et al. - Multiple Simulation", "### Manual scenario inputs", table, sizing_mode="stretch_width", styles={"flex": "1 1 380px", "min-width": "300px"})
    outputs_col = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs_col, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})
