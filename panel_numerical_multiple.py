import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import panel as pn

from analytical_models import cirpka_lmax as _cirpka_lmax, cirpka_domain_length, liedl_lmax
from data_queries import get_user_sites
from numerical_models import run_numerical_model, run_numerical_model_horizontal
from pdf_report import CASTReport
from plot_functions import (
    plot_horizontal_plume_interactive,
    plot_lmax_scatter,
    plot_vertical_plume_interactive,
)

pn.extension("tabulator", sizing_mode="stretch_width")


def _query_float(name, default):
    try:
        req = pn.state.curdoc.session_context.request
        raw = req.arguments.get(name, [str(default).encode()])[0].decode()
        return float(raw)
    except Exception:
        return default


def _query_int(name, default=0):
    try:
        req = pn.state.curdoc.session_context.request
        return int(float(req.arguments.get(name, [str(default).encode()])[0].decode()))
    except Exception:
        return default


def _query_str(name, default=""):
    try:
        req = pn.state.curdoc.session_context.request
        return req.arguments.get(name, [default.encode()])[0].decode()
    except Exception:
        return default


def _safe_float(value):
    try:
        if value is None:
            return None
        value = float(value)
        if not np.isfinite(value):
            return None
        return value
    except Exception:
        return None


def _database_lmax_points(email, alpha_tv, gamma, selected_site_id=0):
    try:
        rows = get_user_sites(email)
    except Exception:
        return [], [], None

    analytical, observed, selected = [], [], None
    for row in rows:
        site_id = int(row[0])
        M = _safe_float(row[3])
        plume_length = _safe_float(row[4])
        C_ED0 = _safe_float(row[7])
        C_EA0 = _safe_float(row[8])
        if None in {M, plume_length, C_ED0, C_EA0}:
            continue
        try:
            model_lmax = liedl_lmax(M, alpha_tv, gamma, C_EA0, C_ED0)
        except Exception:
            continue
        analytical.append(model_lmax)
        observed.append(plume_length)
        if selected_site_id and site_id == selected_site_id:
            selected = {"analytical_lmax": model_lmax, "plume_length": plume_length}
    return analytical, observed, selected


def _result_card(title, body_html, tone="info"):
    if tone == "error":
        border, bg, label = "#f1b7b7", "#fff4f4", "#9f2d2d"
    else:
        border, bg, label = "#c4ddf5", "linear-gradient(135deg,#ffffff 0%,#f4f9ff 100%)", "#2f5f8f"
    return f"""
    <div style="background:{bg};border:1px solid {border};border-radius:16px;padding:18px 20px;box-shadow:0 12px 28px rgba(17,24,39,0.08);">
      <div style="font-size:0.85rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:{label};margin-bottom:8px;">{title}</div>
      {body_html}
    </div>
    """


def _clean_numeric(values):
    out = []
    for value in values or []:
        try:
            value = float(value)
            if np.isfinite(value):
                out.append(value)
        except Exception:
            continue
    return out


