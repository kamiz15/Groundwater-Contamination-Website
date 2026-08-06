import io

import panel as pn

from panel_auth import authenticated_email

from analytical_models import ham_lmax
from panel_analytical_common import (
    baseline_delta, comparison_plot, error_card, explore_sliders, info_card,
    metric_card, query_float, query_int,
)
from pdf_report import CASTReport

pn.extension(sizing_mode="stretch_width")


def ham_single_app():
    q = pn.widgets.FloatInput(name="Source Flux q [m\u00b2/yr]", value=query_float("Q", 5.0), step=0.1)
    alpha_t = pn.widgets.FloatInput(name="Horizontal Transverse Dispersivity \u03b1_Th [m]", value=query_float("alpha_T", 0.01), step=0.001)
    gamma = pn.widgets.FloatInput(name="Stoichiometry Ratio \u03b3 [-]", value=query_float("gamma", 3.5), step=0.1)
    c_ea0 = pn.widgets.FloatInput(name="Acceptor Concentration at Source C_A^0 [mg/L]", value=query_float("C_EA0", 8.0), step=0.1)
    c_ed0 = pn.widgets.FloatInput(name="Donor Concentration at Source C_D^0 [mg/L]", value=query_float("C_ED0", 5.0), step=0.1)
    run_btn = pn.widgets.Button(name="Run Ham simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(info_card("Run the Ham model to compute plume length."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = authenticated_email()
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}
    _baseline: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Ham et al. (2004) \u2014 Single Simulation", "Ham et al. (2004)")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="ham_single_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            lmax = ham_lmax(q.value, alpha_t.value, gamma.value, c_ea0.value, c_ed0.value)
            _baseline.setdefault("lmax", lmax)
            result_pane.object = metric_card(
                "Maximum Plume Length Lₘₐₓ", f"{lmax:.2f}",
                delta=baseline_delta(lmax, _baseline["lmax"]),
            )
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot, plot_data = comparison_plot("Ham et al. (2004)", "Ham model plume length", user_x, [lmax], selected_site_id, email, "Run Number", return_data=True, frame=_baseline)
            plot_pane.object = plot
            _state.update({
                "parameters": [
                    {"symbol": "q", "name": "Source Flux", "value": q.value, "unit": "m\u00b2/yr"},
                    {"symbol": "alpha_Th", "name": "Horizontal Transverse Dispersivity", "value": alpha_t.value, "unit": "m"},
                    {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma.value, "unit": "-"},
                    {"symbol": "C_A0", "name": "Acceptor Concentration at Source", "value": c_ea0.value, "unit": "mg/L"},
                    {"symbol": "C_D0", "name": "Donor Concentration at Source", "value": c_ed0.value, "unit": "mg/L"},
                ],
                "outputs": [{"label": "Maximum Plume Length L\u2098\u2090\u2093", "value": f"{lmax:.2f}", "unit": "m"}],
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
            explore_sliders([("Q", q), ("alpha_T", alpha_t), ("gamma", gamma)], _run),
            sizing_mode="stretch_width", styles={"gap": "14px"},
        )

    controls = pn.Column("### Manual inputs", q, alpha_t, gamma, c_ea0, c_ed0, sizing_mode="stretch_width", styles={"flex": "1 1 320px", "min-width": "280px"})
    outputs_col = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs_col, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})
