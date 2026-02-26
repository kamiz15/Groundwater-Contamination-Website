import panel as pn
from bokeh.plotting import figure

from data_queries import get_user_sites
from empirical_models import maier_lmax

pn.extension(sizing_mode="stretch_width")


def _query_float(name, default):
    try:
        req = pn.state.curdoc.session_context.request
        raw = req.arguments.get(name, [str(default).encode()])[0].decode()
        return float(raw)
    except Exception:
        return default


def _query_str(name, default=""):
    try:
        req = pn.state.curdoc.session_context.request
        return req.arguments.get(name, [default.encode()])[0].decode()
    except Exception:
        return default


def _query_int(name, default=0):
    try:
        req = pn.state.curdoc.session_context.request
        return int(float(req.arguments.get(name, [str(default).encode()])[0].decode()))
    except Exception:
        return default


def _load_field_points(email):
    try:
        rows = get_user_sites(email)
    except Exception:
        return [], []

    xs = []
    ys = []
    for i, row in enumerate(rows, start=1):
        try:
            plume = float(row[4])
        except Exception:
            continue
        xs.append(i)
        ys.append(plume)
    return xs, ys


def maier_single_app():
    title = pn.pane.Markdown("## Maier & Grathwohl - Single Simulation")

    w_M = pn.widgets.FloatInput(name="Aquifer thickness M", value=_query_float("M", 5.0), step=0.1)
    w_tv = pn.widgets.FloatInput(name="Vertical transverse dispersivity tv", value=_query_float("tv", 0.01), step=0.001)
    w_g = pn.widgets.FloatInput(name="Stoichiometry coefficient g", value=_query_float("g", 3.5), step=0.1)
    w_Ca = pn.widgets.FloatInput(name="Contaminant concentration Ca", value=_query_float("Ca", 8.0), step=0.5)
    w_Cd = pn.widgets.FloatInput(name="Reactant concentration Cd", value=_query_float("Cd", 5.0), step=0.5)

    run_btn = pn.widgets.Button(name="Generate Graph", button_type="primary")
    out_md = pn.pane.Markdown("")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=520)

    email = _query_str("email", "demo@example.com")
    selected_site_id = _query_int("site_id", 0)

    def _run(_):
        try:
            lmax_current = maier_lmax(w_M.value, w_tv.value, w_g.value, w_Ca.value, w_Cd.value)
            out_md.object = f"**Plume length (Lmax):** `{lmax_current:.2f}`"

            field_x, field_y = _load_field_points(email)
            user_x = selected_site_id if selected_site_id > 0 else (max(field_x) + 1 if field_x else 1)

            p = figure(
                title="Maier and Grathwohl (2005)",
                x_axis_label="Site Number",
                y_axis_label="Plume Length (m)",
                height=520,
                sizing_mode="stretch_width",
            )
            if field_x and field_y:
                p.scatter(field_x, field_y, size=12, marker="circle", color="#ffa600", legend_label="Original Database Plume Length(LMax)")
            p.scatter([user_x], [lmax_current], size=14, marker="circle", color="#003f5c", legend_label="User Plume Length(LMax)")
            p.legend.location = "top_right"
            plot_pane.object = p

        except Exception as exc:
            out_md.object = f"Error: `{exc}`"

    run_btn.on_click(_run)

    controls = pn.Column(
        title,
        pn.pane.Markdown("### Inputs"),
        w_M,
        w_tv,
        w_g,
        w_Ca,
        w_Cd,
        run_btn,
        out_md,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 300px", "min-width": "260px"},
    )
    plot_col = pn.Column(
        plot_pane,
        sizing_mode="stretch_both",
        styles={"flex": "2 1 420px", "min-width": "320px"},
    )

    _run(None)
    return pn.FlexBox(controls, plot_col, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
