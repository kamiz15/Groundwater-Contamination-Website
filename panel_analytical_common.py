from __future__ import annotations

import json
from math import ceil, log10

import panel as pn
from bokeh.models import HoverTool, Range1d
from bokeh.plotting import figure

from data_queries import get_user_sites
from panel_theme import COMPONENT_CSS, frame_height_bridge_html
from security import user_safe_error


PARAM_ALIASES = {
    "M": ("M", "H", "aquifer_thickness"),
    "H": ("H", "M", "aquifer_thickness"),
    "W": ("W", "Sw", "S_w", "sourceWidthW", "plume_width"),
    "Sw": ("Sw", "W", "S_w", "sourceWidthW", "plume_width"),
    "S_w": ("S_w", "Sw", "W", "sourceWidthW", "plume_width"),
    "C_EA0": ("C_EA0", "C_A", "Ca", "electron_acceptor_o2"),
    "C_A": ("C_A", "Ca", "C_EA0", "electron_acceptor_o2"),
    "Ca": ("Ca", "C_A", "C_EA0", "electron_acceptor_o2"),
    "C_ED0": ("C_ED0", "C_D", "Cd", "c0", "electron_donor"),
    "C_D": ("C_D", "Cd", "C_ED0", "c0", "electron_donor"),
    "Cd": ("Cd", "C_D", "C_ED0", "c0", "electron_donor"),
    "c0": ("c0", "C_D", "Cd", "C_ED0", "electron_donor"),
    "alpha_Tv": ("alpha_Tv", "av", "tv"),
    "av": ("av", "alpha_Tv", "tv"),
    "tv": ("tv", "alpha_Tv", "av"),
    "alpha_Th": ("alpha_Th", "alpha_th", "at", "ay"),
    "alpha_th": ("alpha_th", "alpha_Th", "at", "ay"),
    "at": ("at", "alpha_Th", "alpha_th", "ay"),
    "hk": ("hk", "K", "hydraulic_conductivity"),
    "K": ("K", "hk", "hydraulic_conductivity"),
    "K_h": ("K_h", "Kh", "hk", "K", "hydraulic_conductivity"),
    "vk": ("vk", "K_v", "Kv", "vertical_hydraulic_conductivity"),
    "K_v": ("K_v", "vk", "Kv", "vertical_hydraulic_conductivity"),
    "C0": ("C0", "c0_threshold", "plume_threshold"),
    "perlen": ("perlen", "simulation_time", "simulation_days"),
    "gamma": ("gamma", "g"),
    "g": ("g", "gamma"),
    "S_Ta": ("S_Ta", "R_Ta"),
    "S_Tb": ("S_Tb", "R_Tb"),
    "R_Ta": ("R_Ta", "S_Ta"),
    "R_Tb": ("R_Tb", "S_Tb"),
}


def _request_arg(name: str):
    req = pn.state.curdoc.session_context.request
    names = PARAM_ALIASES.get(name, (name,))
    for candidate in names:
        if candidate in req.arguments:
            return req.arguments[candidate][0].decode()
    return None


def query_float(name: str, default: float) -> float:
    try:
        raw = _request_arg(name)
        if raw is None or raw == "":
            return default
        return float(raw)
    except Exception:
        return default


def query_int(name: str, default: int = 0) -> int:
    try:
        raw = _request_arg(name)
        if raw is None or raw == "":
            return default
        return int(float(raw))
    except Exception:
        return default


def query_str(name: str, default: str = "") -> str:
    try:
        raw = _request_arg(name)
        return raw if raw is not None else default
    except Exception:
        return default


def load_field_points(email: str):
    try:
        rows = get_user_sites(email)
    except Exception as exc:
        user_safe_error(exc, "Database error while loading analytical comparison points")
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


