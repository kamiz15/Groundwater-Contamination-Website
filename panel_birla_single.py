import io

import pandas as pd
import panel as pn

from empirical_models import birla_lmax
from panel_empirical_common import comparison_plot, error_card, info_card, metric_card, query_float, query_int, query_str, summary_card
from pdf_report import CASTReport

pn.extension("tabulator", sizing_mode="stretch_width")


def birla_single_app():
    w_M = pn.widgets.FloatInput(name="Aquifer thickness M", value=query_float("M", 2.0), step=0.1)
    w_tv = pn.widgets.FloatInput(name="Vertical transverse dispersivity tv", value=query_float("tv", 0.001), step=0.0005)
    w_g = pn.widgets.FloatInput(name="Stoichiometry coefficient g", value=query_float("g", 3.5), step=0.1)
    w_Ca = pn.widgets.FloatInput(name="Contaminant concentration Ca", value=query_float("Ca", 8.0), step=0.5)
    w_Cd = pn.widgets.FloatInput(name="Reactant concentration Cd", value=query_float("Cd", 5.0), step=0.5)
    w_R = pn.widgets.FloatInput(name="Recharge rate R", value=query_float("R", 1.0), step=0.1)
    run_btn = pn.widgets.Button(name="Run Birla simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(info_card("Run the Birla et al. model to compute plume length."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Birla et al. \u2014 Single Simulation", "Birla Empirical")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="birla_single_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            lmax_current = birla_lmax(w_M.value, w_tv.value, w_g.value, w_Ca.value, w_Cd.value, w_R.value)
            result_pane.object = metric_card("Plume length", f"{lmax_current:.2f}")
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot_pane.object = comparison_plot("Birla et al. (2020)", "Birla model plume length", user_x, [lmax_current], selected_site_id, email, "Run Number")
            _state.update({
                "parameters": [
                    {"symbol": "M", "name": "Aquifer Thickness", "value": w_M.value, "unit": "m"},
                    {"symbol": "tv", "name": "Vert. Trans. Dispersivity", "value": w_tv.value, "unit": "m"},
                    {"symbol": "g", "name": "Stoichiometry Coefficient", "value": w_g.value, "unit": "-"},
                    {"symbol": "Ca", "name": "Contaminant Concentration", "value": w_Ca.value, "unit": "mg/L"},
                    {"symbol": "Cd", "name": "Reactant Concentration", "value": w_Cd.value, "unit": "mg/L"},
                    {"symbol": "R", "name": "Recharge Rate", "value": w_R.value, "unit": "m/yr"},
                ],
                "outputs": [{"label": "Maximum Plume Length L\u2098\u2090\u2093", "value": f"{lmax_current:.2f}", "unit": "m"}],
                "plot_data": {"labels": ["Lmax"], "values": [lmax_current], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — Birla et al. (2020)"},
            })
            export_btn.visible = True
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None
            export_btn.visible = False

    run_btn.on_click(_run)

    controls = pn.Column("## Birla et al. - Single Simulation", "### Manual inputs", w_M, w_tv, w_g, w_Ca, w_Cd, w_R, sizing_mode="stretch_width", styles={"flex": "1 1 320px", "min-width": "280px"})
    outputs_col = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs_col, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})
