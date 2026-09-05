"""Koehler et al. (2024) single simulation.

Two second-order polynomials, three inputs between them: Eq. (13) gives the
maximum plume length from lambda_e and v, Eq. (14) the time to reach it from
lambda_e and Gamma. So this page shows two numbers where every other single
page shows one; the layout is otherwise the shared one.

Note gamma: here it is the SOURCE DECAY rate constant [1/yr], the quantity
BIOSCREEN calls sourceDecayCoefficient_gamma - NOT the stoichiometric
coefficient the Liedl/Cirpka/Maier family means by the same letter.
"""
import io

import panel as pn

from panel_auth import authenticated_email

from kohler_model import kohler_model
from panel_analytical_common import (
    baseline_delta, comparison_plot, error_card, explore_sliders, output_only_layout, info_card,
    metric_card, query_float, query_int,
)
from pdf_report import CASTReport

pn.extension(sizing_mode="stretch_width")


def _warning_card(messages) -> str:
    """The out-of-range notes kohler_model returns, under the two results.

    Amber, not the red of error_card: an extrapolation is a number the paper
    itself publishes (both its field sites sit outside the fitted lambda_e
    band), not a failed run.
    """
    if not messages:
        return ""
    items = "".join(f"<li style='margin:2px 0;'>{message}</li>" for message in messages)
    return (
        '<div style="background:#fffaeb;border:1px solid #fedf89;border-radius:10px;'
        'padding:14px 18px;margin-top:12px;box-shadow:0 1px 3px rgba(16,24,40,0.05);">'
        '<div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;'
        'text-transform:uppercase;color:#b54708;margin-bottom:6px;">Outside the fitted range</div>'
        f'<ul style="margin:0;padding-left:18px;font-size:0.92rem;color:#7a4708;">{items}</ul>'
        '</div>'
    )


def kohler_single_app():
    lam = pn.widgets.FloatInput(
        name="First-order Decay Coefficient \u03bb_e [1/a]",
        value=query_float("lam", 0.2), step=0.01, start=0.0)
    v = pn.widgets.FloatInput(
        name="Groundwater Seepage Velocity v [m/a]",
        value=query_float("v", 20.0), step=1.0, start=0.000001)
    # Same bounds BIOSCREEN gives the same quantity. Source decay, not stoichiometry.
    gamma = pn.widgets.FloatInput(
        name="Source Decay Coefficient \u0393 [1/a]",
        value=query_float("gamma", 0.5), step=0.01, start=0.0, end=1.0)
    run_btn = pn.widgets.Button(name="Run K\u00f6hler simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(
        info_card("Run the K\u00f6hler model to compute plume length and the time to reach it."),
        sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = authenticated_email()
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}
    _baseline: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("K\u00f6hler et al. (2024) \u2014 Single Simulation", "K\u00f6hler et al. (2024)")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="kohler_single_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            out = kohler_model(lam.value, v.value, gamma.value)
            lmax, tlmax = out["Lmax"], out["TLmax"]
            _baseline.setdefault("lmax", lmax)
            _baseline.setdefault("tlmax", tlmax)
            # One card, two rows: the model gives two numbers, not two results.
            result_pane.object = (
                metric_card(
                    "Maximum Plume Length L\u2098\u2090\u2093", f"{lmax:.2f}",
                    delta=baseline_delta(lmax, _baseline["lmax"]),
                    extra_rows=[(
                        "Time to Maximum Extent T_Lmax", f"{tlmax:.2f}", "a",
                        baseline_delta(tlmax, _baseline["tlmax"]),
                    )],
                )
                + _warning_card(out["warnings"])
            )
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot, plot_data = comparison_plot(
                "K\u00f6hler et al. (2024)", "K\u00f6hler model plume length",
                user_x, [lmax], selected_site_id, email, "Run Number",
                return_data=True, frame=_baseline,
            )
            plot_pane.object = plot
            _state.update({
                "parameters": [
                    {"symbol": "lambda_e", "name": "First-order Decay Coefficient", "value": lam.value, "unit": "1/yr"},
                    {"symbol": "v", "name": "Groundwater Seepage Velocity", "value": v.value, "unit": "m/yr"},
                    {"symbol": "Gamma", "name": "Source Decay Coefficient", "value": gamma.value, "unit": "1/yr"},
                ],
                "outputs": [
                    {"label": "Maximum Plume Length L\u2098\u2090\u2093", "value": f"{lmax:.2f}", "unit": "m"},
                    {"label": "Time to Maximum Extent T_Lmax", "value": f"{tlmax:.2f}", "unit": "yr"},
                ],
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
        return output_only_layout(
            result_pane, plot_pane,
            explore_sliders([("lam", lam), ("v", v), ("gamma", gamma)], _run),
        )

    controls = pn.Column(
        "### Manual inputs",
        lam, v, gamma,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})
