import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
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

pn.extension(sizing_mode="stretch_width")


# ── Query helpers ──────────────────────────────────────────────────────────────

def _query_float(name, default):
    try:
        req = pn.state.curdoc.session_context.request
        raw = req.arguments.get(name, [str(default).encode()])[0].decode()
        return float(raw)
    except Exception:
        return default


def _query_int(name, default):
    try:
        req = pn.state.curdoc.session_context.request
        raw = req.arguments.get(name, [str(default).encode()])[0].decode()
        return int(float(raw))
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


# ── App ────────────────────────────────────────────────────────────────────────

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


def _scatter_image_bytes(db_analytical, db_plumes, numerical_lmax, analytical_lmax, selected_site=None):
    fig, ax = plt.subplots(figsize=(8.5, 5.2), dpi=180)
    clean_x = _clean_numeric(db_analytical)
    clean_y = _clean_numeric(db_plumes)
    if clean_x and clean_y:
        n = min(len(clean_x), len(clean_y))
        ax.scatter(clean_x[:n], clean_y[:n], s=28, alpha=0.5, color="#AED6F1", label="Database plume length")
    ax.scatter([analytical_lmax], [numerical_lmax], s=70, marker="^", color="#1B3A6B", label="Numerical Lmax")
    if selected_site:
        ax.scatter([selected_site["analytical_lmax"]], [selected_site["plume_length"]], s=90, marker="x", color="#DB2777", label="Selected site")
    vals = clean_x + clean_y + _clean_numeric([numerical_lmax, analytical_lmax])
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


