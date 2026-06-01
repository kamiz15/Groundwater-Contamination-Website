"""
panel_source_inversion.py — Panel app for single-source iterative inverse modelling.

The user enters ~4 observed (M, L_max) signal pairs plus chemistry parameters,
configures solver bounds / tolerance / max-iterations, and clicks Run.  The app
calls source_inversion.invert_alpha_tv — which iterates the Liedl forward model
in its inner loop — and reports alpha_Tv, convergence status, per-signal
residuals, and a fit-quality plot.

A non-converged result is shown as an error card; the fitted value is NEVER
presented as a usable result unless convergence is confirmed.
"""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import panel as pn
from bokeh.plotting import figure

from analytical_models import liedl_lmax
from panel_analytical_common import (
    error_card,
    info_card,
    query_float,
    query_int,
    query_str,
    summary_card,
)
from pdf_report import CASTReport
from source_inversion import Signal, invert_alpha_tv

pn.extension("tabulator", sizing_mode="stretch_width")

# ── Default signal table (consistent with alpha_Tv = 0.001 m) ─────────────────
_DEFAULT_SIGNALS = pd.DataFrame(
    {
        "M [m]":         [2.0,    4.0,    6.0,    8.0],
        "L_max_obs [m]": [2270.9, 9083.6, 20438.0, 36334.3],
        "gamma [-]":     [3.5,    3.5,    3.5,    3.5],
        "Ca [mg/L]":     [8.0,    8.0,    8.0,    8.0],
        "Cd [mg/L]":     [5.0,    5.0,    5.0,    5.0],
    }
)

_TABULATOR_EDITORS = {
    "M [m]":         {"type": "number", "step": 0.1},
    "L_max_obs [m]": {"type": "number", "step": 1.0},
    "gamma [-]":     {"type": "number", "step": 0.1},
    "Ca [mg/L]":     {"type": "number", "step": 0.1},
    "Cd [mg/L]":     {"type": "number", "step": 0.1},
}


