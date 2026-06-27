import panel as pn

from panel_auth import authenticated_email

from analytical_models import cirpka_domain_length, cirpka_lmax
from panel_analytical_common import (
    comparison_plot,
    error_card,
    query_float,
    query_int,
    summary_card,
)

pn.extension(sizing_mode="stretch_width")


def cirpka_single_app():
    sw = query_float("Sw", 10.0)
    alpha_th = query_float("alpha_Th", 0.1)
    ca = query_float("C_A", 8.0)
    cd = query_float("C_D", 5.0)
    gamma = query_float("gamma", 3.5)
    email = authenticated_email()
    selected_site_id = query_int("site_id", 0)

    result_pane = pn.pane.HTML(sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)

    if not query_int("run", 0):
        result_pane.object = summary_card(
            [("Status", "Ready")],
            title="Output Waiting",
        )
    else:
        try:
            if sw <= 0:
                raise ValueError("Source width Sw must be positive.")
            if alpha_th <= 0:
                raise ValueError("Dispersivity alpha Th must be positive.")
            if ca <= 0:
                raise ValueError("Electron acceptor CA must be positive.")
            if cd <= 0:
                raise ValueError("Electron donor CD must be positive.")

            lmax = cirpka_lmax(sw, alpha_th, gamma, ca, cd)
            ld = cirpka_domain_length(lmax)
            result_pane.object = summary_card(
                [
                    ("Maximum Plume Length Lmax", f"{lmax:.2f} m"),
                    ("Domain Length LD", f"{ld:.2f} m"),
                ],
                title="Cirpka et al. (2005) Result",
            )
            plot_pane.object = comparison_plot(
                "Cirpka et al. (2005)",
                "Cirpka Lmax",
                [selected_site_id if selected_site_id > 0 else 1],
                [lmax],
                selected_site_id,
                email,
                "Run Number",
            )
        except Exception as exc:
            result_pane.object = error_card(exc)
            plot_pane.object = None

    return pn.Column(
        result_pane,
        plot_pane,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