def site_position(selected_site_id: int, email: str):
    """Where a site sits in the plotted series, which is what the x axis counts.

    load_field_points numbers sites by their position in the list (1..N), but a
    site's own id is a database primary key - in the thousands for a real table,
    a CSV row position for the reference set. The pages pass that id straight
    through as the model point's x, which threw the marker thousands of ticks
    past the end of the axis. Translate it here, where every page routes.

    Returns None when the site cannot be located, leaving the caller's x alone.
    """
    if not selected_site_id or selected_site_id <= 0:
        return None
    try:
        for i, row in enumerate(get_user_sites(email), start=1):
            if row[0] == selected_site_id:
                return i
    except Exception as exc:
        user_safe_error(exc, "Database error while locating the selected site")
    return None


def info_card(message: str) -> str:
    return f"""
    <div style="background:#eef1f5;border:1px solid #e3e8ef;border-radius:10px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,0.07);">
      <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#5b6b7f;margin-bottom:6px;">Result</div>
      <div style="font-size:1rem;color:#16212e;">{message}</div>
    </div>
    """


def metric_card(label: str, value_text: str, unit: str = "m", title: str = "Simulation Result",
                delta: str = "") -> str:
    unit_html = f'<span style="font-size:1rem;font-weight:700;color:#1f72cd;">{unit}</span>' if unit else ''
    # The chip is deliberately neutral-toned: a longer or shorter plume is not
    # "good" or "bad", so red/green would assert a judgement the model does not make.
    delta_html = (
        f'<span style="font-size:0.8rem;font-weight:600;color:#5b6b7f;background:#e3e8ef;'
        f'border-radius:999px;padding:3px 10px;white-space:nowrap;">{delta}</span>'
    ) if delta else ''
    # The card is rebuilt on every run, so the browser replays this animation
    # each time a new number lands - which is what ties a dragged slider at the
    # bottom of the panel to the result at the top. No JS: a freshly inserted
    # element runs its animation on its own.
    return f"""
    <style>
      @keyframes castResultIn {{
        0%   {{ background: #d6e6f8; }}
        100% {{ background: transparent; }}
      }}
      .cast-result-value {{
        border-radius: 6px;
        padding: 0 4px;
        margin: 0 -4px;
        animation: castResultIn .7s ease-out;
      }}
      @media (prefers-reduced-motion: reduce) {{
        .cast-result-value {{ animation: none; }}
      }}
    </style>
    <div style="background:#eef1f5;border:1px solid #e3e8ef;border-left:3px solid #1f72cd;border-radius:10px;padding:18px 20px;box-shadow:0 1px 3px rgba(16,24,40,0.07);">
      <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#5b6b7f;margin-bottom:8px;">{title}</div>
      <div style="display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;">
        <span style="font-size:1rem;font-weight:600;color:#5b6b7f;">{label}</span>
        <span class="cast-result-value" style="font-size:1.9rem;font-weight:800;color:#0b2c4f;line-height:1;">{value_text}</span>
        {unit_html}
        {delta_html}
      </div>
    </div>
    """


def baseline_delta(current: float, baseline: float | None) -> str:
    """Chip text placing the current result against the first run of the page.

    Empty while the sliders still sit on the values the model was run with, so
    the card only grows the chip once the reader has actually moved something.
    """
    if not baseline or current is None:
        return ""
    change = (current - baseline) / baseline * 100
    if abs(change) < 0.05:
        return ""
    arrow = "↑" if change > 0 else "↓"
    return f"{arrow} {abs(change):.0f}% vs. baseline {baseline:.2f}"


# Slider bounds for parameters whose widget carries no start/end of its own.
# Widget bounds always win (BIOSCREEN sets its own, and they are model-specific);
# this table is the fallback for the plain FloatInputs.
SLIDER_RANGES = {
    "M": (0.1, 20.0),          # source / aquifer thickness
    "H": (0.1, 50.0),
    "W": (0.1, 30.0),          # source width
    "Q": (0.1, 50.0),          # source flux
    "alpha_Tv": (0.0001, 0.1),
    "tv": (0.0001, 0.1),       # empirical alias of alpha_Tv
    "alpha_Th": (0.001, 1.0),
    "alpha_T": (0.001, 1.0),
    "gamma": (0.1, 10.0),
    "g": (0.1, 10.0),          # empirical alias of gamma
    "C_EA0": (0.1, 50.0),
    "C_ED0": (0.1, 50.0),
    "Ca": (0.1, 50.0),
    "Cd": (0.1, 50.0),
    "Cthres": (0.001, 5.0),
    "epsilon": (0.0, 5.0),
    "R": (0.0, 5.0),           # recharge rate (Birla)
}


