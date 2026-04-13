import numpy as np
import pandas as pd
import panel as pn

from analytical_models import liedl_lmax
from data_queries import get_user_sites
from numerical_models import run_numerical_model
from plot_functions import plot_lmax_scatter, plot_vertical_plume_interactive

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


def _run_row(row):
    S_T = float(row.get("S_T", 1.0))
    S_Ta = float(row.get("S_Ta", 2.0))
    S_Tb = float(row.get("S_Tb", 2.0))
    delta_x = float(row.get("delta_x", 1.0))
    delta_z = float(row.get("delta_z", 0.25))
    prsity = float(row.get("prsity", 0.3))
    al = float(row.get("al", 5.0))
    av = float(row.get("av", 0.5))
    gamma = float(row.get("gamma", 3.5))
    Cd = float(row.get("Cd", 5.0))
    Ca = float(row.get("Ca", 8.0))
    h1 = float(row.get("h1", 10.0))
    h2 = float(row.get("h2", 9.0))
    hk = float(row.get("hk", 1.0))

    if S_T <= 0:
        raise ValueError("Source thickness ST must be greater than zero.")
    if S_Ta < 0 or S_Tb < 0:
        raise ValueError("Source buffers ST_a and ST_b cannot be negative.")
    if delta_x <= 0 or delta_z <= 0:
        raise ValueError("Grid spacing must be greater than zero.")
    if h1 <= h2:
        raise ValueError("Head h1 must be greater than head h2.")

    A_T = S_Tb + S_Ta + S_T
    if S_T > A_T:
        raise ValueError("Source thickness ST cannot exceed aquifer thickness AT.")
    analytical_lmax = liedl_lmax(A_T, av, gamma, Ca, Cd)
    if analytical_lmax <= 0:
        raise ValueError("Liedl analytical Lmax must be positive.")
    L_D = 1.5 * analytical_lmax
    n_cols = int(np.ceil(L_D / delta_x))
    n_rows = int(np.ceil(A_T / delta_z))
    if n_cols < 2 or n_rows < 2:
        raise ValueError("Grid spacing too coarse - reduce Delta X or Delta Z.")

    result = run_numerical_model(L_D, A_T, n_cols, n_rows, prsity, al, av, gamma, Cd, Ca, h1, h2, hk)
    return {
        "result": result,
        "analytical_lmax": analytical_lmax,
        "L_D": L_D,
        "A_T": A_T,
        "S_T": S_T,
        "S_Ta": S_Ta,
        "S_Tb": S_Tb,
        "av": av,
        "gamma": gamma,
    }


