import panel as pn
from bokeh.plotting import figure

from data_queries import get_user_sites
from analytical_models import liedl_lmax

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
    xs, ys = [], []
    for i, row in enumerate(rows, start=1):
        try:
            plume = float(row[4])
        except Exception:
            continue
        xs.append(i)
        ys.append(plume)
    return xs, ys


def liedl_single_app():
    m = pn.widgets.FloatInput(name="M (mass per unit width)", value=_query_float("M", 3.5), step=0.1)
    alpha_tv = pn.widgets.FloatInput(name="alpha_Tv (transverse dispersivity)", value=_query_float("alpha_Tv", 0.001), step=0.0001)
    gamma = pn.widgets.FloatInput(name="gamma (stoichiometric factor)", value=_query_float("gamma", 3.5), step=0.1)
    c_ea0 = pn.widgets.FloatInput(name="C_EA0 (acceptor) [mg/L]", value=_query_float("C_EA0", 8.0), step=0.1)
    c_ed0 = pn.widgets.FloatInput(name="C_ED0 (donor) [mg/L]", value=_query_float("C_ED0", 5.0), step=0.1)

    result_md = pn.pane.Markdown()
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=520)
    email = _query_str("email", "demo@example.com")
    selected_site_id = _query_int("site_id", 0)

    def update(_=None):
        lmax = liedl_lmax(m.value, alpha_tv.value, gamma.value, c_ea0.value, c_ed0.value)
        result_md.object = f"### Result\n\n- **Lmax ~= {lmax:.2f} m**"

        field_x, field_y = _load_field_points(email)
        user_x = selected_site_id if selected_site_id > 0 else (max(field_x) + 1 if field_x else 1)
        p = figure(title="Liedl et al. (2005)", x_axis_label="Site Number", y_axis_label="Plume Length (m)", height=520, sizing_mode="stretch_width")
        if field_x and field_y:
            p.scatter(field_x, field_y, size=12, marker="circle", color="#ffa600", legend_label="Original Database Plume Length(LMax)")
        p.scatter([user_x], [lmax], size=14, marker="circle", color="#003f5c", legend_label="User Plume Length(LMax)")
        p.legend.location = "top_right"
        plot_pane.object = p

    for w in (m, alpha_tv, gamma, c_ea0, c_ed0):
        w.param.watch(update, "value")

    update()

    left = pn.Column(
        "# Liedl et al. (2005) - Single Simulation",
        m,
        alpha_tv,
        gamma,
        c_ea0,
        c_ed0,
        result_md,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 300px", "min-width": "260px"},
    )
    right = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 420px", "min-width": "320px"})
    return pn.FlexBox(left, right, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