def numerical_single_app():
    # -- Vertical model inputs --
    s_t      = pn.widgets.FloatInput(name="Source Thickness S_T [m]",                 value=_query_float("S_T", 1.0),    step=0.1)
    r_ta     = pn.widgets.FloatInput(name="Upper Reactant Buffer R_Ta [m]",            value=_query_float("R_Ta", 2.0),   step=0.1)
    r_tb     = pn.widgets.FloatInput(name="Lower Reactant Buffer R_Tb [m]",            value=_query_float("R_Tb", 2.0),   step=0.1)
    delta_x  = pn.widgets.FloatInput(name="Grid Spacing \u0394x [m]",                  value=_query_float("delta_x", 1.0), step=0.1)
    delta_z  = pn.widgets.FloatInput(name="Vertical/Lateral Grid Spacing \u0394z or \u0394y [m]", value=_query_float("delta_z", 0.25),step=0.05)
    prsity   = pn.widgets.FloatInput(name="Porosity n [-]",                           value=_query_float("prsity", 0.3),  step=0.01)
    al       = pn.widgets.FloatInput(name="Longitudinal Dispersivity \u03b1L [m]",      value=_query_float("al", 5.0),     step=0.1)
    av       = pn.widgets.FloatInput(name="Transverse Vertical Dispersivity \u03b1Tv [m]", value=_query_float("av", 0.5),     step=0.1)
    gamma    = pn.widgets.FloatInput(name="Stoichiometric Ratio \u03b3 [-]",            value=_query_float("gamma", 3.5),  step=0.1)
    cd       = pn.widgets.FloatInput(name="Source Concentration C_D [mg/L]",           value=_query_float("Cd", 5.0),     step=0.1)
    ca       = pn.widgets.FloatInput(name="Reactant Concentration C_A [mg/L]",         value=_query_float("Ca", 8.0),     step=0.1)
    h1       = pn.widgets.FloatInput(name="Head at Left Domain H_L [m]",               value=_query_float("h1", 10.0),    step=0.1)
    h2       = pn.widgets.FloatInput(name="Head at Right Domain H_R [m]",              value=_query_float("h2", 9.0),     step=0.1)
    hk       = pn.widgets.FloatInput(name="Hydraulic Conductivity K [m/d]",            value=_query_float("hk", 1.0),     step=0.1)

    # -- Horizontal model inputs --
    sw       = pn.widgets.FloatInput(name="Source Width S_w [m]",                       value=_query_float("Sw", 5.0),     step=0.1)
    r_wu     = pn.widgets.FloatInput(name="Upper Reactant Buffer R_Wu [m]",             value=_query_float("R_Wu", 7.5),   step=0.1)
    r_wb     = pn.widgets.FloatInput(name="Lower Reactant Buffer R_Wb [m]",             value=_query_float("R_Wb", 7.5),   step=0.1)
    alpha_th = pn.widgets.FloatInput(name="Transverse Horizontal Dispersivity \u03b1Th [m]", value=_query_float("alpha_Th", 0.1), step=0.01)

    run_btn = pn.widgets.Button(name="Run Numerical Simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane  = pn.pane.HTML(
        _result_card("Ready", '<div style="font-size:1rem;color:#1f2937;">Run the model to compute plume lengths.</div>'),
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
        report = CASTReport("Numerical Model \u2014 Single Simulation", "Numerical MODFLOW/MT3DMS")
        return io.BytesIO(report.generate(
            _state["parameters"],
            _state["outputs"],
            plot_images=_state.get("plot_images"),
        ))

    export_btn = pn.widgets.FileDownload(
        callback=_pdf_callback, filename="numerical_single_report.pdf",
        label="\u2193 Download PDF Report", button_type="primary",
        sizing_mode="stretch_width", visible=False,
    )

    def _run(_=None):
        try:
            if s_t.value <= 0:
                raise ValueError("Source thickness ST must be greater than zero.")
            if r_ta.value < 0 or r_tb.value < 0:
                raise ValueError("Source buffers R_Ta and R_Tb cannot be negative.")
            if delta_x.value <= 0 or delta_z.value <= 0:
                raise ValueError("Grid spacing must be greater than zero.")
            if h1.value <= h2.value:
                raise ValueError("Head h1 must be greater than head h2.")
            if sw.value <= 0:
                raise ValueError("Source width Sw must be positive.")
            if r_wu.value < 0 or r_wb.value < 0:
                raise ValueError("Horizontal reactant buffers R_Wu and R_Wb cannot be negative.")
            if alpha_th.value <= 0:
                raise ValueError("Horizontal dispersivity \u03b1Th must be positive.")

            # ── Vertical model ────────────────────────────────────────────────
            A_T = r_tb.value + r_ta.value + s_t.value
            analytical_lmax = liedl_lmax(A_T, av.value, gamma.value, ca.value, cd.value)
            if analytical_lmax <= 0:
                raise ValueError("Liedl Lmax must be positive.")
            L_D_v = 1.5 * analytical_lmax
            n_cols_v = int(np.ceil(L_D_v / delta_x.value))
            n_rows_v = int(np.ceil(A_T / delta_z.value))
            if n_cols_v < 2 or n_rows_v < 2:
                raise ValueError("Vertical grid too coarse \u2014 reduce \u0394x or \u0394z.")

            run_btn.name = "Running vertical model\u2026"
            v_result = run_numerical_model(
                L_D_v, A_T, n_cols_v, n_rows_v,
                prsity.value, al.value, av.value,
                gamma.value, cd.value, ca.value,
                h1.value, h2.value, hk.value,
            )

            # ── Horizontal model ──────────────────────────────────────────────
            cirpka_lmax_val = _cirpka_lmax(sw.value, alpha_th.value, gamma.value, ca.value, cd.value)
            L_D_h = cirpka_domain_length(cirpka_lmax_val)
            A_W = r_wb.value + sw.value + r_wu.value
            n_cols_h = int(np.ceil(L_D_h / delta_x.value))
            n_rows_h = int(np.ceil(A_W / delta_z.value))
            if n_cols_h < 2 or n_rows_h < 2:
                raise ValueError("Horizontal grid too coarse \u2014 reduce \u0394x or \u0394z.")

            run_btn.name = "Running horizontal model\u2026"
            h_result = run_numerical_model_horizontal(
                L_D_h, A_W, sw.value,
                n_cols_h, n_rows_h,
                prsity.value, al.value, alpha_th.value,
                gamma.value, cd.value, ca.value,
                h1.value, h2.value, hk.value,
            )
            run_btn.name = "Run Numerical Simulation"

            # ── Result card ───────────────────────────────────────────────────
            result_pane.object = _result_card(
                "Simulation Results",
                f"""
                <div style="display:flex;gap:22px;flex-wrap:wrap;align-items:baseline;">
                  <div><span style="font-size:0.88rem;color:#5b7a9a;">Vertical plume L_max</span>
                       <div style="font-size:1.8rem;font-weight:800;color:#163c66;">{v_result.plume_length:.2f} m</div></div>
                  <div><span style="font-size:0.88rem;color:#5b7a9a;">Horizontal plume L_max</span>
                       <div style="font-size:1.8rem;font-weight:800;color:#163c66;">{h_result.plume_length:.2f} m</div></div>
                  <div><span style="font-size:0.88rem;color:#5b7a9a;">Liedl analytical</span>
                       <div style="font-size:1.4rem;font-weight:700;color:#24476b;">{analytical_lmax:.2f} m</div></div>
                  <div><span style="font-size:0.88rem;color:#5b7a9a;">Cirpka analytical</span>
                       <div style="font-size:1.4rem;font-weight:700;color:#0d9887;">{cirpka_lmax_val:.2f} m</div></div>
                </div>
                """,
            )

            # ── Graph 1: Vertical plume ───────────────────────────────────────
            vertical_pane.object = plot_vertical_plume_interactive(
                v_result.concentration, v_result.x_grid, v_result.z_grid,
                analytical_lmax, L_D_v, s_t.value, r_ta.value, r_tb.value, A_T,
            )

            # ── Graph 2: Horizontal plume ─────────────────────────────────────
            horizontal_pane.object = plot_horizontal_plume_interactive(
                h_result.concentration, h_result.x_grid, h_result.y_grid,
                h_result.plume_length, L_D_h, sw.value, A_W,
            )

            # ── Graph 3: Numerical vs Cirpka comparison ───────────────────────
            # ── Database scatter (bonus) ──────────────────────────────────────
            db_analytical, db_plumes, selected_site = _database_lmax_points(
                email, av.value, gamma.value, selected_site_id
            )
            avg_analytical = float(np.mean(db_analytical)) if db_analytical else None
            avg_plume = float(np.mean(db_plumes)) if db_plumes else None
            scatter_pane.object = plot_lmax_scatter(
                db_analytical_lmax=db_analytical,
                db_plume_lengths=db_plumes,
                numerical_lmax=v_result.plume_length,
                analytical_lmax=analytical_lmax,
                avg_analytical_lmax=avg_analytical,
                avg_db_plume_length=avg_plume,
                selected_site=selected_site,
            )

            plot_images = [
                {
                    "title": "Vertical Plume (Cross-Section)",
                    "bytes": _contour_image_bytes(
                        v_result.concentration, v_result.x_grid, v_result.z_grid,
                        "Contaminant Plume - Vertical Model",
                        "Distance Lx [m]", "Aquifer Thickness [m]",
                        v_result.plume_length, L_D_v,
                    ),
                    "caption": "Vertical numerical plume generated by the MODFLOW/MT3DMS model.",
                },
                {
                    "title": "Horizontal Plume (Plan View)",
                    "bytes": _contour_image_bytes(
                        h_result.concentration, h_result.x_grid, h_result.y_grid,
                        "Contaminant Plume - Horizontal Model",
                        "Distance Lx [m]", "Horizontal Width [m]",
                        h_result.plume_length, L_D_h,
                    ),
                    "caption": "Horizontal numerical plume generated by the MODFLOW/MT3DMS model.",
                },
                {
                    "title": "Numerical vs Database Sites",
                    "bytes": _scatter_image_bytes(
                        db_analytical, db_plumes, v_result.plume_length,
                        analytical_lmax, selected_site,
                    ),
                    "caption": "Numerical plume length compared against database plume lengths.",
                },
            ]

            _state.update({
                "parameters": [
                    {"symbol": "S_T",         "name": "Source Thickness",         "value": s_t.value,      "unit": "m"},
                    {"symbol": "R_Ta",        "name": "Buffer Above Source",       "value": r_ta.value,     "unit": "m"},
                    {"symbol": "R_Tb",        "name": "Buffer Below Source",       "value": r_tb.value,     "unit": "m"},
                    {"symbol": "S_w",         "name": "Source Width",              "value": sw.value,       "unit": "m"},
                    {"symbol": "R_Wu",        "name": "Upper Reactant Buffer",      "value": r_wu.value,     "unit": "m"},
                    {"symbol": "R_Wb",        "name": "Lower Reactant Buffer",      "value": r_wb.value,     "unit": "m"},
                    {"symbol": "\u0394x",     "name": "Grid Spacing X",            "value": delta_x.value,  "unit": "m"},
                    {"symbol": "\u0394z",     "name": "Grid Spacing Z",            "value": delta_z.value,  "unit": "m"},
                    {"symbol": "n",           "name": "Porosity",                  "value": prsity.value,   "unit": "-"},
                    {"symbol": "\u03b1L",     "name": "Long. Dispersivity",        "value": al.value,       "unit": "m"},
                    {"symbol": "\u03b1Tv",    "name": "Transverse Vertical Dispersivity", "value": av.value, "unit": "m"},
                    {"symbol": "\u03b1Th",    "name": "Transverse Horizontal Dispersivity", "value": alpha_th.value, "unit": "m"},
                    {"symbol": "\u03b3",      "name": "Stoichiometric Ratio",       "value": gamma.value,    "unit": "-"},
                    {"symbol": "C_D",         "name": "Source Concentration",       "value": cd.value,       "unit": "mg/L"},
                    {"symbol": "C_A",         "name": "Reactant Concentration",     "value": ca.value,       "unit": "mg/L"},
                    {"symbol": "K",           "name": "Hydraulic Conductivity",    "value": hk.value,       "unit": "m/d"},
                ],
                "outputs": [
                    {"label": "Vertical Numerical L_max",  "value": f"{v_result.plume_length:.2f}", "unit": "m"},
                    {"label": "Horizontal Numerical L_max","value": f"{h_result.plume_length:.2f}", "unit": "m"},
                    {"label": "Liedl Analytical L_max",    "value": f"{analytical_lmax:.2f}",       "unit": "m"},
                    {"label": "Cirpka Analytical L_max",   "value": f"{cirpka_lmax_val:.2f}",       "unit": "m"},
                ],
                "plot_images": plot_images,
            })
            export_btn.visible = True

        except Exception as exc:
            run_btn.name = "Run Numerical Simulation"
            result_pane.object = _result_card("Error", f'<div style="font-size:0.98rem;color:#5f1d1d;">{exc}</div>', tone="error")
            vertical_pane.object   = None
            horizontal_pane.object = None
            scatter_pane.object    = None
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

    domain_card = pn.Column(
        pn.pane.HTML('<h3 style="margin:0 0 12px 0;">Vertical model</h3>'),
        s_t, r_ta, r_tb, delta_x, delta_z,
        sizing_mode="stretch_width",
        styles={**card, "flex": "1 1 320px", "min-width": "280px"},
    )
    transport_card = pn.Column(
        pn.pane.HTML('<h3 style="margin:0 0 12px 0;">Transport &amp; flow</h3>'),
        prsity, al, av, gamma, cd, ca, h1, h2, hk,
        sizing_mode="stretch_width",
        styles={**card, "flex": "1 1 320px", "min-width": "280px"},
    )
    horiz_card = pn.Column(
        pn.pane.HTML('<h3 style="margin:0 0 12px 0;">Horizontal model</h3>'),
        sw, r_wu, r_wb, alpha_th,
        pn.pane.HTML('<p style="font-size:0.8rem;color:#6b7280;margin:4px 0 0 0;">Domain width D_w = R_Wb + S_w + R_Wu. Cirpka L_max drives domain length.</p>'),
        sizing_mode="stretch_width",
        styles={**card, "flex": "1 1 260px", "min-width": "240px"},
    )
    inputs = pn.FlexBox(domain_card, transport_card, horiz_card,
                        sizing_mode="stretch_width", flex_wrap="wrap", styles={"gap": "14px"})

    def _plot_card(pane, title):
        return pn.Column(
            pn.pane.HTML(f'<h4 style="margin:0 0 8px 0;color:#1B3A6B;">{title}</h4>'),
            pane,
            sizing_mode="stretch_width",
            min_height=520,
            styles={**card, "width": "100%", "overflow": "visible"},
        )

    graphs = pn.Column(
        _plot_card(vertical_pane,   "Graph 1 \u2014 Vertical Plume (Cross-Section)"),
        _plot_card(horizontal_pane, "Graph 2 \u2014 Horizontal Plume (Plan View)"),
        _plot_card(scatter_pane,    "Graph 3 \u2014 Numerical vs Database Sites"),
        sizing_mode="stretch_width",
        styles={"gap": "18px", "overflow": "visible"},
    )
    export_section = pn.Column(
        pn.pane.HTML('<h3 style="margin:0 0 8px 0;color:#1B3A6B;">Report Export</h3>'),
        pn.pane.HTML('<p style="margin:0 0 10px 0;font-size:0.88rem;color:#4b5563;">Run the simulation, then download the PDF report from here.</p>'),
        export_btn,
        sizing_mode="stretch_width",
        styles={**card, "margin-top": "20px", "margin-bottom": "32px"},
    )

    return pn.Column(
        "Run the model below. Both vertical (cross-section) and horizontal (plan-view) simulations execute sequentially.",
        run_btn,
        result_pane,
        pn.pane.HTML('<h3 style="margin:6px 0 0 0;">Input Parameters</h3>'),
        inputs,
        pn.pane.HTML('<h3 style="margin:6px 0 0 0;">Model Graphs</h3>'),
        graphs,
        export_section,
        sizing_mode="stretch_width",
        styles={"gap": "18px", "padding-bottom": "48px", "overflow": "visible"},
    )
