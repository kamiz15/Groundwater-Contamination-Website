import pandas as pd
import panel as pn
from bokeh.plotting import figure

from data_queries import get_user_sites
from analytical_models import compute_liedl_multiple

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


def liedl_multiple_app():
    init_df = pd.DataFrame([
        {
            "M": _query_float("M", 3.5),
            "alpha_Tv": _query_float("alpha_Tv", 0.001),
            "gamma": _query_float("gamma", 3.5),
            "C_EA0": _query_float("C_EA0", 8.0),
            "C_ED0": _query_float("C_ED0", 5.0),
        }
    ])

    table = pn.widgets.Tabulator(init_df, height=260, sizing_mode="stretch_width", name="Liedl scenarios")
    result_md = pn.pane.Markdown()
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=520)
    email = _query_str("email", "demo@example.com")

    def recompute(_=None):
        df = table.value
        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)

        entries = []
        for _, row in df.iterrows():
            entries.append([
                float(row.get("M", 0.0)),
                float(row.get("alpha_Tv", 0.0)),
                float(row.get("gamma", 0.0)),
                float(row.get("C_EA0", 0.0)),
                float(row.get("C_ED0", 0.0)),
            ])

        if not entries:
            result_md.object = "### Results\n\nNo rows in table."
            plot_pane.object = None
            return

        l_vals = compute_liedl_multiple(entries)
        result_md.object = "\n".join(["### Results"] + [f"- Row {i}: **Lmax ~= {l:.2f} m**" for i, l in enumerate(l_vals, start=1)])

        user_x = list(range(1, len(l_vals) + 1))
        field_x, field_y = _load_field_points(email)
        p = figure(title="Liedl et al. (2005)", x_axis_label="Site Number", y_axis_label="Plume Length (m)", height=520, sizing_mode="stretch_width")
        p.scatter(user_x, l_vals, size=12, marker="circle", color="#003f5c", legend_label="User Plume Length(LMax)")
        if field_x and field_y:
            p.scatter(field_x, field_y, size=12, marker="circle", color="#ffa600", legend_label="Original Database Plume Length(LMax)")
        p.legend.location = "top_right"
        plot_pane.object = p

    table.param.watch(recompute, "value")
    recompute()

    left = pn.Column(
        "# Liedl et al. (2005) - Multiple Simulation",
        "Edit the parameters in the table below. Each row is a scenario.",
        table,
        result_md,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 300px", "min-width": "260px"},
    )
    right = pn.Column(plot_pane, sizing_mode="stretch_both", styles={"flex": "2 1 420px", "min-width": "320px"})
    return pn.FlexBox(left, right, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
