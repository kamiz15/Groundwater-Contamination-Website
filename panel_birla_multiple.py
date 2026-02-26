import pandas as pd
import panel as pn
from bokeh.plotting import figure

from data_queries import get_user_sites
from empirical_models import birla_lmax

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


def birla_multiple_app():
    title = pn.pane.Markdown("## Birla et al. - Multiple Simulation (sweep R)")

    default_r = _query_float("R", 1.0)
    w_Rs = pn.widgets.TextInput(
        name="R values (comma-separated)",
        value=",".join(f"{v:.3f}" for v in [max(0.05, default_r * 0.5), default_r, default_r * 1.5]),
    )
    w_M = pn.widgets.FloatInput(name="M", value=_query_float("M", 2.0), step=0.1)
    w_tv = pn.widgets.FloatInput(name="tv", value=_query_float("tv", 0.001), step=0.0005)
    w_g = pn.widgets.FloatInput(name="g", value=_query_float("g", 3.5), step=0.1)
    w_Ca = pn.widgets.FloatInput(name="Ca", value=_query_float("Ca", 8.0), step=0.5)
    w_Cd = pn.widgets.FloatInput(name="Cd", value=_query_float("Cd", 5.0), step=0.5)

    run_btn = pn.widgets.Button(name="Run sweep", button_type="primary")
    table = pn.widgets.Tabulator(pd.DataFrame(columns=["R", "Lmax"]), height=220, sizing_mode="stretch_width")
    initial_plot = figure(title="Birla et al. (2020)", x_axis_label="Site Number", y_axis_label="Plume Length (m)", height=520, sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(initial_plot, sizing_mode="stretch_width", min_height=520)
    status_md = pn.pane.Markdown("")
    email = _query_str("email", "demo@example.com")

    def _run(_):
        try:
            rs = []
            for part in w_Rs.value.split(","):
                part = part.strip()
                if part:
                    rs.append(float(part))

            if len(rs) == 1:
                center = rs[0]
                rs = [max(0.05, center * 0.5), center, center * 1.5]

            rows = []
            for r in rs:
                lmax = birla_lmax(w_M.value, w_tv.value, w_g.value, w_Ca.value, w_Cd.value, r)
                rows.append({"R": r, "Lmax": lmax})

            df = pd.DataFrame(rows).sort_values("R")
            if df.empty:
                raise ValueError("No valid sweep values found.")
            table.value = df

            user_x = list(range(1, len(df) + 1))
            user_y = df["Lmax"].tolist()
            field_x, field_y = _load_field_points(email)

            p = figure(title="Birla et al. (2020)", x_axis_label="Site Number", y_axis_label="Plume Length (m)", height=520, sizing_mode="stretch_width")
            p.scatter(user_x, user_y, size=12, marker="circle", color="#003f5c", legend_label="User Plume Length(LMax)")
            if field_x and field_y:
                p.scatter(field_x, field_y, size=12, marker="circle", color="#ffa600", legend_label="Original Database Plume Length(LMax)")
            p.legend.location = "top_right"
            plot_pane.object = p
            status_md.object = f"Computed {len(df)} scenario(s)."

        except Exception as exc:
            table.value = pd.DataFrame([{"error": str(exc)}])
            status_md.object = f"Error: `{exc}`"

    run_btn.on_click(_run)

    left = pn.Column(
        title,
        pn.pane.Markdown("### Sweep settings"),
        w_Rs,
        pn.pane.Markdown("### Fixed parameters"),
        w_M,
        w_tv,
        w_g,
        w_Ca,
        w_Cd,
        run_btn,
        status_md,
        table,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 300px", "min-width": "260px"},
    )
    right = pn.Column(
        plot_pane,
        sizing_mode="stretch_both",
        styles={"flex": "2 1 420px", "min-width": "320px"},
    )
    _run(None)
    return pn.FlexBox(left, right, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
