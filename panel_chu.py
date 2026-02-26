import pandas as pd
import panel as pn
from bokeh.plotting import figure

from data_queries import get_user_sites
from analytical_models import chu_lmax, compute_chu_multiple

pn.extension("tabulator", sizing_mode="stretch_width")


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


def chu_single_app():
    w = pn.widgets.FloatInput(name="Source width W [m]", value=_query_float("W", 2.0), step=0.1)
    alpha_th = pn.widgets.FloatInput(name="Horizontal transverse dispersivity alpha_Th [m]", value=_query_float("alpha_Th", 0.01), step=0.001)
    gamma = pn.widgets.FloatInput(name="Stoichiometric ratio gamma [-]", value=_query_float("gamma", 1.5), step=0.1)
    c_ea0 = pn.widgets.FloatInput(name="Acceptor concentration C_EA0 [mg/L]", value=_query_float("C_EA0", 8.0), step=0.1)
    c_ed0 = pn.widgets.FloatInput(name="Donor concentration C_ED0 [mg/L]", value=_query_float("C_ED0", 5.0), step=0.1)
    epsilon = pn.widgets.FloatInput(name="Biological factor epsilon [mg/L]", value=_query_float("epsilon", 0.0), step=0.01)

    result_md = pn.pane.Markdown()
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=520)
    email = _query_str("email", "demo@example.com")
    selected_site_id = _query_int("site_id", 0)

    def update(_=None):
        lmax = chu_lmax(w.value, alpha_th.value, gamma.value, c_ea0.value, c_ed0.value, epsilon.value)
        result_md.object = f"### Result\n\n- **Lmax ~= {lmax:.2f} m**"
        field_x, field_y = _load_field_points(email)
        user_x = selected_site_id if selected_site_id > 0 else (max(field_x) + 1 if field_x else 1)
        p = figure(title="Chu et al.", x_axis_label="Site Number", y_axis_label="Plume Length (m)", height=520, sizing_mode="stretch_width")
        if field_x and field_y:
            p.scatter(field_x, field_y, size=12, marker="circle", color="#ffa600", legend_label="Original Database Plume Length(LMax)")
        p.scatter([user_x], [lmax], size=14, marker="circle", color="#003f5c", legend_label="User Plume Length(LMax)")
        p.legend.location = "top_right"
        plot_pane.object = p

    for widget in (w, alpha_th, gamma, c_ea0, c_ed0, epsilon):
        widget.param.watch(update, "value")

    update()

    left = pn.Column(
        "# Chu et al. - Single Simulation",
        w,
        alpha_th,
        gamma,
        c_ea0,
        c_ed0,
        epsilon,
        result_md,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 300px", "min-width": "260px"},
    )
    right = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 420px", "min-width": "320px"})
    return pn.FlexBox(left, right, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})


def chu_multiple_app():
    default_df = pd.DataFrame([
        {
            "W": _query_float("W", 2.0),
            "alpha_Th": _query_float("alpha_Th", 0.01),
            "gamma": _query_float("gamma", 1.5),
            "C_EA0": _query_float("C_EA0", 8.0),
            "C_ED0": _query_float("C_ED0", 5.0),
            "epsilon": _query_float("epsilon", 0.0),
        }
    ])

    table = pn.widgets.Tabulator(default_df, height=260, sizing_mode="stretch_width", name="Chu scenarios")
    result_md = pn.pane.Markdown()
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=520)
    email = _query_str("email", "demo@example.com")

    def run(_=None):
        df = table.value
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)

        entries = []
        for _, row in df.iterrows():
            entries.append([
                float(row.get("W", 0.0)),
                float(row.get("alpha_Th", 0.0)),
                float(row.get("gamma", 0.0)),
                float(row.get("C_EA0", 0.0)),
                float(row.get("C_ED0", 0.0)),
                float(row.get("epsilon", 0.0)),
            ])

        if not entries:
            result_md.object = "### Results\n\nNo rows in table."
            plot_pane.object = None
            return

        l_vals = compute_chu_multiple(entries)
        result_md.object = "\n".join(["### Results"] + [f"- Row {i}: **Lmax ~= {l:.2f} m**" for i, l in enumerate(l_vals, start=1)])

        user_x = list(range(1, len(l_vals) + 1))
        field_x, field_y = _load_field_points(email)
        p = figure(title="Chu et al.", x_axis_label="Site Number", y_axis_label="Plume Length (m)", height=520, sizing_mode="stretch_width")
        p.scatter(user_x, l_vals, size=12, marker="circle", color="#003f5c", legend_label="User Plume Length(LMax)")
        if field_x and field_y:
            p.scatter(field_x, field_y, size=12, marker="circle", color="#ffa600", legend_label="Original Database Plume Length(LMax)")
        p.legend.location = "top_right"
        plot_pane.object = p

    table.param.watch(run, "value")
    run()

    left = pn.Column(
        "# Chu et al. - Multiple Simulation",
        "Edit the table and the plot will update automatically.",
        table,
        result_md,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 300px", "min-width": "260px"},
    )
    right = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 420px", "min-width": "320px"})
    return pn.FlexBox(left, right, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