def source_inversion_app():
    # ── Signal table ──────────────────────────────────────────────────────────
    signal_table = pn.widgets.Tabulator(
        _DEFAULT_SIGNALS.copy(),
        editors=_TABULATOR_EDITORS,
        height=200,
        sizing_mode="stretch_width",
        name="Observed signals",
    )

    # ── Solver settings ───────────────────────────────────────────────────────
    alpha_lo_w = pn.widgets.FloatInput(
        name="αTv lower bound [m]",
        value=query_float("alpha_lo", 1e-7),
        step=1e-7,
        start=1e-12,
        format="0.0000000",
    )
    alpha_hi_w = pn.widgets.FloatInput(
        name="αTv upper bound [m]",
        value=query_float("alpha_hi", 1.0),
        step=0.1,
        start=1e-7,
    )
    tol_w = pn.widgets.FloatInput(
        name="Convergence tolerance [m]",
        value=query_float("tol", 1e-9),
        step=1e-10,
        start=1e-15,
        format="0.0000000000",
    )
    maxiter_w = pn.widgets.IntInput(
        name="Max iterations",
        value=query_int("maxiter", 500),
        step=50,
        start=1,
    )

    run_btn = pn.widgets.Button(
        name="Run Inversion",
        button_type="primary",
        sizing_mode="stretch_width",
    )

    result_pane = pn.pane.HTML(
        info_card(
            "Enter observed (M, L_max) signal pairs in the table above, "
            "configure solver settings, then click Run."
        ),
        sizing_mode="stretch_width",
    )
    residual_pane = pn.pane.HTML("", sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)

    _state: dict = {}

    # ── Bokeh fit-quality plot ─────────────────────────────────────────────────
    def _make_fit_plot(signals: list[Signal], alpha_tv_fit: float) -> object:
        M_vals = [s.M for s in signals]
        L_obs_vals = [s.L_max_obs for s in signals]

        # Modelled curve over the M range
        M_min = max(min(M_vals) * 0.5, 0.1)
        M_max = max(M_vals) * 1.5
        M_curve = list(np.linspace(M_min, M_max, 200))
        L_curve = []
        for M in M_curve:
            # Use the median chemistry for the smooth curve
            gammas = [s.gamma for s in signals]
            Cas = [s.Ca for s in signals]
            Cds = [s.Cd for s in signals]
            g_med = float(np.median(gammas))
            Ca_med = float(np.median(Cas))
            Cd_med = float(np.median(Cds))
            try:
                L_curve.append(liedl_lmax(M, alpha_tv_fit, g_med, Ca_med, Cd_med))
            except Exception:
                L_curve.append(float("nan"))

        p = figure(
            title=f"Inversion Fit — αTv = {alpha_tv_fit:.6g} m",
            x_axis_label="Source thickness M [m]",
            y_axis_label="Plume length Lmax [m]",
            height=420,
            sizing_mode="stretch_width",
            toolbar_location="above",
        )
        p.line(M_curve, L_curve,
               line_color="#163c66", line_width=2,
               legend_label=f"Model (αTv = {alpha_tv_fit:.4g} m)")
        p.scatter(M_vals, L_obs_vals,
                  size=12, color="#e05c00", marker="circle",
                  legend_label="Observed L_max")
        p.legend.location = "top_left"
        p.legend.click_policy = "hide"
        return p

    # ── Residuals HTML table ──────────────────────────────────────────────────
    def _residuals_html(per_signal: list[dict]) -> str:
        rows = ""
        for i, d in enumerate(per_signal, 1):
            colour = "#1a7a3a" if abs(d["residual_pct"]) < 5 else "#9f2d2d"
            rows += (
                f"<tr>"
                f"<td>{i}</td>"
                f"<td>{d['M']:.2f}</td>"
                f"<td>{d['L_obs']:.1f}</td>"
                f"<td>{d['L_mod']:.1f}</td>"
                f"<td>{d['residual_m']:+.1f}</td>"
                f"<td style='color:{colour};font-weight:700;'>{d['residual_pct']:+.2f}%</td>"
                f"</tr>"
            )
        return (
            "<table style='width:100%;border-collapse:collapse;font-size:0.88rem;'>"
            "<thead><tr style='background:#dce9f9;'>"
            "<th>#</th><th>M [m]</th><th>L_obs [m]</th>"
            "<th>L_mod [m]</th><th>Residual [m]</th><th>Residual [%]</th>"
            "</tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )

    # ── PDF callback ──────────────────────────────────────────────────────────
    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Source Inversion — αTv Recovery", "Iterative Liedl Inversion")
        return io.BytesIO(report.generate(
            _state["parameters"], _state["outputs"], _state.get("plot_data")
        ))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback,
        filename="source_inversion_report.pdf",
        label="↓ Download PDF Report",
        button_type="primary",
        sizing_mode="stretch_width",
        visible=False,
    )

    # ── Run callback ──────────────────────────────────────────────────────────
    def _run(_=None):
        run_btn.disabled = True
        try:
            df = signal_table.value
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)
            if df.empty:
                raise ValueError("Signal table is empty — add at least one observed signal.")

            # Parse signals from table
            signals: list[Signal] = []
            for i, row in df.iterrows():
                try:
                    signals.append(Signal(
                        M=float(row["M [m]"]),
                        L_max_obs=float(row["L_max_obs [m]"]),
                        gamma=float(row["gamma [-]"]),
                        Ca=float(row["Ca [mg/L]"]),
                        Cd=float(row["Cd [mg/L]"]),
                    ))
                except (KeyError, TypeError, ValueError) as e:
                    raise ValueError(f"Row {int(i)+1}: {e}") from e

            lo = alpha_lo_w.value
            hi = alpha_hi_w.value
            tol = tol_w.value
            maxiter = maxiter_w.value

            run_btn.name = f"Running… (max {maxiter} iterations)"
            inv = invert_alpha_tv(
                signals,
                bounds=(lo, hi),
                tol=tol,
                maxiter=maxiter,
            )

            # ── Non-convergence: show error, do NOT present result ────────────
            if not inv.converged:
                result_pane.object = (
                    '<div style="background:#fff4f4;border:2px solid #c0392b;'
                    'border-radius:14px;padding:20px 22px;">'
                    '<div style="font-size:1rem;font-weight:800;color:#9f2d2d;'
                    'letter-spacing:0.06em;text-transform:uppercase;margin-bottom:10px;">'
                    "⚠ Inversion Did Not Converge</div>"
                    f'<p style="font-size:0.95rem;color:#5f1d1d;margin:0 0 8px;">'
                    f"Solver stopped after {inv.n_iterations} iterations without "
                    "reaching the requested tolerance.</p>"
                    '<p style="font-size:0.92rem;color:#5f1d1d;margin:0;">'
                    "<strong>The fitted value is unreliable and must not be used.</strong> "
                    "Try: increasing Max iterations, widening the bounds, or loosening "
                    "the tolerance.</p></div>"
                )
                residual_pane.object = ""
                plot_pane.object = None
                export_btn.visible = False
                return

            # ── Converged: display results ─────────────────────────────────────
            rms = (inv.residual_sum_sq / len(signals)) ** 0.5
            result_pane.object = summary_card(
                [
                    ("Fitted αTv", f"{inv.alpha_tv_fit:.6g} m"),
                    ("RMS residual", f"{rms:.2f} m"),
                    ("Iterations", str(inv.n_iterations)),
                    ("Signals used", str(len(signals))),
                ],
                title="Inversion Converged ✓",
            )

            residual_pane.object = (
                '<div style="background:#f4f9ff;border:1px solid #c4ddf5;'
                'border-radius:12px;padding:14px 16px;margin-top:4px;">'
                '<div style="font-size:0.85rem;font-weight:800;letter-spacing:0.06em;'
                'text-transform:uppercase;color:#2f5f8f;margin-bottom:8px;">'
                "Per-Signal Residuals</div>"
                + _residuals_html(inv.per_signal)
                + "</div>"
            )

            plot_pane.object = _make_fit_plot(signals, inv.alpha_tv_fit)

            _state.update({
                "parameters": [
                    {"symbol": "N", "name": "Signals used", "value": len(signals), "unit": "-"},
                    {"symbol": "αTv_lo", "name": "Lower bound", "value": lo, "unit": "m"},
                    {"symbol": "αTv_hi", "name": "Upper bound", "value": hi, "unit": "m"},
                    {"symbol": "tol", "name": "Tolerance", "value": tol, "unit": "m"},
                    {"symbol": "max_it", "name": "Max iterations", "value": maxiter, "unit": "-"},
                ],
                "outputs": [
                    {"label": "Fitted αTv", "value": f"{inv.alpha_tv_fit:.6g}", "unit": "m"},
                    {"label": "Iterations", "value": str(inv.n_iterations), "unit": "-"},
                    {"label": "RMS residual", "value": f"{rms:.2f}", "unit": "m"},
                    {"label": "Converged", "value": "Yes", "unit": "-"},
                ],
                "plot_data": {
                    "labels": ["αTv fitted"],
                    "values": [inv.alpha_tv_fit],
                    "ylabel": "Dispersivity αTv [m]",
                    "title": "Inversion Result",
                },
            })
            export_btn.visible = True

        except Exception as exc:
            result_pane.object = error_card(exc)
            residual_pane.object = ""
            plot_pane.object = None
            export_btn.visible = False
        finally:
            run_btn.disabled = False
            run_btn.name = "Run Inversion"

    run_btn.on_click(_run)

    # ── Output-only mode ──────────────────────────────────────────────────────
    if query_int("output_only", 0):
        if query_int("run", 0):
            _run()
        return pn.Column(
            result_pane, residual_pane, plot_pane,
            sizing_mode="stretch_width",
            styles={"gap": "14px"},
        )

    # ── Full layout ───────────────────────────────────────────────────────────
    settings_col = pn.Column(
        pn.pane.HTML(
            '<div style="font-weight:700;margin:10px 0 4px;color:#163c66;">'
            "Solver Settings</div>"
        ),
        alpha_lo_w,
        alpha_hi_w,
        tol_w,
        maxiter_w,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 280px", "min-width": "240px"},
    )

    signals_col = pn.Column(
        pn.pane.HTML(
            '<div style="font-weight:700;margin:10px 0 4px;color:#163c66;">'
            "Observed Signals — edit in table</div>"
        ),
        pn.pane.HTML(
            '<p style="font-size:0.83rem;color:#5b7a9a;margin:0 0 6px;">'
            "Each row is one field observation: source thickness M (measured from borehole "
            "or geometry), observed plume length L_max, and chemistry. "
            "Add or remove rows as needed (≥ 1 required, ≥ 4 recommended).</p>"
        ),
        signal_table,
        sizing_mode="stretch_width",
        styles={"flex": "2 1 480px", "min-width": "320px"},
    )

    body = pn.FlexBox(
        signals_col,
        settings_col,
        sizing_mode="stretch_width",
        flex_wrap="wrap",
        styles={
            "align-items": "flex-start",
            "gap": "16px",
            "min-height": "280px",
        },
    )

    outputs_col = pn.Column(
        result_pane,
        residual_pane,
        plot_pane,
        sizing_mode="stretch_width",
        styles={"gap": "12px"},
    )

    return pn.Column(
        run_btn,
        body,
        outputs_col,
        export_btn,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
