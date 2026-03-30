import panel as pn
from bokeh.plotting import figure

from data_queries import get_user_sites
from numerical_models import numerical_model

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


def numerical_single_app():
    lx = pn.widgets.FloatInput(name="Domain length Lx (m)", value=_query_float("Lx", 120.0), step=10.0)
    ly = pn.widgets.FloatInput(name="Domain width Ly (m)", value=_query_float("Ly", 20.0), step=1.0)
    ncol = pn.widgets.IntInput(name="Number of columns", value=_query_int("ncol", 60), start=2)
    nrow = pn.widgets.IntInput(name="Number of rows", value=_query_int("nrow", 20), start=2)
    prsity = pn.widgets.FloatInput(name="Porosity", value=_query_float("prsity", 0.3), step=0.01)
    al = pn.widgets.FloatInput(name="Longitudinal dispersivity al", value=_query_float("al", 5.0), step=0.1)
    av = pn.widgets.FloatInput(name="Vertical dispersivity av", value=_query_float("av", 0.5), step=0.1)
    gamma = pn.widgets.FloatInput(name="Stoichiometry gamma", value=_query_float("gamma", 3.5), step=0.1)
    cd = pn.widgets.FloatInput(name="Contaminant concentration Cd", value=_query_float("Cd", 5.0), step=0.1)
    ca = pn.widgets.FloatInput(name="Reactant concentration Ca", value=_query_float("Ca", 8.0), step=0.1)
    h1 = pn.widgets.FloatInput(name="Head h1", value=_query_float("h1", 10.0), step=0.1)
    h2 = pn.widgets.FloatInput(name="Head h2", value=_query_float("h2", 9.0), step=0.1)
    hk = pn.widgets.FloatInput(name="Hydraulic conductivity hk", value=_query_float("hk", 1.0), step=0.1)
    run_btn = pn.widgets.Button(name="Run numerical simulation", button_type="primary")
    run_btn.sizing_mode = "stretch_width"

    result_pane = pn.pane.HTML(
        """
        <div style="background:#ffffff;border:1px solid #dce9f9;border-radius:14px;padding:16px 18px;box-shadow:0 8px 24px rgba(17,24,39,0.06);">
          <div style="font-size:0.85rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#5b7a9a;margin-bottom:6px;">Result</div>
          <div style="font-size:1rem;color:#1f2937;">Run the numerical model to compute plume length.</div>
        </div>
        """,
        sizing_mode="stretch_width",
    )
    image_pane = pn.pane.HTML("", sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)

    email = _query_str("email", "demo@example.com")
    selected_site_id = _query_int("site_id", 0)

    def _run(_=None):
        try:
            plume_length, plume_img = numerical_model(
                lx.value, ly.value, ncol.value, nrow.value, prsity.value, al.value, av.value,
                gamma.value, cd.value, ca.value, h1.value, h2.value, hk.value
            )
            result_pane.object = f"""
            <div style="background:linear-gradient(135deg,#ffffff 0%,#f4f9ff 100%);border:1px solid #c4ddf5;border-radius:16px;padding:18px 20px;box-shadow:0 12px 28px rgba(17,24,39,0.08);">
              <div style="font-size:0.85rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#2f5f8f;margin-bottom:8px;">Simulation Result</div>
              <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">
                <span style="font-size:1rem;font-weight:700;color:#24476b;">Plume length</span>
                <span style="font-size:1.9rem;font-weight:800;color:#163c66;line-height:1;">{plume_length:.2f}</span>
                <span style="font-size:1rem;font-weight:700;color:#3d82b6;">m</span>
              </div>
            </div>
            """
            image_pane.object = plume_img

            field_x, field_y = ([], [])
            if selected_site_id > 0:
                field_x, field_y = _load_field_points(email)
            user_x = selected_site_id if selected_site_id > 0 else 1
            p = figure(
                title="Numerical model plume length comparison",
                x_axis_label="Site Number" if selected_site_id > 0 else "Run Number",
                y_axis_label="Plume Length (m)",
                height=420,
                sizing_mode="stretch_width",
            )
            if field_x and field_y:
                p.scatter(field_x, field_y, size=12, marker="circle", color="#7fb6e6", legend_label="Database plume length")
            p.scatter([user_x], [plume_length], size=14, marker="circle", color="#163c66", legend_label="Numerical model plume length")
            p.legend.location = "top_right"
            plot_pane.object = p
        except Exception as exc:
            result_pane.object = f"""
            <div style="background:#fff4f4;border:1px solid #f1b7b7;border-radius:14px;padding:16px 18px;box-shadow:0 8px 24px rgba(17,24,39,0.05);">
              <div style="font-size:0.85rem;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;color:#9f2d2d;margin-bottom:6px;">Error</div>
              <div style="font-size:0.98rem;color:#5f1d1d;">{exc}</div>
            </div>
            """
            image_pane.object = ""
            plot_pane.object = None

    run_btn.on_click(_run)

    action_bar = pn.Row(
        run_btn,
        sizing_mode="stretch_width",
        styles={"align-items": "stretch"},
    )

    controls = pn.Column(
        "## Numerical Model (Single Simulation)",
        "### Manual inputs",
        lx, ly, ncol, nrow, prsity, al, av, gamma, cd, ca, h1, h2, hk,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 320px", "min-width": "280px"},
    )
    outputs = pn.Column(
        image_pane,
        plot_pane,
        sizing_mode="stretch_both",
        styles={"flex": "2 1 540px", "min-width": "340px"},
    )
    body = pn.FlexBox(controls, outputs, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
    return pn.Column(
        action_bar,
        result_pane,
        body,
        sizing_mode="stretch_both",
        styles={"gap": "14px"},
    )
