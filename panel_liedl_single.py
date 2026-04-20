import io

import panel as pn

from analytical_models import liedl_lmax
from panel_analytical_common import comparison_plot, error_card, info_card, metric_card, query_float, query_int, query_str
from pdf_report import CASTReport

pn.extension(sizing_mode="stretch_width")


def liedl_single_app():
    m = pn.widgets.FloatInput(name="M (mass per unit width)", value=query_float("M", 3.5), step=0.1)
    alpha_tv = pn.widgets.FloatInput(name="alpha_Tv (transverse dispersivity)", value=query_float("alpha_Tv", 0.001), step=0.0001)
    gamma = pn.widgets.FloatInput(name="gamma (stoichiometric factor)", value=query_float("gamma", 3.5), step=0.1)
    c_ea0 = pn.widgets.FloatInput(name="C_EA0 (acceptor) [mg/L]", value=query_float("C_EA0", 8.0), step=0.1)
    c_ed0 = pn.widgets.FloatInput(name="C_ED0 (donor) [mg/L]", value=query_float("C_ED0", 5.0), step=0.1)
    run_btn = pn.widgets.Button(name="Run Liedl simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(info_card("Run the Liedl model to compute plume length."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Liedl et al. (2005) \u2014 Single Simulation", "Liedl Analytical")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="liedl_single_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            lmax = liedl_lmax(m.value, alpha_tv.value, gamma.value, c_ea0.value, c_ed0.value)
            result_pane.object = metric_card("Plume length", f"{lmax:.2f}")
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot_pane.object = comparison_plot(
                "Liedl et al. (2005)", "Liedl model plume length",
                user_x, [lmax], selected_site_id, email, "Run Number",
            )
            _state.update({
                "parameters": [
                    {"symbol": "M", "name": "Aquifer Thickness", "value": m.value, "unit": "m"},
                    {"symbol": "\u03b1Tv", "name": "Transverse Dispersivity", "value": alpha_tv.value, "unit": "m"},
                    {"symbol": "\u03b3", "name": "Stoichiometric Factor", "value": gamma.value, "unit": "-"},
                    {"symbol": "C_EA0", "name": "Electron Acceptor", "value": c_ea0.value, "unit": "mg/L"},
                    {"symbol": "C_ED0", "name": "Electron Donor", "value": c_ed0.value, "unit": "mg/L"},
                ],
                "outputs": [{"label": "Maximum Plume Length L\u2098\u2090\u2093", "value": f"{lmax:.2f}", "unit": "m"}],
                "plot_data": {"labels": ["Lmax"], "values": [lmax], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — Liedl et al. (2005)"},
            })
            export_btn.visible = True
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None
            export_btn.visible = False

    run_btn.on_click(_run)

    controls = pn.Column(
        "## Liedl et al. (2005) - Single Simulation", "### Manual inputs",
        m, alpha_tv, gamma, c_ea0, c_ed0,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})
