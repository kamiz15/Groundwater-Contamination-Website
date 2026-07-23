"""Bokeh figure builders for the workbench.

Each function takes plain data (arrays / DataFrames / helper results) and returns
a Bokeh ``figure`` (or a layout of figures). No Panel here, so a builder can be
called from a notebook or a test. Styling follows the conventions already used
in ``plot_functions.py`` (RdYlGn image palette, #163c66 accents, standard tools).

Axis scales (linear / ln / log10 / inverse) are applied by transforming the data
and relabelling the axis — see ``scales.py`` for why. All displayed numbers use
the two-decimal convention in ``formatting.py``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from bokeh.layouts import column as bk_column
from bokeh.models import (
    ColorBar,
    ColumnDataSource,
    FactorRange,
    HoverTool,
    LabelSet,
    LinearColorMapper,
    NumeralTickFormatter,
    Whisker,
)
from bokeh.palettes import (
    Category10,
    Cividis256,
    Greys256,
    Inferno256,
    Magma256,
    Plasma256,
    RdBu,
    RdYlGn11,
    Turbo256,
    Viridis256,
)
from bokeh.plotting import figure

from . import fits as fits_mod
from . import formatting as fmt_mod
from . import kde as kde_mod
from . import notation
from . import scales as scales_mod
from . import stats as stats_mod
from .formatting import fmt
from .grids import GridData, gradient_vectors

_TOOLS = "pan,wheel_zoom,box_zoom,reset,save"
_ACCENT = "#163c66"
_ACCENT2 = "#3d82b6"

# Colour maps offered for the contour / heat-map plots.
COLORMAPS = {
    "Viridis": Viridis256,
    "Cividis": Cividis256,
    "Inferno": Inferno256,
    "Magma": Magma256,
    "Plasma": Plasma256,
    "Turbo": Turbo256,
    "Greys": Greys256,
    "Red-Yellow-Green": list(reversed(RdYlGn11)),
}
DEFAULT_COLORMAP = "Viridis"


def colormap(name: str):
    """Look up a palette by display name."""
    if name not in COLORMAPS:
        raise ValueError(f"Unknown colour map '{name}'.")
    return COLORMAPS[name]


def _base_figure(title: str, x_label: str, y_label: str, height: int = 380, **kwargs):
    return figure(
        title=title, x_axis_label=x_label, y_axis_label=y_label,
        tools=_TOOLS, toolbar_location="above", active_drag="pan",
        active_scroll="wheel_zoom", sizing_mode="stretch_width", height=height,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Group 1 — univariate
# --------------------------------------------------------------------------- #

def histogram_figure(values: np.ndarray, column: str, bins: int = 30, scale: str = "linear"):
    # Binning happens after the transform, so a log scale gives log-spaced bins
    # in the original units rather than uneven bars on a stretched axis.
    data = scales_mod.transform(values, scale, name=column)
    tex = scales_mod.axis_label(column, scale)
    plain = scales_mod.plain_axis_label(column, scale)
    counts, edges = np.histogram(data, bins=bins)
    p = _base_figure(f"Histogram — {plain}", tex, "Count")
    p.quad(top=counts, bottom=0, left=edges[:-1], right=edges[1:],
           fill_color=_ACCENT2, line_color="white", alpha=0.85)
    p.y_range.start = 0
    pat = fmt_mod.tick_pattern(edges)
    p.add_tools(HoverTool(tooltips=[("Range", f"@left{{{pat}}}–@right{{{pat}}}"), ("Count", "@top")]))
    fmt_mod.apply_number_format(p, edges, axis="x")
    return p


def bar_figure(series: pd.Series, column: str, max_categories: int = 30):
    counts = series.value_counts().head(max_categories)
    cats = [str(i) for i in counts.index]
    source = ColumnDataSource(data={"cats": cats, "count": counts.to_numpy()})
    p = _base_figure(f"Frequency — {notation.plain_label(column)}", notation.plain_label(column), "Count", x_range=cats)
    p.vbar(x="cats", top="count", width=0.8, source=source,
           fill_color=_ACCENT, line_color="white", alpha=0.85)
    p.y_range.start = 0
    p.xaxis.major_label_orientation = 0.8
    p.xgrid.grid_line_color = None
    p.add_tools(HoverTool(tooltips=[("Category", "@cats"), ("Count", "@count")]))
    return p


def pdf_cdf_figure(values: np.ndarray, column: str, dist: str = "normal",
                   bins: int = 30, scale: str = "linear"):
    data = scales_mod.transform(values, scale, name=column)
    tex = scales_mod.axis_label(column, scale)
    plain = scales_mod.plain_axis_label(column, scale)
    stats_data = stats_mod.pdf_cdf_data(data, dist=dist, bins=bins)
    pat = fmt_mod.tick_pattern(data)

    pdf = _base_figure(f"PDF — {plain}", tex, "Density", height=300)
    pdf.quad(top=stats_data.density, bottom=0,
             left=stats_data.bin_edges[:-1], right=stats_data.bin_edges[1:],
             fill_color=_ACCENT2, line_color="white", alpha=0.5, legend_label="Histogram")
    pdf.line(stats_data.pdf_x, stats_data.pdf_y, color=_ACCENT, line_width=3,
             legend_label=f"Fitted {stats_data.params_label}")
    pdf.y_range.start = 0
    pdf.legend.location = "top_right"
    pdf.legend.label_text_font_size = "8pt"
    fmt_mod.apply_number_format(pdf, data, axis="x")

    cdf = _base_figure(f"CDF — {plain}", tex, "Cumulative probability", height=300)
    cdf.scatter(stats_data.ecdf_x, stats_data.ecdf_y, size=5, color=_ACCENT2,
                alpha=0.7, legend_label="Empirical CDF")
    cdf.line(stats_data.cdf_x, stats_data.cdf_y, color=_ACCENT, line_width=3,
             legend_label="Fitted CDF")
    cdf.legend.location = "bottom_right"
    cdf.legend.label_text_font_size = "8pt"
    fmt_mod.apply_number_format(cdf, data, axis="x")

    return bk_column(pdf, cdf, sizing_mode="stretch_width")


def qq_figure(values: np.ndarray, column: str, dist: str = "normal"):
    # No scale option here on purpose: a Q-Q plot's whole diagnostic is whether
    # points fall on a straight line, which rescaling the axes would destroy.
    data = stats_mod.qq_data(values, dist=dist)
    p = _base_figure(f"Q-Q plot ({dist}) — {notation.plain_label(column)}", data.space_label, "Ordered sample values")
    p.scatter(data.theoretical, data.ordered, size=6, color=_ACCENT2, alpha=0.8)
    line_x = np.array([data.theoretical.min(), data.theoretical.max()])
    line_y = data.slope * line_x + data.intercept
    p.line(line_x, line_y, color=_ACCENT, line_width=2,
           legend_label=f"Reference (R={fmt(data.r)})")
    p.legend.location = "top_left"
    fmt_mod.apply_number_format(p, data.ordered)
    return p


def kde_figure(values: np.ndarray, column: str, kernel: str = "gaussian",
               bw="ISJ", scale: str = "linear"):
    data = scales_mod.transform(values, scale, name=column)
    tex = scales_mod.axis_label(column, scale)
    plain = scales_mod.plain_axis_label(column, scale)
    x, y = kde_mod.kde_curve(data, kernel=kernel, bw=bw)
    bw_label = bw if isinstance(bw, str) else fmt(bw)
    p = _base_figure(f"KDE — {plain}", tex, "Density")
    p.varea(x=x, y1=0, y2=y, fill_color=_ACCENT2, alpha=0.25)
    p.line(x, y, color=_ACCENT, line_width=3, legend_label=f"{kernel}, bw={bw_label}")
    p.y_range.start = 0
    p.legend.location = "top_right"
    fmt_mod.apply_number_format(p, x, axis="x")
    return p


# --------------------------------------------------------------------------- #
# Group 2 — bivariate
# --------------------------------------------------------------------------- #

def scatter_figure(
    df: pd.DataFrame, x_col: str, y_col: str,
    fit_kind: str | None = None, with_band: bool = False,
    error_col: str | None = None,
    x_scale: str = "linear", y_scale: str = "linear",
):
    sub_cols = [x_col, y_col] + ([error_col] if error_col else [])
    sub = df[sub_cols].apply(pd.to_numeric, errors="coerce").dropna()
    if sub.empty:
        raise ValueError("No numeric (X, Y) pairs to plot.")
    x_raw = sub[x_col].to_numpy(dtype=float)
    y_raw = sub[y_col].to_numpy(dtype=float)

    # Transform only for display; the fit below stays on the raw data so its
    # coefficients and R² remain physically meaningful.
    x = scales_mod.transform(x_raw, x_scale, name=x_col)
    y = scales_mod.transform(y_raw, y_scale, name=y_col)
    x_tex = scales_mod.axis_label(x_col, x_scale)
    y_tex = scales_mod.axis_label(y_col, y_scale)
    x_label = scales_mod.plain_axis_label(x_col, x_scale)
    y_label = scales_mod.plain_axis_label(y_col, y_scale)

    p = _base_figure(f"{y_label} vs {x_label}", x_tex, y_tex, height=420)
    xpat = fmt_mod.tick_pattern(x)
    ypat = fmt_mod.tick_pattern(y)

    if error_col:
        err = sub[error_col].to_numpy(dtype=float)
        upper = scales_mod.transform_lenient(y_raw + err, y_scale)
        lower = scales_mod.transform_lenient(y_raw - err, y_scale)
        src = ColumnDataSource(data={"x": x, "y": y, "upper": upper, "lower": lower})
        p.add_layout(Whisker(base="x", upper="upper", lower="lower", source=src,
                             line_color=_ACCENT2, level="underlay"))
        p.scatter("x", "y", source=src, size=7, color=_ACCENT2, alpha=0.75, legend_label="Data")
    else:
        src = ColumnDataSource(data={"x": x, "y": y})
        p.scatter("x", "y", source=src, size=7, color=_ACCENT2, alpha=0.75, legend_label="Data")

    if fit_kind:
        fit = fits_mod.fit_curve(x_raw, y_raw, fit_kind, with_band=with_band)
        gx = scales_mod.transform_lenient(fit.x_grid, x_scale)
        gy = scales_mod.transform_lenient(fit.y_grid, y_scale)
        if fit.band is not None:
            band_src = ColumnDataSource(data={
                "x": gx,
                "lower": scales_mod.transform_lenient(fit.band[0], y_scale),
                "upper": scales_mod.transform_lenient(fit.band[1], y_scale),
            })
            p.varea(x="x", y1="lower", y2="upper", source=band_src,
                    fill_color=_ACCENT, alpha=0.12)
        p.line(gx, gy, color=_ACCENT, line_width=3,
               legend_label=f"{fit.name} (R²={fmt(fit.r2)})")

    p.legend.location = "top_left"
    p.add_tools(HoverTool(tooltips=[(x_label, f"@x{{{xpat}}}"), (y_label, f"@y{{{ypat}}}")]))
    fmt_mod.apply_number_format(p, np.concatenate([x[np.isfinite(x)], y[np.isfinite(y)]]))
    return p


def grouped_bar_figure(df: pd.DataFrame, x_col: str, y_col: str, group_col: str | None = None):
    """Mean of ``y_col`` per ``x_col`` category, optionally split by ``group_col``.

    Error bars show the within-group standard deviation. No scale option: bars
    are read against a zero baseline, which a log/inverse axis cannot represent.
    """
    if group_col == x_col:
        raise ValueError("Choose a different column to group by than the X column.")
    work = df.copy()
    work[y_col] = pd.to_numeric(work[y_col], errors="coerce")
    work = work.dropna(subset=[x_col, y_col])
    if work.empty:
        raise ValueError("No rows with both a category and a numeric value.")

    if group_col:
        agg = work.groupby([x_col, group_col])[y_col].agg(["mean", "std"]).reset_index()
        x_cats = [str(c) for c in sorted(work[x_col].dropna().unique(), key=str)]
        groups = [str(g) for g in sorted(work[group_col].dropna().unique(), key=str)]
        factors = [(str(xc), str(g)) for xc in x_cats for g in groups]
        means, stds = [], []
        lookup = {(str(r[x_col]), str(r[group_col])): (r["mean"], r["std"]) for _, r in agg.iterrows()}
        for f in factors:
            m, s = lookup.get(f, (0.0, 0.0))
            means.append(float(m)); stds.append(0.0 if pd.isna(s) else float(s))
        palette = Category10[10]
        colors = [palette[groups.index(f[1]) % 10] for f in factors]
        source = ColumnDataSource(data={
            "factors": factors, "mean": means,
            "upper": [m + s for m, s in zip(means, stds)],
            "lower": [m - s for m, s in zip(means, stds)],
            "color": colors,
        })
        p = _base_figure(f"Mean {notation.plain_label(y_col)} by {notation.plain_label(x_col)} / {notation.plain_label(group_col)}", notation.plain_label(x_col), f"Mean {notation.plain_label(y_col)}",
                         x_range=FactorRange(*factors))
        p.vbar(x="factors", top="mean", width=0.9, source=source,
               fill_color="color", line_color="white", alpha=0.9)
        p.add_layout(Whisker(base="factors", upper="upper", lower="lower", source=source,
                             line_color=_ACCENT))
        values = np.asarray(means, dtype=float)
    else:
        agg = work.groupby(x_col)[y_col].agg(["mean", "std"]).reset_index()
        cats = [str(c) for c in agg[x_col]]
        means = agg["mean"].to_numpy(dtype=float)
        stds = np.nan_to_num(agg["std"].to_numpy(dtype=float))
        source = ColumnDataSource(data={
            "cats": cats, "mean": means, "upper": means + stds, "lower": means - stds,
        })
        p = _base_figure(f"Mean {notation.plain_label(y_col)} by {notation.plain_label(x_col)}", notation.plain_label(x_col), f"Mean {notation.plain_label(y_col)}", x_range=cats)
        p.vbar(x="cats", top="mean", width=0.8, source=source,
               fill_color=_ACCENT2, line_color="white", alpha=0.9)
        p.add_layout(Whisker(base="cats", upper="upper", lower="lower", source=source,
                             line_color=_ACCENT))
        values = means

    p.y_range.start = 0
    p.xgrid.grid_line_color = None
    p.xaxis.major_label_orientation = 0.8
    fmt_mod.apply_number_format(p, values, axis="y")
    return p


def correlation_figure(df: pd.DataFrame, columns: list[str] | None = None):
    numeric = df.select_dtypes(include=[np.number])
    if columns:
        numeric = numeric[[c for c in columns if c in numeric.columns]]
    if numeric.shape[1] < 2:
        raise ValueError("Need at least 2 numeric columns for a correlation matrix.")
    corr = numeric.corr()
    # Raw names index the matrix; pretty labels are what the axes display.
    raw_cols = [str(c) for c in corr.columns]
    cols = [notation.plain_label(c) for c in raw_cols]
    display = dict(zip(raw_cols, cols))

    xs, ys, vals = [], [], []
    for yi in raw_cols:
        for xi in raw_cols:
            xs.append(display[xi]); ys.append(display[yi])
            vals.append(float(corr.loc[yi, xi]))
    source = ColumnDataSource(data={
        "x": xs, "y": ys, "value": vals, "label": [fmt(v) for v in vals],
    })
    mapper = LinearColorMapper(palette=list(reversed(RdBu[11])), low=-1.0, high=1.0)

    p = figure(
        title="Correlation matrix", x_range=cols, y_range=list(reversed(cols)),
        tools="hover,save", toolbar_location="above", sizing_mode="stretch_width",
        height=max(320, 60 * len(cols)),
        tooltips=[("Pair", "@y / @x"), ("r", "@value{0.00}")],
    )
    p.rect(x="x", y="y", width=1, height=1, source=source,
           fill_color={"field": "value", "transform": mapper}, line_color="white")
    p.add_layout(LabelSet(x="x", y="y", text="label", source=source,
                          text_align="center", text_baseline="middle", text_font_size="9pt"))
    p.add_layout(ColorBar(color_mapper=mapper, title="r"), "right")
    p.xaxis.major_label_orientation = 0.8
    p.grid.grid_line_color = None
    return p


# --------------------------------------------------------------------------- #
# Group 3 — scientific (gridded)
# --------------------------------------------------------------------------- #

def contour_figure(grid: GridData, n_levels: int = 10, filled: bool = True,
                   palette_name: str = DEFAULT_COLORMAP):
    C = grid.values
    finite = C[np.isfinite(C)]
    if finite.size == 0:
        raise ValueError("The grid has no finite values to contour.")
    low, high = float(finite.min()), float(finite.max())
    if low == high:
        high = low + 1.0
    levels = np.linspace(low, high, n_levels)

    p = _base_figure(f"Contour — {notation.plain_label(grid.value_label)}",
                     notation.latex_label(grid.x_label), notation.latex_label(grid.y_label),
                     height=440, x_range=(float(grid.x.min()), float(grid.x.max())),
                     y_range=(float(grid.y.min()), float(grid.y.max())))
    full = colormap(palette_name)
    palette = [full[int(i)] for i in np.linspace(0, len(full) - 1, max(n_levels - 1, 1))]
    contour = p.contour(grid.x, grid.y, C, levels,
                        fill_color=palette if filled else None,
                        line_color="#00000033")
    colorbar = contour.construct_color_bar(title=notation.plain_label(grid.value_label))
    # A ContourColorBar labels a FixedTicker at the level values and ignores a
    # swapped-in formatter, so set the label text for each level explicitly.
    colorbar.major_label_overrides = {float(lv): fmt(lv) for lv in levels}
    p.add_layout(colorbar, "right")
    fmt_mod.apply_number_format(p, np.concatenate([grid.x, grid.y]))
    return p


def quiver_figure(grid: GridData, palette_name: str = "Red-Yellow-Green"):
    vectors = gradient_vectors(grid)
    finite = grid.values[np.isfinite(grid.values)]
    c_min = float(finite.min()) if finite.size else 0.0
    c_max = float(finite.max()) if finite.size else 1.0
    if c_min == c_max:
        c_max = c_min + 1.0

    p = _base_figure(f"Gradient vectors — {notation.plain_label(grid.value_label)}",
                     notation.latex_label(grid.x_label), notation.latex_label(grid.y_label),
                     height=440, x_range=(float(grid.x.min()), float(grid.x.max())),
                     y_range=(float(grid.y.min()), float(grid.y.max())))
    mapper = LinearColorMapper(palette=colormap(palette_name), low=c_min, high=c_max)
    p.image(image=[np.flipud(grid.values)], x=float(grid.x.min()), y=float(grid.y.min()),
            dw=float(grid.x.max()) - float(grid.x.min()),
            dh=float(grid.y.max()) - float(grid.y.min()),
            color_mapper=mapper, alpha=0.45)
    source = ColumnDataSource(data=vectors)
    p.segment("x0", "y0", "x1", "y1", source=source, color=_ACCENT, line_width=1.4, alpha=0.85)
    p.scatter("x1", "y1", angle="angle", source=source, marker="triangle",
              color=_ACCENT, size=7, alpha=0.9)
    pat = fmt_mod.tick_pattern(vectors["magnitude"])
    p.add_tools(HoverTool(tooltips=[("Gradient magnitude", f"@magnitude{{{pat}}}")]))
    p.add_layout(ColorBar(color_mapper=mapper, title=notation.plain_label(grid.value_label),
                          formatter=NumeralTickFormatter(format=fmt_mod.tick_pattern(finite))),
                 "right")
    fmt_mod.apply_number_format(p, np.concatenate([grid.x, grid.y]))
    return p


def profile_line_options(grid: GridData, axis: str = "x") -> list[float]:
    """Coordinates you can draw a profile at, i.e. the other axis's grid lines."""
    return [float(v) for v in (grid.y if axis == "x" else grid.x)]