def _slider_format(step: float) -> str:
    """Decimal places a value of this step size needs to be readable."""
    if step <= 0:
        return "0.00"
    places = min(6, max(2, ceil(-log10(step)) + 1))
    return "0." + "0" * places


def _track_position(value: float, lo: float, hi: float) -> float:
    """Where `value` sits along the track, as a percentage."""
    if hi <= lo:
        return 0.0
    return min(100.0, max(0.0, (value - lo) / (hi - lo) * 100.0))


def _slider_bounds(name: str, widget) -> tuple[float, float]:
    lo, hi = getattr(widget, "start", None), getattr(widget, "end", None)
    if lo is None or hi is None:
        lo, hi = SLIDER_RANGES.get(name, (None, None))
    value = float(widget.value or 0.0)
    if lo is None or hi is None or float(lo) >= float(hi):
        lo, hi = 0.0, max(1.0, abs(value) * 5)
    # A site loaded from the database can sit outside the table; widen rather
    # than clamp, so the slider always opens on the value that was actually run.
    return min(float(lo), value), max(float(hi), value)


_SLIDER_STRIP_HEAD = """
<div>
  <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;
              text-transform:uppercase;color:#5b6b7f;border-bottom:2px solid #1f72cd;
              display:inline-block;padding-bottom:5px;">Explore</div>
  <div style="font-size:0.85rem;color:#5b6b7f;margin-top:7px;">Drag a slider to recompute the model &mdash;
    the notch on each track marks the value it was last run with.</div>
</div>
"""

# Reset sits on the card, which is the same grey a default Panel button paints
# itself: it was a grey block on a grey card. White with a hairline reads as a
# control. COMPONENT_CSS first because a per-widget sheet REPLACES the theme's.
_RESET_BTN_CSS = """
.bk-btn, button.bk-btn-default {
  background: #ffffff !important;
  border: 1px solid #d7dfea !important;
  color: #2c3e52 !important;
  font-weight: 600;
}
.bk-btn:hover, button.bk-btn-default:hover {
  border-color: #5598e3 !important;
  color: #114b88 !important;
}
"""


# Posted to the embedding page on every slider change. The page keeps its input
# form and its export link in step with it - see the CAST input bridge in
# static/script.js, which is the other half of this contract.
_INPUT_BRIDGE_JS = (
    # Rounded to the precision the slider itself displays: the raw float lands
    # in a form field and a URL, where 8.258999999999999 is just noise.
    "window.parent.postMessage("
    "{type: 'cast-input', name: %s, value: Number(cb_obj.value.toFixed(%d))}, '*');"
)


def output_only_layout(*objects):
    """The panel a single page serves into its workbench frame.

    Carries the height bridge, so the page sizes the frame to this document.
    Without it the frame sits at whatever floor styles.css guesses - dead space
    under the panel when the guess is high, a cut-off panel when it is low - and
    the guess has to be re-tuned by hand every time the strip changes height.
    The multiple pages have posted their height all along; this is the same
    contract, and the other half of it is already in static/script.js.
    """
    return pn.Column(
        *objects,
        pn.pane.HTML(frame_height_bridge_html(), height=0, margin=0,
                     sizing_mode="fixed"),
        sizing_mode="stretch_width", styles={"gap": "14px"},
    )


