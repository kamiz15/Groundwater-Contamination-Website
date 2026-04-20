import io

import pandas as pd
import panel as pn

from empirical_models import maier_lmax
from panel_empirical_common import comparison_plot, error_card, info_card, query_float, query_int, query_str, summary_card
from pdf_report import CASTReport

pn.extension("tabulator", sizing_mode="stretch_width")


def maier_multiple_app():
    default_df = pd.DataFrame([{
        "M": query_float("M", 5.0), "tv": query_float("tv", 0.01),
        "g": query_float("g", 3.5), "Ca": query_float("Ca", 8.0),
        "Cd": query_float("Cd", 5.0),
    }])

    table = pn.widgets.Tabulator(default_df, height=300, sizing_mode="stretch_width", name="Maier scenarios")
    run_btn = pn.widgets.Button(name="Run Maier scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the Maier scenarios to compare plume lengths."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Maier & Grathwohl \u2014 Multiple Simulation", "Maier Empirical")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="maier_multiple_report.pdf",
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
            lengths = [maier_lmax(float(row.get("M", 0)), float(row.get("tv", 0)), float(row.get("g", 0)), float(row.get("Ca", 0)), float(row.get("Cd", 0))) for _, row in df.iterrows()]
            result_pane.object = summary_card([("Successful runs", str(len(lengths))), ("Max plume length", f"{max(lengths):.2f} m")])
            plot_pane.object = comparison_plot("Maier and Grathwohl (2005)", "Maier model plume length", list(range(1, len(lengths) + 1)), lengths, selected_site_id, email, "Scenario Number")
            _state.update({
                "parameters": [{"symbol": f"Sc.{i+1}", "name": f"Scenario {i+1}", "value": f"L={v:.2f}", "unit": "m"} for i, v in enumerate(lengths)],
                "outputs": [
                    {"label": "Scenarios run", "value": str(len(lengths)), "unit": ""},
                    {"label": "Max plume length", "value": f"{max(lengths):.2f}", "unit": "m"},
                    {"label": "Min plume length", "value": f"{min(lengths):.2f}", "unit": "m"},
                ],
                "plot_data": {"labels": [f"Sc.{i+1}" for i in range(len(lengths))], "values": lengths, "ylabel": "Plume Length (m)", "title": "Scenario Comparison — Maier & Grathwohl"},
            })
            export_btn.visible = True
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None
            export_btn.visible = False

    run_btn.on_click(_run)

    controls = pn.Column("## Maier & Grathwohl - Multiple Simulation", "### Manual scenario inputs", table, sizing_mode="stretch_width", styles={"flex": "1 1 380px", "min-width": "300px"})
    outputs_col = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs_col, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})