def _figure_bytes(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _contour_image_bytes(C, x_grid, y_grid, title, xlabel, ylabel, plume_length, domain_length):
    C = np.asarray(C, dtype=float)
    x_grid = np.asarray(x_grid, dtype=float)
    y_grid = np.asarray(y_grid, dtype=float)
    fig, ax = plt.subplots(figsize=(9.5, 4.8), dpi=180)
    im = ax.imshow(
        np.flipud(C),
        extent=[float(x_grid.min()), float(x_grid.max()), float(y_grid.min()), float(y_grid.max())],
        aspect="auto",
        cmap="RdYlGn_r",
    )
    finite = C[np.isfinite(C)]
    if finite.size and float(np.nanmin(finite)) < float(np.nanmax(finite)):
        levels = np.linspace(float(np.nanmin(finite)), float(np.nanmax(finite)), 12)
        ax.contour(x_grid, y_grid, C, levels=levels, colors="black", linewidths=0.45, alpha=0.45)
    ax.axvline(plume_length, color="#1B3A6B", linestyle="--", linewidth=1.5, label=f"Lmax = {plume_length:.1f} m")
    ax.axvline(domain_length, color="#6B7280", linestyle=":", linewidth=1.5, label=f"LD = {domain_length:.1f} m")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend(loc="upper right", fontsize=8)
    fig.colorbar(im, ax=ax, label="Concentration [mg/L]")
    fig.tight_layout()
    return _figure_bytes(fig)


def _scatter_image_bytes(db_analytical, db_plumes, numerical_runs, selected_site=None):
    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=180)
    clean_x = _clean_numeric(db_analytical)
    clean_y = _clean_numeric(db_plumes)
    if clean_x and clean_y:
        n = min(len(clean_x), len(clean_y))
        ax.scatter(clean_x[:n], clean_y[:n], s=28, alpha=0.5, color="#AED6F1", label="Database plume length")
    vals = clean_x + clean_y
    for x_val, y_val, label in numerical_runs:
        ax.scatter([x_val], [y_val], s=60, marker="^", label=label)
        vals.extend(_clean_numeric([x_val, y_val]))
    if selected_site:
        ax.scatter([selected_site["analytical_lmax"]], [selected_site["plume_length"]], s=90, marker="x", color="#DB2777", label="Selected site")
        vals.extend(_clean_numeric([selected_site["analytical_lmax"], selected_site["plume_length"]]))
    ref_max = max(vals) * 1.1 if vals else 1.0
    ax.plot([0, ref_max], [0, ref_max], linestyle="--", color="#D1D5DB", label="1:1 reference")
    ax.set_xlim(0, ref_max)
    ax.set_ylim(0, ref_max)
    ax.set_title("Numerical Model Plume Length Comparison")
    ax.set_xlabel("Analytical Lmax [m]")
    ax.set_ylabel("Numerical / Observed Plume Length [m]")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    return _figure_bytes(fig)


def _run_row(row):
    S_T      = float(row.get("S_T",      1.0))
    R_Ta     = float(row.get("R_Ta",     2.0))
    R_Tb     = float(row.get("R_Tb",     2.0))
    delta_x  = float(row.get("delta_x",  1.0))
    delta_z  = float(row.get("delta_z",  0.25))
    prsity   = float(row.get("prsity",   0.3))
    al       = float(row.get("al",       5.0))
    av       = float(row.get("av",       0.5))
    gamma    = float(row.get("gamma",    3.5))
    Cd       = float(row.get("Cd",       5.0))
    Ca       = float(row.get("Ca",       8.0))
    h1       = float(row.get("h1",       10.0))
    h2       = float(row.get("h2",       9.0))
    hk       = float(row.get("hk",       1.0))
    Sw       = float(row.get("Sw",       5.0))
    R_Wu     = float(row.get("R_Wu",     7.5))
    R_Wb     = float(row.get("R_Wb",     7.5))
    alpha_th = float(row.get("alpha_th", 0.1))

    if S_T <= 0:
        raise ValueError("Source thickness ST must be > 0.")
    if R_Ta < 0 or R_Tb < 0:
        raise ValueError("Source buffers R_Ta and R_Tb cannot be negative.")
    if delta_x <= 0 or delta_z <= 0:
        raise ValueError("Grid spacing must be > 0.")
    if h1 <= h2:
        raise ValueError("Head h1 must be greater than head h2.")
    if Sw <= 0:
        raise ValueError("Source width Sw must be > 0.")
    if R_Wu < 0 or R_Wb < 0:
        raise ValueError("Horizontal reactant buffers R_Wu and R_Wb cannot be negative.")
    if alpha_th <= 0:
        raise ValueError("Horizontal dispersivity alpha_th must be > 0.")

    # Vertical model
    A_T = R_Tb + R_Ta + S_T
    analytical_lmax = liedl_lmax(A_T, av, gamma, Ca, Cd)
    if analytical_lmax <= 0:
        raise ValueError("Liedl analytical Lmax must be positive.")
    L_D_v = 1.5 * analytical_lmax
    n_cols_v = int(np.ceil(L_D_v / delta_x))
    n_rows_v = int(np.ceil(A_T / delta_z))
    if n_cols_v < 2 or n_rows_v < 2:
        raise ValueError("Vertical grid too coarse — reduce delta_x or delta_z.")

    v_result = run_numerical_model(L_D_v, A_T, n_cols_v, n_rows_v, prsity, al, av, gamma, Cd, Ca, h1, h2, hk)

    # Horizontal model
    cirpka_lmax_val = _cirpka_lmax(Sw, alpha_th, gamma, Ca, Cd)
    L_D_h = cirpka_domain_length(cirpka_lmax_val)
    A_W = R_Wb + Sw + R_Wu
    n_cols_h = int(np.ceil(L_D_h / delta_x))
    n_rows_h = int(np.ceil(A_W / delta_z))
    if n_cols_h < 2 or n_rows_h < 2:
        raise ValueError("Horizontal grid too coarse — reduce delta_x or delta_z.")

    h_result = run_numerical_model_horizontal(
        L_D_h, A_W, Sw, n_cols_h, n_rows_h,
        prsity, al, alpha_th, gamma, Cd, Ca, h1, h2, hk,
    )

    return {
        "v_result":        v_result,
        "h_result":        h_result,
        "analytical_lmax": analytical_lmax,
        "cirpka_lmax":     cirpka_lmax_val,
        "L_D_v":           L_D_v,
        "L_D_h":           L_D_h,
        "A_T":             A_T,
        "A_W":             A_W,
        "S_T":             S_T,
        "Sw":              Sw,
        "R_Wu":            R_Wu,
        "R_Wb":            R_Wb,
        "R_Ta":            R_Ta,
        "R_Tb":            R_Tb,
        "av":              av,
        "gamma":           gamma,
    }