def explore_sliders(pairs, rerun):
    """Slider strip that sits under the plot, one slider per main parameter.

    pairs: [(query-parameter name, the widget the model already reads)].
    Each slider drives its widget, so `rerun` needs no arguments and the PDF
    state the panel builds on every run stays in step with what is on screen.
    """
    sliders, defaults = [], []
    for name, widget in pairs:
        lo, hi = _slider_bounds(name, widget)
        value = float(widget.value)
        step = (hi - lo) / 200
        fmt = _slider_format(step)
        decimals = max(0, len(fmt) - 2)          # "0.000" -> 3
        slider = pn.widgets.FloatSlider(
            name=widget.name, start=lo, end=hi,
            value=value, step=step,
            sizing_mode="stretch_width",
            # Without this a value far below its step reads as a flat "0" -
            # alpha_Tv is 0.001 on a 0.0005 step and showed nothing at all.
            format=fmt,
            # Where the value the model was RUN with sits on the track, so the
            # notch says how far the reader has dragged from the baseline the
            # result chip is comparing against.
            styles={"--cast-baseline": f"{_track_position(value, lo, hi):.4f}%",
                    "--cast-baseline-on": "1"},
        )
        slider.link(widget, value="value")
        # value_throttled fires on release, not per pixel: one recompute per drag.
        slider.param.watch(lambda _event: rerun(), "value_throttled")
        # Tell the page what this slider is now worth. The input form and the
        # PDF export link both live out there and are built from the form, so
        # without this a drag left both stale: Run Model discarded the
        # exploration, and the exported report was computed from the values the
        # page was rendered with rather than the ones on screen.
        #
        # ponytail: bound to `value`, not `value_throttled`, so a programmatic
        # change - Reset sliders - reaches the page too. That is one postMessage
        # per pixel of drag, and each one only writes a form field.
        slider.jscallback(value=_INPUT_BRIDGE_JS % (json.dumps(name), decimals))
        sliders.append(slider)
        defaults.append((slider, float(widget.value)))

    reset_btn = pn.widgets.Button(name="Reset sliders", width=130, sizing_mode="fixed",
                                  stylesheets=[COMPONENT_CSS, _RESET_BTN_CSS])

    def _reset(_=None):
        for slider, value in defaults:
            slider.value = value
        rerun()

    reset_btn.on_click(_reset)

    # Each slider gets a card of its own: on the flat grey strip the three of
    # them ran together as loose label-and-track pairs. White cells make them
    # read as three controls.
    #
    # Wrapping flex cells rather than a fixed grid: the strip is inside an iframe
    # whose width the page decides, so it has to fold to one column on its own.
    # The 320px basis holds it to two per row at the usual stage width - three
    # abreast is not enough room for names this long. A lone cell on the last
    # row grows to fill it, so the row never reads as an orphan.
    cells = [
        pn.Column(s, styles={
            "flex": "1 1 320px", "min-width": "300px",
            "background": "#ffffff",
            "border": "1px solid #e3e8ef",
            "border-radius": "8px",
            "padding": "10px 16px 2px",
        })
        for s in sliders
    ]
    return pn.Column(
        pn.Row(
            pn.pane.HTML(_SLIDER_STRIP_HEAD, sizing_mode="stretch_width", margin=0),
            reset_btn,
            sizing_mode="stretch_width",
            styles={"align-items": "flex-start", "gap": "12px"},
        ),
        pn.FlexBox(*cells, flex_wrap="wrap", sizing_mode="stretch_width",
                   styles={"gap": "12px"}),
        sizing_mode="stretch_width",
        styles={
            "background": "#eef1f5",
            "border": "1px solid #e3e8ef",
            # The blue edge the result card wears: these are the controls that
            # move that number, so the two read as one pair.
            "border-left": "3px solid #1f72cd",
            "border-radius": "10px",
            "padding": "16px 18px",
            "gap": "12px",
            "box-shadow": "0 1px 3px rgba(16,24,40,0.07)",
        },
    )


