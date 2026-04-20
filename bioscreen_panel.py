import io

import pandas as pd
import panel as pn

from bioscreen_model import bio
from panel_analytical_common import comparison_plot, error_card, info_card, metric_card, query_float, query_int, query_str, summary_card
from pdf_report import CASTReport

pn.extension("tabulator", sizing_mode="stretch_width")


def _base_widgets():
    cthres = pn.widgets.FloatInput(name="Threshold concentration Cthres (mg/L)", value=query_float("Cthres", 5e-5), step=1e-5, start=1e-8)
    time = pn.widgets.IntInput(name="Time (years)", value=query_int("time", 20), start=1, end=1000)
    h = pn.widgets.FloatSlider(name="Source thickness H (m)", value=query_float("H", 5), start=0.1, end=50, step=0.1)
    c0 = pn.widgets.FloatSlider(name="Source concentration c0 (mg/L)", value=query_float("c0", 100), start=0.1, end=1000, step=1)
    w = pn.widgets.FloatSlider(name="Source width W (m)", value=query_float("W", 10), start=0.1, end=1000, step=0.1)
    v = pn.widgets.FloatInput(name="Avg. linear groundwater velocity v (m/yr)", value=query_float("v", 50), start=10, end=1000)
    ax = pn.widgets.FloatSlider(name="Longitudinal dispersivity ax (m)", value=query_float("ax", 10), start=1, end=100, step=0.5)
    ay = pn.widgets.FloatInput(name="Horizontal transverse dispersivity ay (m)", value=query_float("ay", 0.5), start=0.1, end=10)
    az = pn.widgets.FloatInput(name="Vertical transverse dispersivity az (m)", value=query_float("az", 0.05), start=0.01, end=1)
    df = pn.widgets.FloatInput(name="Effective diffusion coefficient Df (m2/yr)", value=query_float("Df", 0.0), start=0.0, end=0.1)
    r = pn.widgets.FloatInput(name="Retardation factor R (-)", value=query_float("R", 1.0), start=0.01)
    gamma = pn.widgets.FloatInput(name="Source decay gamma (1/yr)", value=query_float("gamma", 0.0), start=0.0, end=1.0)
    lam = pn.widgets.FloatSlider(name="Effective first-order decay lam (1/yr)", value=query_float("lam", 0.1), start=0.0, end=1.0, step=0.01)
    ng_default = query_int("ng", 60)
    if ng_default not in [4, 5, 6, 10, 15, 20, 60, 104, 256]:
        ng_default = 60
    ng = pn.widgets.Select(name="Number of Gauss points", value=ng_default, options=[4, 5, 6, 10, 15, 20, 60, 104, 256])
    return cthres, time, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng


def bioscreen_single_app():
    cthres, time, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng = _base_widgets()
    run_btn = pn.widgets.Button(name="Run BIOSCREEN simulation", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the BIOSCREEN model to compute plume length."), sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("BIOSCREEN-AT \u2014 Single Simulation", "BIOSCREEN Analytical")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="bioscreen_single_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            lmax = float(bio(cthres.value, time.value, h.value, c0.value, w.value, v.value, ax.value, ay.value, az.value, df.value, r.value, gamma.value, lam.value, int(ng.value)))
            result_pane.object = metric_card("Plume length", f"{lmax:.2f}")
            user_x = [selected_site_id if selected_site_id > 0 else 1]
            plot_pane.object = comparison_plot(
                "BioScreen",
                "BIOSCREEN plume length",
                user_x,
                [lmax],
                selected_site_id,
                email,
                "Run Number",
            )
            _state.update({
                "parameters": [
                    {"symbol": "Cthres", "name": "Threshold Concentration", "value": cthres.value, "unit": "mg/L"},
                    {"symbol": "t", "name": "Time", "value": time.value, "unit": "yr"},
                    {"symbol": "H", "name": "Source Thickness", "value": h.value, "unit": "m"},
                    {"symbol": "c0", "name": "Source Concentration", "value": c0.value, "unit": "mg/L"},
                    {"symbol": "W", "name": "Source Width", "value": w.value, "unit": "m"},
                    {"symbol": "v", "name": "Groundwater Velocity", "value": v.value, "unit": "m/yr"},
                    {"symbol": "ax", "name": "Long. Dispersivity", "value": ax.value, "unit": "m"},
                    {"symbol": "ay", "name": "Horiz. Trans. Dispersivity", "value": ay.value, "unit": "m"},
                    {"symbol": "az", "name": "Vert. Trans. Dispersivity", "value": az.value, "unit": "m"},
                    {"symbol": "\u03bb", "name": "First-order Decay", "value": lam.value, "unit": "1/yr"},
                ],
                "outputs": [{"label": "Maximum Plume Length L\u2098\u2090\u2093", "value": f"{lmax:.2f}", "unit": "m"}],
                "plot_data": {"labels": ["Lmax"], "values": [lmax], "ylabel": "Plume Length (m)", "title": "Maximum Plume Length — BIOSCREEN-AT"},
            })
            export_btn.visible = True
        except Exception as exc:
            result_pane.object = error_card(str(exc))
            plot_pane.object = None
            export_btn.visible = False

    run_btn.on_click(_run)

    controls = pn.Column(
        "## BIOSCREEN-AT (Single)",
        "### Manual inputs",
        cthres, time, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})