def profile_figure(grid: GridData, axis: str = "x", at: float | None = None):
    """Profile of the gridded value along one axis.

    ``at`` selects a single grid line on the *other* axis (the nearest one is
    used); leaving it ``None`` averages over that axis instead.
    """
    if axis not in ("x", "y"):
        raise ValueError("Profile axis must be 'x' or 'y'.")

    if axis == "x":
        coord, xcol = grid.x, grid.x_label
        other, other_col = grid.y, grid.y_label
    else:
        coord, xcol = grid.y, grid.y_label
        other, other_col = grid.x, grid.x_label
    xlabel = notation.plain_label(xcol)
    other_label = notation.plain_label(other_col)
    value_label = notation.plain_label(grid.value_label)

    if at is None:
        profile = np.nanmean(grid.values, axis=0 if axis == "x" else 1)
        subtitle = f"mean over {other_label}"
    else:
        idx = int(np.argmin(np.abs(other - float(at))))
        actual = float(other[idx])
        profile = grid.values[idx, :] if axis == "x" else grid.values[:, idx]
        subtitle = f"at {other_label} = {fmt(actual)}"

    p = _base_figure(f"{value_label} along {xlabel} ({subtitle})",
                     notation.latex_label(xcol), notation.latex_label(grid.value_label),
                     height=340)
    source = ColumnDataSource(data={"x": coord, "value": profile})
    p.line("x", "value", source=source, color="#0d766e", line_width=3)
    p.scatter("x", "value", source=source, color="#0d766e", size=5, alpha=0.7)
    xpat = fmt_mod.tick_pattern(coord)
    vpat = fmt_mod.tick_pattern(profile)
    p.add_tools(HoverTool(tooltips=[(xlabel, f"@x{{{xpat}}}"),
                                    (value_label, f"@value{{{vpat}}}")]))
    fmt_mod.apply_number_format(p, np.concatenate([coord, profile[np.isfinite(profile)]]))
    return p