def summary_card(items: list[tuple[str, str]], title: str = "Simulation Summary") -> str:
    blocks = "".join(
        f'<div><span style="font-size:0.85rem;color:#5b6b7f;">{label}</span><div style="font-size:1.7rem;font-weight:800;color:#0b2c4f;">{value}</div></div>'
        for label, value in items
    )
    return f"""
    <div style="background:#eef1f5;border:1px solid #e3e8ef;border-left:3px solid #1f72cd;border-radius:10px;padding:18px 20px;box-shadow:0 1px 3px rgba(16,24,40,0.07);">
      <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#5b6b7f;margin-bottom:8px;">{title}</div>
      <div style="display:flex;gap:18px;flex-wrap:wrap;">{blocks}</div>
    </div>
    """


def error_card(message) -> str:
    message = user_safe_error(message)
    return f"""
    <div style="background:#fef3f2;border:1px solid #f7c5c0;border-radius:10px;padding:16px 18px;box-shadow:0 1px 3px rgba(16,24,40,0.05);">
      <div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;color:#b42318;margin-bottom:6px;">Error</div>
      <div style="font-size:0.98rem;color:#7a271a;">{message}</div>
    </div>
    """


# The three series a comparison chart can carry. Exported because the pages that
# draw their own key next to the plot have to name the same colours - a legend
# that disagrees with the dots is worse than none.
MODEL_COLOR = "#1b5e20"        # dark green: modelled, from the scenario table
MEASURED_COLOR = "#f59e0b"     # amber: measured, typed into the scenario table
SITE_COLOR = "#155da9"         # brand blue: measured, from the site database


def comparison_plot_data(title: str, manual_label: str, manual_x, manual_y,
                         selected_site_id: int, email: str, manual_axis_label: str,
                         show_database: bool = True, field_points=None,
                         field_label: str = "Database plume length",
                         site_points=None,
                         site_series_label: str = "Measured plume length (site)"):
    # The database series is the point of this chart on the single pages, so it
    # loads whether or not a site has been picked: landing on the page shows the
    # database plume lengths next to the model result from the default inputs.
    # get_user_sites falls back to the reference database, so this works without
    # an account.
    #
    # The multiple pages pass show_database=False. They already plot one point
    # per site the user picked, and drawing every other site in the database on
    # top of that is the whole dataset, not a comparison.
    #
    # field_points overrides both: the scenario pages already know which measured
    # value belongs on which x, so they hand the series over ready-made and keep
    # their own axis labelling instead of the 1..N site numbering.
    # A second measured series, kept apart from field_points so the two can be
    # told apart on the chart: the scenario pages plot what was typed into the
    # table AND what the picked sites measured, and merging them into one colour
    # made a legend impossible to write honestly.
    site_x, site_y = ((list(site_points[0]), list(site_points[1]))
                      if site_points is not None else ([], []))
    manual_x = list(manual_x)
    if field_points is not None:
        field_x, field_y = list(field_points[0]), list(field_points[1])
        axis_label = manual_axis_label
    else:
        field_x, field_y = load_field_points(email) if show_database else ([], [])
        axis_label = "Site Number" if field_x else manual_axis_label
        position = site_position(selected_site_id, email)
        if position is not None:
            # Loaded site: put the model result on that site's own tick so the two
            # markers line up for a direct comparison.
            manual_x = [position] * len(manual_x)
        elif field_x and selected_site_id <= 0:
            # A manual run is not one of the sites. Park it just past the last one
            # rather than letting it sit on top of site 1 and read as that site.
            last = max(field_x)
            manual_x = [last + i for i in range(1, len(manual_x) + 1)]
    return {
        "type": "comparison_scatter",
        "title": title,
        "x_label": axis_label,
        "y_label": "Plume Length (m)",
        "field_label": field_label,
        "field_x": field_x,
        "field_y": field_y,
        "site_label": site_series_label,
        "site_x": site_x,
        "site_y": site_y,
        "manual_label": manual_label,
        "manual_x": manual_x,
        "manual_y": list(manual_y),
        "caption": ("Database plume lengths compared with the model result."
                    if field_x else "Computed model plume lengths."),
    }


