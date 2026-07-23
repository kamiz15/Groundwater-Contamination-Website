import base64
import io
import logging

import panel as pn

from numerical_jobs import cancel_job, fetch_result, job_status, submit_job
from panel_analytical_common import error_card, info_card, query_float, query_int, summary_card
from panel_theme import report_bridge_html
from panel_numerical_animation import play_growth_once, stop_growth

pn.extension(sizing_mode="stretch_width", raw_css=["""
@keyframes numericalStatusPulse {
  0%, 100% { opacity: 1; transform: translateY(0); }
  50% { opacity: 0.72; transform: translateY(-1px); }
}
.numerical-loading-card {
  animation: numericalStatusPulse 1.6s ease-in-out infinite;
}
"""])

logger = logging.getLogger(__name__)


def _input_row(*widgets):
    """A wrapping input row: keeps each widget at a usable minimum width on
    narrow screens instead of squeezing them until labels overlap (pn.Row
    does not wrap). The stylesheet lets long labels wrap inside the widget's
    shadow DOM instead of bleeding into the neighbouring column."""
    for widget in widgets:
        widget.styles = {"flex": "1 1 160px", "min-width": "150px"}
        widget.stylesheets = ["label { white-space: normal; overflow-wrap: anywhere; }"]
    return pn.FlexBox(*widgets, flex_wrap="wrap", sizing_mode="stretch_width", styles={"gap": "10px"})


def _loading_status_card(items, title):
    return f'<div class="numerical-loading-card">{summary_card(items, title=title)}</div>'


