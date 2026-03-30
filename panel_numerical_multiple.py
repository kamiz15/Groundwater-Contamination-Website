import pandas as pd
import panel as pn
from bokeh.plotting import figure

from data_queries import get_user_sites
from numerical_models import numerical_model

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


def _load_field_points(email):
    try:
        rows = get_user_sites(email)
    except Exception:
        return [], []
    xs, ys = [], []
    for i, row in enumerate(rows, start=1):
        try:
            plume = float(row[4])
        except Exception:
            continue
        xs.append(i)
        ys.append(plume)
    return xs, ys


def numerical_multiple_app():
    default_df = pd.DataFrame([
        {
            "Lx": _query_float("Lx", 120.0),
            "Ly": _query_float("Ly", 20.0),
            "ncol": _query_int("ncol", 60),
            "nrow": _query_int("nrow", 20),
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
        """
        <div style="background:#ffffff;border:1px solid #dce9f9;border-radius:14px;padding:16px 18px;box-shadow:0 8px 24px rgba(17,24,39,0.06);">
          <div style="font-size:0.85rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#5b7a9a;margin-bottom:6px;">Result</div>
          <div style="font-size:1rem;color:#1f2937;">Run the scenarios to compute plume lengths.</div>
        </div>
        """,
        sizing_mode="stretch_width",
    )
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    preview_pane = pn.pane.HTML("", sizing_mode="stretch_width")

    email = _query_str("email", "demo@example.com")
    selected_site_id = _query_int("site_id", 0)

    def _run(_=None):
        try:
            df = table.value
            if not isinstance(df, pd.DataFrame):
                df = pd.DataFrame(df)

            if df.empty:
                raise ValueError("No scenarios available.")

            rows = []
            preview_html = ""
            success_lengths = []
            success_x = []

            for idx, row in df.reset_index(drop=True).iterrows():
                try:
                    plume_length, plume_img = numerical_model(
                        float(row.get("Lx", 0.0)),
                        float(row.get("Ly", 0.0)),
                        int(float(row.get("ncol", 0))),
                        int(float(row.get("nrow", 0))),
                        float(row.get("prsity", 0.0)),
                        float(row.get("al", 0.0)),
                        float(row.get("av", 0.0)),
                        float(row.get("gamma", 0.0)),
                        float(row.get("Cd", 0.0)),
                        float(row.get("Ca", 0.0)),
                        float(row.get("h1", 0.0)),
                        float(row.get("h2", 0.0)),
                        float(row.get("hk", 0.0)),
                    )
                    rows.append({"scenario": idx + 1, "plume_length_m": round(plume_length, 3), "status": "ok"})
                    success_lengths.append(plume_length)
                    success_x.append(idx + 1)
                    if not preview_html:
                        preview_html = plume_img
                except Exception as exc:
                    rows.append({"scenario": idx + 1, "plume_length_m": None, "status": str(exc)})

            table.value = pd.concat([df.reset_index(drop=True), pd.DataFrame(rows)], axis=1)

            if not success_lengths:
                raise ValueError("All numerical scenarios failed.")

            result_pane.object = f"""
            <div style="background:linear-gradient(135deg,#ffffff 0%,#f4f9ff 100%);border:1px solid #c4ddf5;border-radius:16px;padding:18px 20px;box-shadow:0 12px 28px rgba(17,24,39,0.08);">
              <div style="font-size:0.85rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#2f5f8f;margin-bottom:8px;">Simulation Summary</div>
              <div style="display:flex;gap:18px;flex-wrap:wrap;">
                <div><span style="font-size:0.92rem;color:#5b7a9a;">Successful runs</span><div style="font-size:1.8rem;font-weight:800;color:#163c66;">{len(success_lengths)}</div></div>
                <div><span style="font-size:0.92rem;color:#5b7a9a;">Max plume length</span><div style="font-size:1.8rem;font-weight:800;color:#163c66;">{max(success_lengths):.2f} m</div></div>
              </div>
            </div>
            """

            field_x, field_y = ([], [])
            if selected_site_id > 0:
                field_x, field_y = _load_field_points(email)

            p = figure(
                title="Numerical model plume length comparison",
                x_axis_label="Site Number" if selected_site_id > 0 else "Scenario Number",
                y_axis_label="Plume Length (m)",
                height=420,
                sizing_mode="stretch_width",
            )
            p.scatter(success_x, success_lengths, size=12, marker="circle", color="#163c66", legend_label="Numerical model plume length")
            if field_x and field_y:
                p.scatter(field_x, field_y, size=12, marker="circle", color="#7fb6e6", legend_label="Database plume length")
            p.legend.location = "top_right"
            plot_pane.object = p
            preview_pane.object = preview_html
        except Exception as exc:
            result_pane.object = f"""
            <div style="background:#fff4f4;border:1px solid #f1b7b7;border-radius:14px;padding:16px 18px;box-shadow:0 8px 24px rgba(17,24,39,0.05);">
              <div style="font-size:0.85rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#9f2d2d;margin-bottom:6px;">Error</div>
              <div style="font-size:0.98rem;color:#5f1d1d;">{exc}</div>
            </div>
            """
            preview_pane.object = ""
            plot_pane.object = None

    run_btn.on_click(_run)

    controls = pn.Column(
        "## Numerical Model (Multiple Simulation)",
        "### Manual scenario inputs",
        table,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 380px", "min-width": "300px"},
    )
    outputs = pn.Column(
        preview_pane,
        plot_pane,
        sizing_mode="stretch_both",
        styles={"flex": "2 1 540px", "min-width": "340px"},
    )
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(run_btn, result_pane, body, sizing_mode="stretch_both", styles={"gap": "14px"})
