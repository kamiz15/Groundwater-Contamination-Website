import pandas as pd
import panel as pn
from bokeh.plotting import figure

from bioscreen_model import bio
from data_queries import get_user_sites

pn.extension("tabulator", sizing_mode="stretch_width")


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


def _field_points(email):
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


def _base_widgets():
    cthres = pn.widgets.FloatInput(name="Threshold concentration Cthres (mg/L)", value=_query_float("Cthres", 5e-5), step=1e-5, start=1e-8)
    time = pn.widgets.IntInput(name="Time (years)", value=_query_int("time", 20), start=1, end=1000)
    h = pn.widgets.FloatSlider(name="Source thickness H (m)", value=_query_float("H", 5), start=0.1, end=50, step=0.1)
    c0 = pn.widgets.FloatSlider(name="Source concentration c0 (mg/L)", value=_query_float("c0", 100), start=0.1, end=1000, step=1)
    w = pn.widgets.FloatSlider(name="Source width W (m)", value=_query_float("W", 10), start=0.1, end=1000, step=0.1)
    v = pn.widgets.FloatInput(name="Avg. linear groundwater velocity v (m/yr)", value=_query_float("v", 50), start=10, end=1000)
    ax = pn.widgets.FloatSlider(name="Longitudinal dispersivity ax (m)", value=_query_float("ax", 10), start=1, end=100, step=0.5)
    ay = pn.widgets.FloatInput(name="Horizontal transverse dispersivity ay (m)", value=_query_float("ay", 0.5), start=0.1, end=10)
    az = pn.widgets.FloatInput(name="Vertical transverse dispersivity az (m)", value=_query_float("az", 0.05), start=0.01, end=1)
    df = pn.widgets.FloatInput(name="Effective diffusion coefficient Df (m2/yr)", value=_query_float("Df", 0.0), start=0.0, end=0.1)
    r = pn.widgets.FloatInput(name="Retardation factor R (-)", value=_query_float("R", 1.0), start=0.01)
    gamma = pn.widgets.FloatInput(name="Source decay gamma (1/yr)", value=_query_float("gamma", 0.0), start=0.0, end=1.0)
    lam = pn.widgets.FloatSlider(name="Effective first-order decay lam (1/yr)", value=_query_float("lam", 0.1), start=0.0, end=1.0, step=0.01)
    ng_default = _query_int("ng", 60)
    if ng_default not in [4, 5, 6, 10, 15, 20, 60, 104, 256]:
        ng_default = 60
    ng = pn.widgets.Select(name="Number of Gauss points", value=ng_default, options=[4, 5, 6, 10, 15, 20, 60, 104, 256])
    return cthres, time, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng


def bioscreen_single_app():
    cthres, time, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng = _base_widgets()
    run_btn = pn.widgets.Button(name="Generate Graph", button_type="primary")
    result_md = pn.pane.Markdown("### lMax: -")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=460)
    email = _query_str("email", "demo@example.com")
    selected_site_id = _query_int("site_id", 0)

    def _compute(_=None):
        try:
            lmax = float(
                bio(
                    cthres.value,
                    time.value,
                    h.value,
                    c0.value,
                    w.value,
                    v.value,
                    ax.value,
                    ay.value,
                    az.value,
                    df.value,
                    r.value,
                    gamma.value,
                    lam.value,
                    int(ng.value),
                )
            )
            result_md.object = f"### lMax: **{lmax:.2f} m**"

            field_x, field_y = _field_points(email)
            user_x = selected_site_id if selected_site_id > 0 else (max(field_x) + 1 if field_x else 1)

            p = figure(
                title="BioScreen",
                x_axis_label="Site Number",
                y_axis_label="Plume Length (m)",
                height=460,
                sizing_mode="stretch_width",
            )
            p.scatter([user_x], [lmax], size=14, marker="circle", color="#003f5c", legend_label="User Plume Length(LMax)")
            if field_x and field_y:
                p.scatter(field_x, field_y, size=12, marker="circle", color="#ffa600", legend_label="Original Database Plume Length(LMax)")
            p.legend.location = "top_right"
            plot_pane.object = p
        except Exception as exc:
            result_md.object = f"### Error\n`{exc}`"

    run_btn.on_click(_compute)
    _compute()

    left = pn.Column(
        "## BIOSCREEN-AT (Single)",
        cthres,
        time,
        h,
        c0,
        w,
        v,
        ax,
        ay,
        az,
        df,
        r,
        gamma,
        lam,
        ng,
        run_btn,
        result_md,
        sizing_mode="stretch_width",
        styles={"flex": "1 1 300px", "min-width": "260px"},
    )
    right = pn.Column(
        plot_pane,
        sizing_mode="stretch_both",
        styles={"flex": "2 1 420px", "min-width": "320px"},
    )
    return pn.FlexBox(left, right, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})


def bioscreen_multiple_app():
    cthres, time, h, c0, w, v, ax, ay, az, df, r, gamma, lam, ng = _base_widgets()
    w_times = pn.widgets.TextInput(name="Times for sweep (comma-separated years)", value=f"{max(1, time.value // 2)},{time.value},{time.value * 2}")
    run_btn = pn.widgets.Button(name="Generate Graph", button_type="primary")
    status_md = pn.pane.Markdown("")
    table = pn.widgets.Tabulator(pd.DataFrame(columns=["time_years", "lmax_m"]), height=220, sizing_mode="stretch_width")
    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=460)
    email = _query_str("email", "demo@example.com")

    def _run(_=None):
        try:
            times = []
            for part in w_times.value.split(","):
                part = part.strip()
                if part:
                    times.append(float(part))
            times = sorted(set(times))
            if not times:
                raise ValueError("Provide at least one time value.")

            rows = []
            for t in times:
                lmax = float(
                    bio(
                        cthres.value,
                        t,
                        h.value,
                        c0.value,
                        w.value,
                        v.value,
                        ax.value,
                        ay.value,
                        az.value,
                        df.value,
                        r.value,
                        gamma.value,
                        lam.value,
                        int(ng.value),
                    )
                )
                rows.append({"time_years": t, "lmax_m": lmax})

            df_out = pd.DataFrame(rows).sort_values("time_years")
            table.value = df_out
            status_md.object = f"Computed {len(df_out)} scenario(s)."

            user_x = list(range(1, len(df_out) + 1))
            user_y = df_out["lmax_m"].tolist()
            field_x, field_y = _field_points(email)

            p = figure(
                title="BioScreen",
                x_axis_label="Site Number",
                y_axis_label="Plume Length (m)",
                height=460,
                sizing_mode="stretch_width",
            )
            p.scatter(user_x, user_y, size=14, marker="circle", color="#003f5c", legend_label="User Plume Length(LMax)")
            if field_x and field_y:
                p.scatter(field_x, field_y, size=12, marker="circle", color="#ffa600", legend_label="Original Database Plume Length(LMax)")
            p.legend.location = "top_right"
            plot_pane.object = p
        except Exception as exc:
            table.value = pd.DataFrame([{"error": str(exc)}])
            status_md.object = f"Error: `{exc}`"

    run_btn.on_click(_run)
    _run()

    left = pn.Column(
        "## BIOSCREEN-AT (Multiple)",
        w_times,
        cthres,
        h,
        c0,
        w,
        v,
        ax,
        ay,
        az,
        df,
        r,
        gamma,
        lam,
        ng,
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
    return pn.FlexBox(left, right, sizing_mode="stretch_both", flex_wrap="wrap", styles={"gap": "16px"})