def bioscreen_multiple_app():
    cthres, time, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng = _base_widgets()
    w_times = pn.widgets.TextInput(name="Times for sweep (comma-separated years)", value=f"{max(1, time.value // 2)},{time.value},{time.value * 2}")
    run_btn = pn.widgets.Button(name="Run BIOSCREEN scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(info_card("Run the BIOSCREEN sweep to compare plume lengths over time."), sizing_mode="stretch_width")
    table = pn.widgets.Tabulator(pd.DataFrame(columns=["time_years", "lmax_m"]), height=240, sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    email = query_str("email", "demo@example.com")
    selected_site_id = query_int("site_id", 0)

    _state: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("BIOSCREEN-AT \u2014 Multiple Simulation", "BIOSCREEN Analytical")
        return io.BytesIO(report.generate(_state["parameters"], _state["outputs"], _state.get("plot_data")))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="bioscreen_multiple_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            times = sorted({float(part.strip()) for part in w_times.value.split(",") if part.strip()})
            if not times:
                raise ValueError("Provide at least one time value.")

            rows = []
            for t in times:
                lmax = float(bio(cthres.value, t, h.value, c0.value, w.value, v.value, ax.value, ay.value, az.value, df.value, r.value, gamma.value, lam.value, int(ng.value)))
                rows.append({"time_years": t, "lmax_m": lmax})

            df_out = pd.DataFrame(rows).sort_values("time_years")
            table.value = df_out
            l_vals = df_out["lmax_m"].tolist()
            result_pane.object = summary_card([
                ("Successful runs", str(len(l_vals))),
                ("Max plume length", f"{max(l_vals):.2f} m"),
            ])
            plot_pane.object = comparison_plot(
                "BioScreen",
                "BIOSCREEN plume length",
                list(range(1, len(l_vals) + 1)),
                l_vals,
                selected_site_id,
                email,
                "Scenario Number",
            )
            _state.update({
                "parameters": [{"symbol": f"t={r['time_years']:.0f}yr", "name": f"Time {r['time_years']:.0f} yr", "value": f"L={r['lmax_m']:.2f}", "unit": "m"} for r in rows],
                "outputs": [
                    {"label": "Scenarios run", "value": str(len(l_vals)), "unit": ""},
                    {"label": "Max plume length", "value": f"{max(l_vals):.2f}", "unit": "m"},
                    {"label": "Min plume length", "value": f"{min(l_vals):.2f}", "unit": "m"},
                ],
                "plot_data": {"labels": [f"t={r['time_years']:.0f}yr" for r in rows], "values": [r["lmax_m"] for r in rows], "ylabel": "Plume Length (m)", "title": "Plume Length Over Time — BIOSCREEN-AT"},
            })
            export_btn.visible = True
        except Exception as exc:
            table.value = pd.DataFrame([{"error": str(exc)}])
            result_pane.object = error_card(str(exc))
            plot_pane.object = None
            export_btn.visible = False

    run_btn.on_click(_run)

    controls = pn.Column(
        "## BIOSCREEN-AT (Multiple)",
        "### Manual scenario inputs",
        w_times, cthres, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng, table,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 380px", "min-width": "300px"},
    )
    outputs = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 540px", "min-width": "340px"})
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, export_btn, sizing_mode="stretch_both", styles={"gap": "14px"})
