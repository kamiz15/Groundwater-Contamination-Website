import io

import panel as pn

from panel_auth import authenticated_email

from bioscreen_model import bio
from panel_analytical_common import (
    baseline_delta, comparison_plot, error_card, explore_sliders, info_card,
    metric_card, query_float, query_int,
)
from panel_model_scenarios import scenario_app
from pdf_report import CASTReport

pn.extension(sizing_mode="stretch_width")


def _base_widgets():
    cthres = pn.widgets.FloatInput(name="Threshold Contaminant Concentration C_thres [mg/L]", value=query_float("Cthres", 5e-5), step=1e-5, start=1e-8)
    time = pn.widgets.IntInput(name="Simulation Time t [a]", value=query_int("time", 20), start=1, end=1000)
    h = pn.widgets.FloatSlider(name="Source Thickness T_s [m]", value=query_float("H", 6.1), start=0.1, end=50, step=0.1)
    c0 = pn.widgets.FloatSlider(name="Contamination Concentration C_D^0 [mg/L]", value=query_float("c0", 106.35), start=0.1, end=1000, step=1)
    w = pn.widgets.FloatSlider(name="Source Width S_W [m]", value=query_float("W", 20), start=0.1, end=1000, step=0.1)
    v = pn.widgets.FloatInput(name="Groundwater Seepage Velocity v [m/a]", value=query_float("v", 292), start=10, end=1000)
    ax = pn.widgets.FloatSlider(name="Longitudinal Dispersivity α_L [m]", value=query_float("ax", 10.7), start=1, end=100, step=0.5)
    ay = pn.widgets.FloatInput(name="Horizontal Transverse Dispersivity α_Th [m]", value=query_float("ay", 1.1), start=0.1, end=10)
    az = pn.widgets.FloatInput(name="Vertical Transverse Dispersivity α_Tv [m]", value=query_float("az", 0.11), start=0.01, end=1)
    df = pn.widgets.FloatInput(name="Diffusion Coefficient D_f [m²/a]", value=query_float("Df", 0.0), start=0.0, end=0.1)
    r = pn.widgets.FloatInput(name="Retardation Factor R [-]", value=query_float("R", 1.0), start=0.01)
    gamma = pn.widgets.FloatInput(name="Source Decay Coefficient Γ [1/a]", value=query_float("gamma", 0.0), start=0.0, end=1.0)
    lam = pn.widgets.FloatSlider(name="First-order Decay Coefficient λ_e [1/a]", value=query_float("lam", 0.445), start=0.0, end=1.0, step=0.01)
    ng_default = query_int("ng", 60)
    if ng_default not in [4, 5, 6, 10, 15, 20, 60, 104, 256]:
        ng_default = 60
    ng = pn.widgets.Select(name="Number of Gauss Points n_g [-]", value=ng_default, options=[4, 5, 6, 10, 15, 20, 60, 104, 256])
    return cthres, time, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng


def bioscreen_single_app():
    cthres, time, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng = _base_widgets()
    run_btn = pn.widgets.Button(name="Run BIOSCREEN simulation", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the BIOSCREEN model to compute plume length."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = authenticated_email()
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}
    _baseline: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("BIOSCREEN-AT 3D \u2014 Single Simulation", "BIOSCREEN-AT 3D")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="bioscreen_single_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            lmax = float(bio(cthres.value, time.value, h.value, c0.value, w.value, v.value, ax.value, ay.value, az.value, df.value, r.value, gamma.value, lam.value, int(ng.value)))
            _baseline.setdefault("lmax", lmax)
            result_pane.object = metric_card(
                "Maximum Plume Length Lₘₐₓ", f"{lmax:.2f}",
                delta=baseline_delta(lmax, _baseline["lmax"]),
            )
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot, plot_data = comparison_plot(
                "BIOSCREEN-AT 3D",
                "BIOSCREEN plume length",
                user_x,
                [lmax],
                selected_site_id,
                email,
                "Run Number",
                return_data=True,
                frame=_baseline,
            )
            plot_pane.object = plot
            _state.update({
                "parameters": [
                    {"symbol": "C_thres", "name": "Threshold Contaminant Concentration", "value": cthres.value, "unit": "mg/L"},
                    {"symbol": "t", "name": "Time", "value": time.value, "unit": "yr"},
                    {"symbol": "T_s", "name": "Source Thickness", "value": h.value, "unit": "m"},
                    {"symbol": "C_D0", "name": "Contamination Concentration", "value": c0.value, "unit": "mg/L"},
                    {"symbol": "S_W", "name": "Source Width", "value": w.value, "unit": "m"},
                    {"symbol": "v", "name": "Groundwater Seepage Velocity", "value": v.value, "unit": "m/yr"},
                    {"symbol": "alpha_L", "name": "Longitudinal Dispersivity", "value": ax.value, "unit": "m"},
                    {"symbol": "alpha_Th", "name": "Horizontal Transverse Dispersivity", "value": ay.value, "unit": "m"},
                    {"symbol": "alpha_Tv", "name": "Vertical Transverse Dispersivity", "value": az.value, "unit": "m"},
                    {"symbol": "D_f", "name": "Diffusion Coefficient", "value": df.value, "unit": "m\u00b2/yr"},
                    {"symbol": "R", "name": "Retardation Factor", "value": r.value, "unit": "-"},
                    {"symbol": "Gamma", "name": "Source Decay Coefficient", "value": gamma.value, "unit": "1/yr"},
                    {"symbol": "lambda_e", "name": "First-order Decay Coefficient", "value": lam.value, "unit": "1/yr"},
                    {"symbol": "n_g", "name": "Number of Gauss Points", "value": ng.value, "unit": "-"},
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
            explore_sliders([("H", h), ("W", w), ("ax", ax), ("lam", lam)], _run),
            sizing_mode="stretch_width", styles={"gap": "14px"},
        )

    controls = pn.Column(
        "### Manual inputs",
        cthres, time, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})


def bioscreen_multiple_app():
    """Multiple simulation: one run per site picked in the sidebar."""
    return scenario_app("bioscreen")