def numerical_multiple_app():
    default_df = pd.DataFrame([
        {
            "S_T":      _query_float("S_T",      1.0),
            "R_Ta":     _query_float("R_Ta",      2.0),
            "R_Tb":     _query_float("R_Tb",      2.0),
            "delta_x":  _query_float("delta_x",   1.0),
            "delta_z":  _query_float("delta_z",   0.25),
            "prsity":   _query_float("prsity",    0.3),
            "al":       _query_float("al",        5.0),
            "av":       _query_float("av",        0.5),
            "gamma":    _query_float("gamma",     3.5),
            "Cd":       _query_float("Cd",        5.0),
            "Ca":       _query_float("Ca",        8.0),
            "h1":       _query_float("h1",        10.0),
            "h2":       _query_float("h2",        9.0),
            "hk":       _query_float("hk",        1.0),
            "Sw":       _query_float("Sw",        5.0),
            "R_Wu":     _query_float("R_Wu",      7.5),
            "R_Wb":     _query_float("R_Wb",      7.5),
            "alpha_th": _query_float("alpha_th",  0.1),
        }
    ])

    table = pn.widgets.Tabulator(default_df, height=320, sizing_mode="stretch_width", name="Numerical scenarios")
    run_btn = pn.widgets.Button(name="Run numerical scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(
        _result_card("Result", '<div style="font-size:1rem;color:#1f2937;">Run the scenarios to compute plume lengths.</div>'),
        sizing_mode="stretch_width",
    )
    vertical_pane    = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
    horizontal_pane  = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
    scatter_pane     = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=410)

    email            = _query_str("email", "demo@example.com")
    selected_site_id = _query_int("site_id", 0)

    _state: dict = {}

    def _pdf_callback():
        if not _state:
            return io.BytesIO(b"")
        report = CASTReport("Numerical Model \u2014 Multiple Simulation", "Numerical MODFLOW/MT3DMS")
        return io.BytesIO(report.generate(
            _state["parameters"],
            _state["outputs"],
            plot_images=_state.get("plot_images"),
        ))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="numerical_multiple_report.pdf",
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

            status_rows = []
            successful = []

            for idx, row in df.reset_index(drop=True).iterrows():
                run_btn.name = f"Running scenario {idx + 1}\u2026"
                try:
                    run_data = _run_row(row)
                    successful.append((idx + 1, run_data))
                    status_rows.append({
                        "scenario":          idx + 1,
                        "analytical_lmax_m": round(run_data["analytical_lmax"], 3),
                        "cirpka_lmax_m":     round(run_data["cirpka_lmax"], 3),
                        "v_plume_m":         round(run_data["v_result"].plume_length, 3),
                        "h_plume_m":         round(run_data["h_result"].plume_length, 3),
                        "status":            "ok",
                    })
                except Exception as exc:
                    status_rows.append({
                        "scenario":          idx + 1,
                        "analytical_lmax_m": None,
                        "cirpka_lmax_m":     None,
                        "v_plume_m":         None,
                        "h_plume_m":         None,
                        "status":            str(exc),
                    })

            run_btn.name = "Run numerical scenarios"
            table.value = pd.concat([df.reset_index(drop=True), pd.DataFrame(status_rows)], axis=1)

            if not successful:
                raise ValueError("All numerical scenarios failed.")

            v_lengths = [rd["v_result"].plume_length for _, rd in successful]
            h_lengths = [rd["h_result"].plume_length for _, rd in successful]
            result_pane.object = _result_card(
                "Simulation Summary",
                f"""
                <div style="display:flex;gap:22px;flex-wrap:wrap;">
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Successful runs</span>
                       <div style="font-size:1.8rem;font-weight:800;color:#163c66;">{len(successful)}</div></div>
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Max vertical L_max</span>
                       <div style="font-size:1.8rem;font-weight:800;color:#163c66;">{max(v_lengths):.2f} m</div></div>
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Max horizontal L_max</span>
                       <div style="font-size:1.8rem;font-weight:800;color:#163c66;">{max(h_lengths):.2f} m</div></div>
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Min vertical L_max</span>
                       <div style="font-size:1.4rem;font-weight:700;color:#24476b;">{min(v_lengths):.2f} m</div></div>
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Min horizontal L_max</span>
                       <div style="font-size:1.4rem;font-weight:700;color:#0d9887;">{min(h_lengths):.2f} m</div></div>
                </div>
                """,
            )

            # Use first successful scenario for the contour graphs
            _sc, first_run = successful[0]
            v_res = first_run["v_result"]
            h_res = first_run["h_result"]

            # Graph 1: Vertical plume (first scenario)
            vertical_pane.object = plot_vertical_plume_interactive(
                v_res.concentration, v_res.x_grid, v_res.z_grid,
                first_run["analytical_lmax"], first_run["L_D_v"],
                first_run["S_T"], first_run["R_Ta"], first_run["R_Tb"], first_run["A_T"],
            )

            # Graph 2: Horizontal plume (first scenario)
            horizontal_pane.object = plot_horizontal_plume_interactive(
                h_res.concentration, h_res.x_grid, h_res.y_grid,
                h_res.plume_length, first_run["L_D_h"],
                first_run["Sw"], first_run["A_W"],
            )

            # Graph 3: Comparison — all scenarios as grouped bars, using first scenario analytical values
            # Graph 4: Database scatter (vertical numerical runs as overlay)
            db_analytical, db_plumes, selected_site = _database_lmax_points(
                email, first_run["av"], first_run["gamma"], selected_site_id
            )
            avg_analytical = float(np.mean(db_analytical)) if db_analytical else None
            avg_plume = float(np.mean(db_plumes)) if db_plumes else None
            numerical_runs = [
                (rd["analytical_lmax"], rd["v_result"].plume_length, f"Scenario {sc}")
                for sc, rd in successful
            ]
            scatter_pane.object = plot_lmax_scatter(
                db_analytical_lmax=db_analytical,
                db_plume_lengths=db_plumes,
                numerical_lmax=v_res.plume_length,
                analytical_lmax=first_run["analytical_lmax"],
                avg_analytical_lmax=avg_analytical,
                avg_db_plume_length=avg_plume,
                selected_site=selected_site,
                numerical_runs=numerical_runs,
            )

            plot_images = [
                {
                    "title": "Vertical Plume (Scenario 1, Cross-Section)",
                    "bytes": _contour_image_bytes(
                        v_res.concentration, v_res.x_grid, v_res.z_grid,
                        "Contaminant Plume - Vertical Model",
                        "Distance Lx [m]", "Aquifer Thickness [m]",
                        v_res.plume_length, first_run["L_D_v"],
                    ),
                    "caption": "Vertical numerical plume for the first successful scenario.",
                },
                {
                    "title": "Horizontal Plume (Scenario 1, Plan View)",
                    "bytes": _contour_image_bytes(
                        h_res.concentration, h_res.x_grid, h_res.y_grid,
                        "Contaminant Plume - Horizontal Model",
                        "Distance Lx [m]", "Horizontal Width [m]",
                        h_res.plume_length, first_run["L_D_h"],
                    ),
                    "caption": "Horizontal numerical plume for the first successful scenario.",
                },
                {
                    "title": "Numerical vs Database Sites",
                    "bytes": _scatter_image_bytes(
                        db_analytical, db_plumes, numerical_runs, selected_site,
                    ),
                    "caption": "Successful numerical scenarios compared against database plume lengths.",
                },
            ]

            _state.update({
                "parameters": [
                    {"symbol": f"Sc.{s}", "name": f"Scenario {s} — Vertical L_max",   "value": f"{rd['v_result'].plume_length:.2f}", "unit": "m"}
                    for s, rd in successful
                ] + [
                    {"symbol": f"Sc.{s}h", "name": f"Scenario {s} — Horizontal L_max", "value": f"{rd['h_result'].plume_length:.2f}", "unit": "m"}
                    for s, rd in successful
                ],
                "outputs": [
                    {"label": "Scenarios run",        "value": str(len(successful)),    "unit": ""},
                    {"label": "Max vertical L_max",   "value": f"{max(v_lengths):.2f}", "unit": "m"},
                    {"label": "Max horizontal L_max", "value": f"{max(h_lengths):.2f}", "unit": "m"},
                    {"label": "Min vertical L_max",   "value": f"{min(v_lengths):.2f}", "unit": "m"},
                    {"label": "Min horizontal L_max", "value": f"{min(h_lengths):.2f}", "unit": "m"},
                ],
                "plot_images": plot_images,
            })
            export_btn.visible = True

        except Exception as exc:
            run_btn.name = "Run numerical scenarios"
            result_pane.object = _result_card("Error", f'<div style="font-size:0.98rem;color:#5f1d1d;">{exc}</div>', tone="error")
            vertical_pane.object    = None
            horizontal_pane.object  = None
            scatter_pane.object     = None
            export_btn.visible = False

    run_btn.on_click(_run)

    # ── Layout ─────────────────────────────────────────────────────────────────
    card = {
        "background": "#ffffff",
        "border": "1px solid #dce9f9",
        "border-radius": "16px",
        "box-shadow": "0 10px 24px rgba(17,24,39,0.06)",
        "padding": "14px",
    }

    controls = pn.Column(
        pn.pane.HTML('<p style="margin:0 0 6px 0;font-size:0.9rem;color:#4b5563;">Each row is one scenario. Horizontal domain width is D_w = R_Wb + Sw + R_Wu; use alpha_th for transverse horizontal dispersivity.</p>'),
        table,
        sizing_mode="stretch_width",
        styles={**card, "padding": "18px"},
    )

    def _plot_card(pane, title):
        return pn.Column(
            pn.pane.HTML(f'<h4 style="margin:0 0 8px 0;color:#1B3A6B;">{title}</h4>'),
            pane,
            sizing_mode="stretch_width",
            min_height=520,
            styles={**card, "width": "100%", "overflow": "visible"},
        )

    graphs = pn.Column(
        _plot_card(vertical_pane,   "Graph 1 \u2014 Vertical Plume (Scenario 1, Cross-Section)"),
        _plot_card(horizontal_pane, "Graph 2 \u2014 Horizontal Plume (Scenario 1, Plan View)"),
        _plot_card(scatter_pane,    "Graph 3 \u2014 Numerical vs Database Sites"),
        sizing_mode="stretch_width",
        styles={"gap": "18px", "overflow": "visible"},
    )
    export_section = pn.Column(
        pn.pane.HTML('<h3 style="margin:0 0 8px 0;color:#1B3A6B;">Report Export</h3>'),
        pn.pane.HTML('<p style="margin:0 0 10px 0;font-size:0.88rem;color:#4b5563;">Run the scenarios, then download the PDF report from here.</p>'),
        export_btn,
        sizing_mode="stretch_width",
        styles={**card, "margin-top": "20px", "margin-bottom": "32px"},
    )

    return pn.Column(
        "Each table row is a manual scenario. The vertical model uses S_T, R_Ta, and R_Tb; the horizontal model uses Sw, R_Wu, and R_Wb. Database records appear as comparison points only.",
        run_btn,
        result_pane,
        pn.pane.HTML('<h3 style="margin:6px 0 0 0;">User inputs</h3>'),
        controls,
        pn.pane.HTML('<h3 style="margin:6px 0 0 0;">Graphs (Scenario 1 shown in contour plots)</h3>'),
        graphs,
        export_section,
        sizing_mode="stretch_width",
        styles={"gap": "18px", "padding-bottom": "48px", "overflow": "visible"},
    )
