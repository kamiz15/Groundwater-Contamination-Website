import io

import pandas as pd
import panel as pn

from analytical_models import compute_liedl3d_multiple
from panel_analytical_common import comparison_plot, error_card, info_card, query_float, query_int, query_str, summary_card
from pdf_report import CASTReport

pn.extension("tabulator", sizing_mode="stretch_width")


def liedl3d_multiple_app():
    init_df = pd.DataFrame([{
        "M": query_float("M", 10.0), "alpha_Th": query_float("alpha_Th", 0.01),
        "alpha_Tv": query_float("alpha_Tv", 0.01), "W": query_float("W", 7.0),
        "Cthres": query_float("Cthres", 0.5), "C_EA0": query_float("C_EA0", 8.0),
        "C_ED0": query_float("C_ED0", 5.0), "gamma": query_float("gamma", 3.0),
    }])

    table = pn.widgets.Tabulator(init_df, height=300, sizing_mode="stretch_width", name="Liedl 3D scenarios")
    run_btn = pn.widgets.Button(name="Run Liedl 3D scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the Liedl 3D scenarios to compare plume lengths."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Liedl 3D \u2014 Multiple Simulation", "Liedl 3D Analytical")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="liedl3d_multiple_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            df = table.value
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)
            if df.empty:
                raise ValueError("No scenarios available.")
            entries = [[float(row.get(k, 0)) for k in ("M", "alpha_Th", "alpha_Tv", "W", "Cthres", "C_EA0", "C_ED0", "gamma")] for _, row in df.iterrows()]
            l_vals = compute_liedl3d_multiple(entries)
            result_pane.object = summary_card([("Successful runs", str(len(l_vals))), ("Max plume length", f"{max(l_vals):.2f} m")])
            plot_pane.object = comparison_plot("Liedl 3D", "Liedl 3D model plume length", list(range(1, len(l_vals) + 1)), l_vals, selected_site_id, email, "Scenario Number")
            _state.update({
                "parameters": [{"symbol": f"Sc.{i+1}", "name": f"Scenario {i+1}", "value": f"L={v:.2f}", "unit": "m"} for i, v in enumerate(l_vals)],
                "outputs": [
                    {"label": "Scenarios run", "value": str(len(l_vals)), "unit": ""},
                    {"label": "Max plume length", "value": f"{max(l_vals):.2f}", "unit": "m"},
                    {"label": "Min plume length", "value": f"{min(l_vals):.2f}", "unit": "m"},
                ],
                "plot_data": {"labels": [f"Sc.{i+1}" for i in range(len(l_vals))], "values": l_vals, "ylabel": "Plume Length (m)", "title": "Scenario Comparison — Liedl 3D"},
            })
            export_btn.visible = True
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None
            export_btn.visible = False

    run_btn.on_click(_run)

    controls = pn.Column("## Liedl 3D - Multiple Simulation", "### Manual scenario inputs", table, sizing_mode="stretch_width", styles={"flex": "1 1 380px", "min-width": "300px"})
    outputs_col = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs_col, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})
