import numpy as np
import panel as pn

from analytical_models import liedl_lmax
from data_queries import get_user_sites
from numerical_models import run_numerical_model
from plot_functions import plot_lmax_scatter, plot_vertical_plume_interactive

pn.extension(sizing_mode="stretch_width")


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


def numerical_single_app():
    s_t = pn.widgets.FloatInput(name="Source Thickness ST [m]", value=_query_float("S_T", 1.0), step=0.1)
    s_ta = pn.widgets.FloatInput(name="Buffer Above ST_a [m]", value=_query_float("S_Ta", 2.0), step=0.1)
    s_tb = pn.widgets.FloatInput(name="Buffer Below ST_b [m]", value=_query_float("S_Tb", 2.0), step=0.1)
    delta_x = pn.widgets.FloatInput(name="Grid Spacing Delta X [m]", value=_query_float("delta_x", 1.0), step=0.1)
    delta_z = pn.widgets.FloatInput(name="Grid Spacing Delta Z [m]", value=_query_float("delta_z", 0.25), step=0.05)
    prsity = pn.widgets.FloatInput(name="Porosity", value=_query_float("prsity", 0.3), step=0.01)
    al = pn.widgets.FloatInput(name="Longitudinal dispersivity al", value=_query_float("al", 5.0), step=0.1)
    av = pn.widgets.FloatInput(name="Vertical dispersivity av", value=_query_float("av", 0.5), step=0.1)
    gamma = pn.widgets.FloatInput(name="Stoichiometry gamma", value=_query_float("gamma", 3.5), step=0.1)
    cd = pn.widgets.FloatInput(name="Contaminant concentration Cd", value=_query_float("Cd", 5.0), step=0.1)
    ca = pn.widgets.FloatInput(name="Reactant concentration Ca", value=_query_float("Ca", 8.0), step=0.1)
    h1 = pn.widgets.FloatInput(name="Head h1", value=_query_float("h1", 10.0), step=0.1)
    h2 = pn.widgets.FloatInput(name="Head h2", value=_query_float("h2", 9.0), step=0.1)
    hk = pn.widgets.FloatInput(name="Hydraulic conductivity hk", value=_query_float("hk", 1.0), step=0.1)
    run_btn = pn.widgets.Button(name="Run numerical simulation", button_type="primary", sizing_mode="stretch_width")

    result_pane = pn.pane.HTML(
        _result_card("Result", '<div style="font-size:1rem;color:#1f2937;">Run the numerical model to compute plume length.</div>'),
        sizing_mode="stretch_width",
    )
    contour_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)

    email = _query_str("email", "demo@example.com")
    selected_site_id = _query_int("site_id", 0)

    def _run(_=None):
        try:
            if s_t.value <= 0:
                raise ValueError("Source thickness ST must be greater than zero.")
            if s_ta.value < 0 or s_tb.value < 0:
                raise ValueError("Source buffers ST_a and ST_b cannot be negative.")
            if delta_x.value <= 0 or delta_z.value <= 0:
                raise ValueError("Grid spacing must be greater than zero.")
            if h1.value <= h2.value:
                raise ValueError("Head h1 must be greater than head h2.")

            A_T = s_tb.value + s_ta.value + s_t.value
            if s_t.value > A_T:
                raise ValueError("Source thickness ST cannot exceed aquifer thickness AT.")

            analytical_lmax = liedl_lmax(A_T, av.value, gamma.value, ca.value, cd.value)
            if analytical_lmax <= 0:
                raise ValueError("Liedl analytical Lmax must be positive. Check concentrations and dispersivity.")
            L_D = 1.5 * analytical_lmax
            n_cols = int(np.ceil(L_D / delta_x.value))
            n_rows = int(np.ceil(A_T / delta_z.value))
            if n_cols < 2 or n_rows < 2:
                raise ValueError("Grid spacing too coarse - reduce Delta X or Delta Z.")

            result = run_numerical_model(
                L_D,
                A_T,
                n_cols,
                n_rows,
                prsity.value,
                al.value,
                av.value,
                gamma.value,
                cd.value,
                ca.value,
                h1.value,
                h2.value,
                hk.value,
            )

            result_pane.object = _result_card(
                "Simulation Result",
                f"""
                <div style="display:flex;gap:22px;flex-wrap:wrap;align-items:baseline;">
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Numerical plume length</span><div style="font-size:1.9rem;font-weight:800;color:#163c66;">{result.plume_length:.2f} m</div></div>
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Analytical Lmax</span><div style="font-size:1.5rem;font-weight:800;color:#24476b;">{analytical_lmax:.2f} m</div></div>
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Domain LD</span><div style="font-size:1.5rem;font-weight:800;color:#24476b;">{L_D:.2f} m</div></div>
                </div>
                """,
            )

            contour_fig = plot_vertical_plume_interactive(
                result.concentration,
                result.x_grid,
                result.z_grid,
                analytical_lmax,
                L_D,
                s_t.value,
                s_ta.value,
                s_tb.value,
                A_T,
            )
            contour_pane.object = contour_fig

            db_analytical, db_plumes, selected_site = _database_lmax_points(
                email, av.value, gamma.value, selected_site_id
            )
            avg_analytical = float(np.mean(db_analytical)) if db_analytical else None
            avg_plume = float(np.mean(db_plumes)) if db_plumes else None
            plot_pane.object = plot_lmax_scatter(
                db_analytical_lmax=db_analytical,
                db_plume_lengths=db_plumes,
                numerical_lmax=result.plume_length,
                analytical_lmax=analytical_lmax,
                avg_analytical_lmax=avg_analytical,
                avg_db_plume_length=avg_plume,
                selected_site=selected_site,
            )
        except Exception as exc:
            result_pane.object = _result_card("Error", f'<div style="font-size:0.98rem;color:#5f1d1d;">{exc}</div>', tone="error")
            contour_pane.object = None
            plot_pane.object = None

    run_btn.on_click(_run)

    card_style = {
        "background": "#ffffff",
        "border": "1px solid #dce9f9",
        "border-radius": "16px",
        "box-shadow": "0 10px 24px rgba(17,24,39,0.06)",
        "padding": "18px",
        "flex": "1 1 420px",
        "min-width": "300px",
        "min-height": "455px",
    }
    domain_card = pn.Column(
        pn.pane.HTML('<h3 style="margin:0 0 14px 0;">Domain and source</h3>'),
        s_t,
        s_ta,
        s_tb,
        delta_x,
        delta_z,
        sizing_mode="stretch_width",
        styles=card_style,
    )
    transport_card = pn.Column(
        pn.pane.HTML('<h3 style="margin:0 0 14px 0;">Transport parameters</h3>'),
        prsity,
        al,
        av,
        gamma,
        cd,
        ca,
        h1,
        h2,
        hk,
        sizing_mode="stretch_width",
        styles=card_style,
    )
    inputs = pn.FlexBox(
        domain_card,
        transport_card,
        sizing_mode="stretch_width",
        flex_wrap="wrap",
        styles={"gap": "16px"},
    )
    contour_card = pn.Column(
        contour_pane,
        sizing_mode="stretch_both",
        styles={
            "background": "#ffffff",
            "border": "1px solid #dce9f9",
            "border-radius": "16px",
            "box-shadow": "0 10px 24px rgba(17,24,39,0.06)",
            "padding": "14px",
            "flex": "1 1 520px",
            "min-width": "340px",
        },
    )
    scatter_card = pn.Column(
        plot_pane,
        sizing_mode="stretch_both",
        styles={
            "background": "#ffffff",
            "border": "1px solid #dce9f9",
            "border-radius": "16px",
            "box-shadow": "0 10px 24px rgba(17,24,39,0.06)",
            "padding": "14px",
            "flex": "1 1 520px",
            "min-width": "340px",
        },
    )
    graphs = pn.FlexBox(
        contour_card,
        scatter_card,
        sizing_mode="stretch_both",
        flex_wrap="wrap",
        styles={"gap": "16px"},
    )
    return pn.Column(
        "Run manual model inputs below; uploaded database records remain separate and appear only as comparison points.",
        run_btn,
        result_pane,
        pn.pane.HTML('<h3 style="margin:6px 0 0 0;">User inputs</h3>'),
        inputs,
        pn.pane.HTML('<h3 style="margin:6px 0 0 0;">Graphs</h3>'),
        graphs,
        sizing_mode="stretch_both",
        styles={"gap": "16px"},
    )
