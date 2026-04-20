import io

import panel as pn

from analytical_models import cirpka_lmax, cirpka_domain_length
from panel_analytical_common import (
    comparison_plot, error_card, info_card, metric_card, summary_card,
    query_float, query_int, query_str,
)
from pdf_report import CASTReport

pn.extension(sizing_mode="stretch_width")


def cirpka_single_app():
    sw = pn.widgets.FloatInput(name="Source Width Sw [m]", value=query_float("Sw", 10.0), step=0.5)
    alpha_th = pn.widgets.FloatInput(
        name="Horizontal Transverse Dispersivity \u03b1Th [m]",
        value=query_float("alpha_Th", 0.1), step=0.01,
    )
    ca = pn.widgets.FloatInput(name="Electron Acceptor CA [mg/L]", value=query_float("C_A", 8.0), step=0.1)
    cd = pn.widgets.FloatInput(name="Electron Donor CD [mg/L]", value=query_float("C_D", 5.0), step=0.1)
    gamma = pn.widgets.FloatInput(name="Stoichiometric Ratio \u03b3 [-]", value=query_float("gamma", 3.5), step=0.1)
    run_btn = pn.widgets.Button(name="Compute Plume Length", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(info_card("Enter parameters and click Compute."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)

    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Cirpka et al. (2005) \u2014 Single Simulation", "Cirpka Analytical")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="cirpka_single_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            if sw.value <= 0:
                raise ValueError("Source width Sw must be positive.")
            if alpha_th.value <= 0:
                raise ValueError("Dispersivity \u03b1Th must be positive.")
            if ca.value <= 0:
                raise ValueError("Electron acceptor CA must be positive.")
            if cd.value <= 0:
                raise ValueError("Electron donor CD must be positive.")

            lmax = cirpka_lmax(sw.value, alpha_th.value, gamma.value, ca.value, cd.value)
            ld = cirpka_domain_length(lmax)

            result_pane.object = summary_card(
                [("Maximum Plume Length L\u2098\u2090\u2093", f"{lmax:.2f} m"),
                 ("Domain Length L\u1d30", f"{ld:.2f} m")],
                title="Cirpka et al. (2005) Result",
            )
            plot_pane.object = comparison_plot(
                "Cirpka et al. (2005)",
                "Cirpka L\u2098\u2090\u2093",
                [selected_site_id if selected_site_id > 0 else 1],
                [lmax],
                selected_site_id,
                email,
                "Run Number",
            )
            _state.update({
                "parameters": [
                    {"symbol": "Sw", "name": "Source Width", "value": sw.value, "unit": "m"},
                    {"symbol": "\u03b1Th", "name": "Horiz. Trans. Dispersivity", "value": alpha_th.value, "unit": "m"},
                    {"symbol": "\u03b3", "name": "Stoichiometric Ratio", "value": gamma.value, "unit": "-"},
                    {"symbol": "CA", "name": "Electron Acceptor", "value": ca.value, "unit": "mg/L"},
                    {"symbol": "CD", "name": "Electron Donor", "value": cd.value, "unit": "mg/L"},
                ],
                "outputs": [
                    {"label": "Maximum Plume Length L\u2098\u2090\u2093", "value": f"{lmax:.2f}", "unit": "m"},
                    {"label": "Domain Length LD", "value": f"{ld:.2f}", "unit": "m"},
                ],
                "plot_data": {"labels": ["Lmax", "Domain LD"], "values": [lmax, ld], "ylabel": "Length (m)", "title": "Plume & Domain Length — Cirpka et al. (2005)"},
            })
            export_btn.visible = True
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None
            export_btn.visible = False

    run_btn.on_click(_run)

    controls = pn.Column(
        "## Cirpka et al. (2005) \u2014 Single Simulation",
        "### Model Parameters",
        sw, alpha_th, ca, cd, gamma,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs = pn.Column(
        plot_pane,
        sizing_mode="stretch_both",
        styles={"flex": "2 1 540px", "min-width": "340px"},
    )
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})