def numerical_multiple_app():
    default_df = pd.DataFrame([
        {
            "S_T": _query_float("S_T", 1.0),
            "S_Ta": _query_float("S_Ta", 2.0),
            "S_Tb": _query_float("S_Tb", 2.0),
            "delta_x": _query_float("delta_x", 1.0),
            "delta_z": _query_float("delta_z", 0.25),
            "prsity": _query_float("prsity", 0.3),
            "al": _query_float("al", 5.0),
            "av": _query_float("av", 0.5),
            "gamma": _query_float("gamma", 3.5),
            "Cd": _query_float("Cd", 5.0),
            "Ca": _query_float("Ca", 8.0),
            "h1": _query_float("h1", 10.0),
            "h2": _query_float("h2", 9.0),
            "hk": _query_float("hk", 1.0),
        }
    ])

    table = pn.widgets.Tabulator(default_df, height=320, sizing_mode="stretch_width", name="Numerical scenarios")
    run_btn = pn.widgets.Button(name="Run numerical scenarios", button_type="primary", sizing_mode="stretch_width")
    result_pane = pn.pane.HTML(
        _result_card("Result", '<div style="font-size:1rem;color:#1f2937;">Run the scenarios to compute plume lengths.</div>'),
        sizing_mode="stretch_width",
    )
    contour_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=430)
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)

    email = _query_str("email", "demo@example.com")
    selected_site_id = _query_int("site_id", 0)

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
                try:
                    run_data = _run_row(row)
                    result = run_data["result"]
                    successful.append((idx + 1, run_data))
                    status_rows.append(
                        {
                            "scenario": idx + 1,
                            "analytical_lmax_m": round(run_data["analytical_lmax"], 3),
                            "domain_LD_m": round(run_data["L_D"], 3),
                            "plume_length_m": round(result.plume_length, 3),
                            "status": "ok",
                        }
                    )
                except Exception as exc:
                    status_rows.append(
                        {
                            "scenario": idx + 1,
                            "analytical_lmax_m": None,
                            "domain_LD_m": None,
                            "plume_length_m": None,
                            "status": str(exc),
                        }
                    )

            table.value = pd.concat([df.reset_index(drop=True), pd.DataFrame(status_rows)], axis=1)
            if not successful:
                raise ValueError("All numerical scenarios failed.")

            lengths = [run_data["result"].plume_length for _scenario, run_data in successful]
            result_pane.object = _result_card(
                "Simulation Summary",
                f"""
                <div style="display:flex;gap:22px;flex-wrap:wrap;">
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Successful runs</span><div style="font-size:1.8rem;font-weight:800;color:#163c66;">{len(successful)}</div></div>
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Max plume length</span><div style="font-size:1.8rem;font-weight:800;color:#163c66;">{max(lengths):.2f} m</div></div>
                  <div><span style="font-size:0.92rem;color:#5b7a9a;">Min plume length</span><div style="font-size:1.8rem;font-weight:800;color:#163c66;">{min(lengths):.2f} m</div></div>
                </div>
                """,
            )

            first_scenario, first_run = successful[0]
            first_result = first_run["result"]
            contour_pane.object = plot_vertical_plume_interactive(
                first_result.concentration,
                first_result.x_grid,
                first_result.z_grid,
                first_run["analytical_lmax"],
                first_run["L_D"],
                first_run["S_T"],
                first_run["S_Ta"],
                first_run["S_Tb"],
                first_run["A_T"],
            )

            alpha_tv_for_db = first_run["av"]
            gamma_for_db = first_run["gamma"]
            db_analytical, db_plumes, selected_site = _database_lmax_points(
                email, alpha_tv_for_db, gamma_for_db, selected_site_id
            )
            avg_analytical = float(np.mean(db_analytical)) if db_analytical else None
            avg_plume = float(np.mean(db_plumes)) if db_plumes else None
            numerical_runs = [
                (run_data["analytical_lmax"], run_data["result"].plume_length, f"Scenario {scenario}")
                for scenario, run_data in successful
            ]
            plot_pane.object = plot_lmax_scatter(
                db_analytical_lmax=db_analytical,
                db_plume_lengths=db_plumes,
                numerical_lmax=successful[0][1]["result"].plume_length,
                analytical_lmax=successful[0][1]["analytical_lmax"],
                avg_analytical_lmax=avg_analytical,
                avg_db_plume_length=avg_plume,
                selected_site=selected_site,
                numerical_runs=numerical_runs,
            )
        except Exception as exc:
            result_pane.object = _result_card("Error", f'<div style="font-size:0.98rem;color:#5f1d1d;">{exc}</div>', tone="error")
            contour_pane.object = None
            plot_pane.object = None

    run_btn.on_click(_run)

    controls = pn.Column(
        table,
        sizing_mode="stretch_width",
        styles={
            "background": "#ffffff",
            "border": "1px solid #dce9f9",
            "border-radius": "16px",
            "box-shadow": "0 10px 24px rgba(17,24,39,0.06)",
            "padding": "18px",
        },
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
        "Each table row is a manual scenario; uploaded database records remain separate and appear only as comparison points.",
        run_btn,
        result_pane,
        pn.pane.HTML('<h3 style="margin:6px 0 0 0;">User inputs</h3>'),
        controls,
        pn.pane.HTML('<h3 style="margin:6px 0 0 0;">Graphs</h3>'),
        graphs,
        sizing_mode="stretch_both",
        styles={"gap": "16px"},
    )
