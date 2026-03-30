import panel as pn

from analytical_models import ham_lmax
from panel_analytical_common import comparison_plot, error_card, info_card, metric_card, query_float, query_int, query_str

pn.extension(sizing_mode="stretch_width")


def ham_single_app():
    q = pn.widgets.FloatInput(name="Q", value=query_float("Q", 5.0), step=0.1)
    alpha_t = pn.widgets.FloatInput(name="alpha_T", value=query_float("alpha_T", 0.01), step=0.001)
    gamma = pn.widgets.FloatInput(name="gamma", value=query_float("gamma", 3.5), step=0.1)
    c_ea0 = pn.widgets.FloatInput(name="EA0 (Electron Acceptor)", value=query_float("C_EA0", 8.0), step=0.1)
    c_ed0 = pn.widgets.FloatInput(name="ED0 (Electron Donor)", value=query_float("C_ED0", 5.0), step=0.1)
    run_btn = pn.widgets.Button(name="Run Ham simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(info_card("Run the Ham model to compute plume length."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    def _run(_=None):
        try:
            lmax = ham_lmax(q.value, alpha_t.value, gamma.value, c_ea0.value, c_ed0.value)
            result_pane.object = metric_card("Plume length", f"{lmax:.2f}")
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot_pane.object = comparison_plot("Ham et al.", "Ham model plume length", user_x, [lmax], selected_site_id, email, "Run Number")
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None

    run_btn.on_click(_run)

    controls = pn.Column("## Ham et al. - Single Simulation", "### Manual inputs", q, alpha_t, gamma, c_ea0, c_ed0, sizing_mode="stretch_width", styles={"flex": "1 1 320px", "min-width": "280px"})
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, sizing_mode="stretch_both", styles={"gap": "14px"})