def numerical_horizontal_single_app():
    # Input (user / database)
    source = pn.widgets.FloatInput(name="Source Thickness Sw [m]", value=query_float("source_thickness", query_float("source", query_float("Sw", 5.0))), step=0.1)
    grid_size = pn.widgets.FloatInput(name="Grid Size dx=dy [m]", value=query_float("grid_size", 1.0), step=0.1)
    alpha_l = pn.widgets.FloatInput(name="Longitudinal Dispersivity aL [m]", value=query_float("al", 1.0), step=0.1)
    at = pn.widgets.FloatInput(name="Transverse Dispersivity aT [m]", value=query_float("at", query_float("alpha_Th", 0.2)), step=0.01)
    gamma = pn.widgets.FloatInput(name="Stoichiometric Ratio gamma [-]", value=query_float("gamma", 3.5), step=0.1)
    cd = pn.widgets.FloatInput(name="Electron Donor Cd [mg/L]", value=query_float("Cd", query_float("C_D", 5.0)), step=0.1)
    ca = pn.widgets.FloatInput(name="Electron Acceptor Ca [mg/L]", value=query_float("Ca", query_float("C_A", 8.0)), step=0.1)
    # Standard (modifiable defaults; analytical L_D / width are derived in the model)
    prsity = pn.widgets.FloatInput(name="Porosity n [-]", value=query_float("prsity", 0.3), step=0.01)
    hk = pn.widgets.FloatInput(name="Hydraulic Conductivity K [m/d]", value=query_float("hk", 8.64), step=0.1)
    gradient = pn.widgets.FloatInput(name="Hydraulic Gradient i [-]", value=query_float("gradient", 0.0125), step=0.001)
    # Analytical column (computed, read-only; filled after a run)
    ld_out = pn.widgets.StaticText(name="Domain Length L_D [m]", value="\u2014")
    dw_out = pn.widgets.StaticText(name="Domain Width [m]", value="\u2014")
    for _w in (source, grid_size, alpha_l, at, gamma, cd, ca, prsity, hk, gradient, ld_out, dw_out):
        _w.stylesheets = ["label { white-space: normal; overflow-wrap: anywhere; }"]

    run_btn = pn.widgets.Button(name="Run Horizontal Simulation", button_type="primary", sizing_mode="stretch_width")
    cancel_btn = pn.widgets.Button(name="Cancel Job", button_type="danger", sizing_mode="stretch_width", visible=False)
    result_pane = pn.pane.HTML(info_card("Enter horizontal model parameters and run the simulation."), sizing_mode="stretch_width")
    graph_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
    comparison_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=340)
    state = {}
    anim = {"holder": None}
    poller = {"callback": None}
    report_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")

    head_dl_btn = pn.widgets.FileDownload(
        callback=lambda: io.BytesIO(state.get("head_file") or b""),
        filename="head.hds", label="Download head (.hds)",
        button_type="default", sizing_mode="stretch_width", visible=False,
    )
    conc_dl_btn = pn.widgets.FileDownload(
        callback=lambda: io.BytesIO(state.get("concentration_file") or b""),
        filename="concentration.ucn", label="Download concentration (.ucn)",
        button_type="default", sizing_mode="stretch_width", visible=False,
    )

    def _stop_polling():
        cancel_btn.visible = False
        run_btn.disabled = False
        if poller["callback"] is not None:
            poller["callback"].stop()
            poller["callback"] = None

    def _render_completed_result(result):
        stop_growth(anim.get("holder"))
        footer_meta = (
            f"L_D = {result.domain_length:.2f} m  |  Δx=Δy = {grid_size.value:.2f} m  |  "
            f"porosity = {prsity.value:.2f}  |  K = {hk.value:.2f} m/d  |  "
            f"gradient = {gradient.value:.4f}  |  Péclet = {getattr(result, 'peclet', 0.0):.2f}  |  "
            "Courant target = 5"
        )
        plot_kwargs = dict(
            concentration=result.concentration,
            x_grid=result.x_grid,
            cross_grid=result.y_grid,
            ca=ca.value,
            cd=cd.value,
            gamma=gamma.value,
            plume_length=result.plume_length,
            domain_length=result.domain_length,
            cross_extent=result.domain_width,
            orientation="horizontal",
            source_extent=source.value,
            footer_meta=footer_meta,
        )
        # One-shot growth sweep for visual effect, then the full static plume.
        anim["holder"] = play_growth_once(graph_pane, plot_kwargs)
        logger.info("Horizontal single graph_pane.object assigned")
        comparison_pane.object = None
        _rows = [
            ("Numerical Lmax", f"{result.plume_length:.2f} m"),
            ("Domain Length LD", f"{result.domain_length:.2f} m"),
            ("Domain Width", f"{result.domain_width:.2f} m"),
            ("Peclet", f"{result.peclet:.2f}"),
        ]
        if getattr(result, "k_warning", ""):
            _rows.append(("\u26a0 K warning", result.k_warning))
        result_pane.object = summary_card(_rows, title="Horizontal Simulation Results")
        state.update({
            "parameters": [
                {"symbol": "Sw", "name": "Source Thickness", "value": source.value, "unit": "m"},
                {"symbol": "dx", "name": "Grid Size", "value": grid_size.value, "unit": "m"},
                {"symbol": "aL", "name": "Longitudinal Dispersivity", "value": alpha_l.value, "unit": "m"},
                {"symbol": "aT", "name": "Transverse Dispersivity", "value": at.value, "unit": "m"},
                {"symbol": "gamma", "name": "Stoichiometric Ratio", "value": gamma.value, "unit": "-"},
                {"symbol": "Cd", "name": "Electron Donor", "value": cd.value, "unit": "mg/L"},
                {"symbol": "Ca", "name": "Electron Acceptor", "value": ca.value, "unit": "mg/L"},
                {"symbol": "n", "name": "Porosity", "value": prsity.value, "unit": "-"},
                {"symbol": "K", "name": "Hydraulic Conductivity", "value": hk.value, "unit": "m/d"},
                {"symbol": "i", "name": "Hydraulic Gradient", "value": gradient.value, "unit": "-"},
                {"symbol": "LD", "name": "Domain Length (analytical)", "value": result.domain_length, "unit": "m"},
                {"symbol": "DW", "name": "Domain Width", "value": result.domain_width, "unit": "m"},
                {"symbol": "Pe", "name": "Peclet Number", "value": result.peclet, "unit": "-"},
            ],
            "outputs": [
                {"label": "Horizontal Numerical Lmax", "value": f"{result.plume_length:.2f}", "unit": "m"},
                {"label": "Domain Length LD", "value": f"{result.domain_length:.2f}", "unit": "m"},
                {"label": "Domain Width", "value": f"{result.domain_width:.2f}", "unit": "m"},
                {"label": "Peclet", "value": f"{result.peclet:.2f}", "unit": "-"},
                {"label": "Courant Target", "value": f"{result.courant:.2f}", "unit": "-"},
            ],
            "plot_data": {
                "labels": ["Horizontal numerical"],
                "values": [result.plume_length],
                "ylabel": "Plume Length (m)",
                "title": "Horizontal Numerical",
            },
            "plot_images": [
                {
                    "title": "Horizontal Plume Concentration",
                    "bytes": result.plot_png,
                    "caption": "Simulated contaminant plume - plan view (horizontal model).",
                    "max_height_mm": 82,
                }
            ] if result.plot_png else [],
        })
        state["head_file"] = getattr(result, "head_file", b"")
        state["concentration_file"] = getattr(result, "concentration_file", b"")
        head_dl_btn.visible = bool(state["head_file"])
        conc_dl_btn.visible = bool(state["concentration_file"])
        ld_out.value = f"{result.domain_length:.2f}"
        dw_out.value = f"{result.domain_width:.2f}"
        report_bridge.object = report_bridge_html(
            "Numerical Horizontal Model - Single Simulation", "Numerical Horizontal",
            "numerical_horizontal_single_report.pdf",
            parameters=state["parameters"], outputs=state["outputs"],
            plot_data=state.get("plot_data"),
            plot_images_b64=[
                {
                    "title": img["title"],
                    "caption": img.get("caption", ""),
                    "b64": base64.b64encode(img["bytes"]).decode(),
                    "max_height_mm": img.get("max_height_mm", 82),
                }
                for img in (state.get("plot_images") or [])
            ],
        )

    def _poll(job_id):
        status = job_status(job_id)
        if not status:
            result_pane.object = error_card(f"Unknown numerical job {job_id}")
            _stop_polling()
            return
        fields = [("Job", job_id[:8]), ("Status", status["status"])]
        if status["status"] == "queued":
            fields.append(("Queue position", status.get("queue_position", "?")))
        if status["status"] in {"queued", "running"}:
            result_pane.object = _loading_status_card(fields, title="Horizontal Simulation Status")
        else:
            result_pane.object = summary_card(fields, title="Horizontal Simulation Status")
        if status["status"] == "done":
            _render_completed_result(fetch_result(job_id))
            _stop_polling()
        elif status["status"] == "failed":
            result_pane.object = error_card(status.get("error") or "Numerical job failed.")
            _stop_polling()
        elif status["status"] == "cancelled":
            result_pane.object = summary_card([("Job", job_id[:8]), ("Status", "cancelled")], title="Horizontal Simulation Cancelled")
            _stop_polling()

    def _run(_=None):
        stop_growth(anim.get("holder"))
        report_bridge.object = report_bridge_html(clear=True)
        run_btn.disabled = True
        ld_out.value = "\u2014"
        dw_out.value = "\u2014"
        try:
            if min(source.value, grid_size.value, alpha_l.value, at.value, gamma.value,
                   cd.value, ca.value, prsity.value, hk.value) <= 0:
                raise ValueError("All horizontal inputs must be positive.")
            params = {
                "source_thickness": source.value,
                "grid_size": grid_size.value,
                "al": alpha_l.value,
                "at": at.value,
                "gamma": gamma.value,
                "cd": cd.value,
                "ca": ca.value,
                "prsity": prsity.value,
                "hk": hk.value,
                "gradient": gradient.value,
            }
            job_id = submit_job("horizontal_single", params)
            state["job_id"] = job_id
            cancel_btn.visible = True
            graph_pane.object = None
            comparison_pane.object = None
            result_pane.object = _loading_status_card([("Job", job_id[:8]), ("Status", "queued")], title="Horizontal Simulation Submitted")
            poller["callback"] = pn.state.add_periodic_callback(lambda: _poll(job_id), 2000, start=True)
            _poll(job_id)
        except Exception as exc:
            logger.exception("Horizontal numerical single simulation failed")
            result_pane.object = error_card(exc)
            graph_pane.object = None
            comparison_pane.object = None
            report_bridge.object = report_bridge_html(clear=True)
            cancel_btn.visible = False
            run_btn.disabled = False

    def _cancel(_=None):
        job_id = state.get("job_id")
        if job_id and cancel_job(job_id):
            result_pane.object = summary_card([("Job", job_id[:8]), ("Status", "cancelled")], title="Horizontal Simulation Cancelled")
            _stop_polling()

    run_btn.on_click(_run)
    cancel_btn.on_click(_cancel)

    if query_int("output_only", 0):
        should_run = query_int("run", 0)
        if should_run:
            _run()
        output_objects = [result_pane]
        if should_run:
            output_objects.extend([graph_pane, comparison_pane, cancel_btn])
        output_objects.append(report_bridge)
        return pn.Column(*output_objects, sizing_mode="stretch_width", styles={"gap": "14px"})

    return pn.Column(
        "## Horizontal Numerical Model",
        pn.FlexBox(
            pn.Column("#### Input", source, grid_size, alpha_l, at, gamma, cd, ca, styles={"flex": "1 1 240px", "min-width": "210px", "gap": "8px"}),
            pn.Column("#### Analytical", ld_out, dw_out, "#### Standard (editable)", prsity, hk, gradient, styles={"flex": "1 1 240px", "min-width": "210px", "gap": "8px"}),
            flex_wrap="wrap", sizing_mode="stretch_width", styles={"gap": "18px"}),
        run_btn,
        cancel_btn,
        result_pane,
        graph_pane,
        comparison_pane,
        head_dl_btn,
        conc_dl_btn,
        report_bridge,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