def _held_y_range(plot_data, frame: dict) -> tuple[float, float]:
    """Y limits that stay put while a slider moves the model point.

    The figure is rebuilt from scratch on every run, so Bokeh's autoranging
    refits the axis around the new value and the point appears pinned in place
    while only the tick labels change. Sizing the frame once on the first run
    and holding it lets the point actually travel. It widens only when a value
    would otherwise leave the plot, which beats drawing a point nobody can see.
    """
    values = [float(v) for v in (list(plot_data["field_y"])
                                 + list(plot_data.get("site_y") or [])
                                 + list(plot_data["manual_y"]))
              if v is not None]
    top = max(values) if values else 1.0
    low, high = frame.get("y_range", (None, None))
    if low is None:
        low, high = 0.0, top * 1.3 or 1.0
    elif top > high:
        high = top * 1.15
    frame["y_range"] = (low, high)
    return low, high


def comparison_plot(title: str, manual_label: str, manual_x, manual_y,
                    selected_site_id: int, email: str, manual_axis_label: str,
                    return_data: bool = False, frame: dict | None = None,
                    show_database: bool = True, field_points=None,
                    field_label: str = "Database plume length",
                    site_points=None,
                    site_series_label: str = "Measured plume length (site)",
                    manual_color: str = MODEL_COLOR):
    plot_data = comparison_plot_data(
        title, manual_label, manual_x, manual_y,
        selected_site_id, email, manual_axis_label,
        show_database=show_database, field_points=field_points,
        field_label=field_label, site_points=site_points,
        site_series_label=site_series_label,
    )
    p = figure(
        title=plot_data["title"],
        x_axis_label=plot_data["x_label"],
        y_axis_label=plot_data["y_label"],
        height=420,
        sizing_mode="stretch_width",
    )
    if frame is not None:
        low, high = _held_y_range(plot_data, frame)
        p.y_range = Range1d(low, high)
    if plot_data["field_x"] and plot_data["field_y"]:
        field = p.scatter(plot_data["field_x"], plot_data["field_y"], size=12, marker="circle", color=MEASURED_COLOR)
        # Only the database points get the tooltip: their x IS the site number
        # (load_field_points numbers them 1..N). The model point is parked past
        # the last site on a manual run, so a site number there would be a lie.
        p.add_tools(HoverTool(
            renderers=[field],
            tooltips=[("Site", "@x{0}"), ("Plume length", "@y{0.00} m")],
        ))
    # Dark green against the amber database points: opposite hue and a wide
    # lightness gap, so the two series stay apart on a projector and under
    # red-green colour blindness (which flattens the hue but not the lightness).
    # The old pairing was two blues differing only in lightness.
    # No legend. It restated the chart title and the y-axis, and wherever it sat
    # it cost space or covered a point - top-right hid the model result parked
    # past the last site, top-left hid the first scenario row, above the frame it
    # took a band of its own. The two series are told apart by the hover tooltip
    # and by colour: amber is measured, dark green is modelled. plot_data still
    # carries field_label/manual_label for the PDF report, which keeps its legend.
    if plot_data.get("site_x") and plot_data.get("site_y"):
        site = p.scatter(plot_data["site_x"], plot_data["site_y"], size=12,
                         marker="circle", color=SITE_COLOR)
        p.add_tools(HoverTool(
            renderers=[site],
            tooltips=[("Site", "@x{0}"), ("Measured plume length", "@y{0.00} m")],
        ))
    # manual_color, not MODEL_COLOR outright: the single pages set the modelled
    # result against the amber database points and need their own hue, while a
    # page whose key is by SOURCE rather than by kind wants everything the
    # scenario table produced - modelled and measured alike - in one colour.
    p.scatter(plot_data["manual_x"], plot_data["manual_y"], size=14 if len(plot_data["manual_y"]) == 1 else 12, marker="circle", color=manual_color)
    return (p, plot_data) if return_data else p
