import panel as pn

from empirical_models import maier_lmax
from panel_empirical_common import comparison_plot, error_card, info_card, metric_card, query_float, query_int, query_str

pn.extension(sizing_mode="stretch_width")


def maier_single_app():
    w_M = pn.widgets.FloatInput(name="Aquifer thickness M", value=query_float("M", 5.0), step=0.1)
    w_tv = pn.widgets.FloatInput(name="Vertical transverse dispersivity tv", value=query_float("tv", 0.01), step=0.001)
    w_g = pn.widgets.FloatInput(name="Stoichiometry coefficient g", value=query_float("g", 3.5), step=0.1)
    w_Ca = pn.widgets.FloatInput(name="Contaminant concentration Ca", value=query_float("Ca", 8.0), step=0.5)
    w_Cd = pn.widgets.FloatInput(name="Reactant concentration Cd", value=query_float("Cd", 5.0), step=0.5)
    run_btn = pn.widgets.Button(name="Run Maier simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(info_card("Run the Maier & Grathwohl model to compute plume length."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    def _run(_=None):
        try:
            lmax_current = maier_lmax(w_M.value, w_tv.value, w_g.value, w_Ca.value, w_Cd.value)
            result_pane.object = metric_card("Plume length", f"{lmax_current:.2f}")
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot_pane.object = comparison_plot(
                "Maier and Grathwohl (2005)",
                "Maier model plume length",
                user_x,
                [lmax_current],
                selected_site_id,
                email,
                "Run Number",
            )
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None

    run_btn.on_click(_run)

    controls = pn.Column(
        "## Maier & Grathwohl - Single Simulation",
        "### Manual inputs",
        w_M,
        w_tv,
        w_g,
        w_Ca,
        w_Cd,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, sizing_mode="stretch_both", styles={"gap": "14px"})
