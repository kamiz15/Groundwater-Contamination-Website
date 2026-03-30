import panel as pn

from analytical_models import liedl3d_lmax
from panel_analytical_common import comparison_plot, error_card, info_card, metric_card, query_float, query_int, query_str

pn.extension(sizing_mode="stretch_width")


def liedl3d_single_app():
    m = pn.widgets.FloatInput(name="Source thickness M [m]", value=query_float("M", 10.0), step=0.1)
    alpha_th = pn.widgets.FloatInput(name="Horizontal transverse dispersivity alpha_Th [m]", value=query_float("alpha_Th", 0.01), step=0.001)
    alpha_tv = pn.widgets.FloatInput(name="Vertical transverse dispersivity alpha_Tv [m]", value=query_float("alpha_Tv", 0.01), step=0.001)
    w = pn.widgets.FloatInput(name="Source width W [m]", value=query_float("W", 7.0), step=0.1)
    cthres = pn.widgets.FloatInput(name="Threshold concentration Cthres [mg/L]", value=query_float("Cthres", 0.5), step=0.01)
    c_ea0 = pn.widgets.FloatInput(name="Partner reactant concentration C_EA0 [mg/L]", value=query_float("C_EA0", 8.0), step=0.1)
    c_ed0 = pn.widgets.FloatInput(name="Contaminant concentration C_ED0 [mg/L]", value=query_float("C_ED0", 5.0), step=0.1)
    gamma = pn.widgets.FloatInput(name="Stoichiometric ratio gamma", value=query_float("gamma", 3.0), step=0.1)
    run_btn = pn.widgets.Button(name="Run Liedl 3D simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(info_card("Run the Liedl 3D model to compute plume length."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    def _run(_=None):
        try:
            lmax = liedl3d_lmax(m.value, alpha_th.value, alpha_tv.value, w.value, cthres.value, c_ea0.value, c_ed0.value, gamma.value)
            result_pane.object = metric_card("Plume length", f"{lmax:.2f}")
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot_pane.object = comparison_plot(
                "Liedl 3D",
                "Liedl 3D model plume length",
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
        "## Liedl 3D - Single Simulation",
        "### Manual inputs",
        m,
        alpha_th,
        alpha_tv,
        w,
        cthres,
        c_ea0,
        c_ed0,
        gamma,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs = pn.Column(
        plot_pane,
        sizing_mode="stretch_both",
        styles={"flex": "2 1 540px", "min-width": "340px"},
    )
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, sizing_mode="stretch_both", styles={"gap": "14px"})
