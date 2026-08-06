import io

import pandas as pd
import panel as pn

from panel_auth import authenticated_email

from empirical_models import birla_lmax
from panel_empirical_common import (
    baseline_delta, comparison_plot, error_card, explore_sliders, info_card,
    metric_card, query_float, query_int, summary_card,
)
from pdf_report import CASTReport

pn.extension("tabulator", sizing_mode="stretch_width")


def birla_single_app():
    w_M = pn.widgets.FloatInput(name="Source Thickness S_T [m]", value=query_float("M", 2.0), step=0.1)
    w_tv = pn.widgets.FloatInput(name="Vertical Transverse Dispersivity \u03b1_Tv [m]", value=query_float("tv", 0.001), step=0.0005)
    w_g = pn.widgets.FloatInput(name="Stoichiometry Coefficient \u03b3 [-]", value=query_float("g", 3.5), step=0.1)
    w_Ca = pn.widgets.FloatInput(name="Acceptor Concentration at Source C_A^0 [mg/L]", value=query_float("Ca", 8.0), step=0.5)
    w_Cd = pn.widgets.FloatInput(name="Donor Concentration at Source C_D^0 [mg/L]", value=query_float("Cd", 5.0), step=0.5)
    w_R = pn.widgets.FloatInput(name="Recharge Rate R_c [m/yr]", value=query_float("R", 1.0), step=0.1)
    run_btn = pn.widgets.Button(name="Run Birla simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(info_card("Run the Birla et al. model to compute plume length."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = authenticated_email()
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}
    _baseline: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Birla et al. (2020) \u2014 Single Simulation", "Birla et al. (2020)")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="birla_single_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            lmax_current = birla_lmax(w_M.value, w_tv.value, w_g.value, w_Ca.value, w_Cd.value, w_R.value)
            _baseline.setdefault("lmax", lmax_current)
            result_pane.object = metric_card(
                "Maximum Plume Length L_max", f"{lmax_current:.2f}",
                delta=baseline_delta(lmax_current, _baseline["lmax"]),
            )
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot, plot_data = comparison_plot("Birla et al. (2020)", "Birla model plume length", user_x, [lmax_current], selected_site_id, email, "Run Number", return_data=True, frame=_baseline)
            plot_pane.object = plot
            _state.update({
                "parameters": [
                    {"symbol": "S_T", "name": "Source Thickness", "value": w_M.value, "unit": "m"},
                    {"symbol": "alpha_Tv", "name": "Vertical Transverse Dispersivity", "value": w_tv.value, "unit": "m"},
                    {"symbol": "R_c", "name": "Recharge Rate", "value": w_R.value, "unit": "m/yr"},
                    {"symbol": "gamma", "name": "Stoichiometry Ratio", "value": w_g.value, "unit": "-"},
                    {"symbol": "C_A0", "name": "Acceptor Concentration at Source", "value": w_Ca.value, "unit": "mg/L"},
                    {"symbol": "C_D0", "name": "Donor Concentration at Source", "value": w_Cd.value, "unit": "mg/L"},
                ],
                "outputs": [{"label": "Maximum Plume Length L\u2098\u2090\u2093", "value": f"{lmax_current:.2f}", "unit": "m"}],
                "plot_data": plot_data,
            })
            export_btn.visible = True
        except Exception as exc:
            result_pane.object = error_card(exc)
            plot_pane.object = None
            export_btn.visible = False

    run_btn.on_click(_run)
    if query_int("output_only", 0):
        if query_int("run", 0):
            _run()
        return pn.Column(
            result_pane, plot_pane,
            explore_sliders([("M", w_M), ("tv", w_tv), ("R", w_R)], _run),
            sizing_mode="stretch_width", styles={"gap": "14px"},
        )

    controls = pn.Column("### Manual inputs", w_M, w_tv, w_g, w_Ca, w_Cd, w_R, sizing_mode="stretch_width", styles={"flex": "1 1 320px", "min-width": "280px"})
    outputs_col = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs_col, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})
