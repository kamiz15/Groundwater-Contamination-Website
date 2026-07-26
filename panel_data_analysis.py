"""Visual Analysis Workbench — a standalone Panel app.

Users upload a CSV (results from the AEM/analytical or numerical methods, or any
external data) and explore it through four tabs:

  * Univariate  — histogram, frequency bar, PDF/CDF, Q-Q (normal/lognormal), KDE
  * Bivariate   — scatter with optional fits + confidence band + error bars,
                  grouped/mean bars, correlation matrix
  * Scientific  — contour, gradient-vector (quiver) and profile plots from a
                  regular grid promoted out of the uploaded data
  * Statistics  — df.describe() (+ skew/kurtosis/missing), downloadable as CSV

The UI is intentionally thin: every computation lives in the ``data_analysis``
package so it stays unit-testable. Uploaded data is held only in per-session
closures, so it is never persisted or shared between users.

Plots are produced with ``pn.bind`` rather than by mutating a pre-created Bokeh
pane. Letting Panel own each pane's lifecycle (mount a fresh figure, replace it
wholesale on change) avoids the "dropping a patch" model-sync failures that
blank-swapping a shared ``pn.pane.Bokeh`` inside ``pn.Tabs`` runs into.

Run standalone for development::

    python panel_data_analysis.py    # then open http://localhost:5008

To wire it into the site's Panel server later, add one entry to the ``apps``
dict in ``panel_server.py``::

    "panel_data_analysis": data_analysis_app
"""
from __future__ import annotations

import html
import io
import logging

import numpy as np
import pandas as pd
import panel as pn

from data_analysis import datasets, plots
from data_analysis import formatting as fmt_mod
from data_analysis import stats as stats_mod
from data_analysis.fits import FIT_TYPES
from data_analysis.grids import long_form_from_aem_result, pivot_gridded
from data_analysis.kde import BANDWIDTHS, KERNELS
from data_analysis.plots import COLORMAPS, DEFAULT_COLORMAP, profile_line_options
from data_analysis.scales import SCALES
from data_analysis.stats import DISTRIBUTIONS
from data_queries import get_user_sites_rows
from numerical_jobs import fetch_result, job_status, load_job_meta
from panel_auth import authenticated_email
from symbol_registry import SITE_COLUMN_DEFS, ui_label_markup

try:
    # Reuse the site's card styling when available (running inside the app).
    from panel_analytical_common import error_card, info_card
except Exception:  # pragma: no cover - standalone fallback
    def info_card(message: str) -> str:
        return f'<div style="padding:14px;border:1px solid #dce9f9;border-radius:12px;background:#fff;">{message}</div>'

    def error_card(message) -> str:
        return f'<div style="padding:14px;border:1px solid #f1b7b7;border-radius:12px;background:#fff4f4;color:#7a1d1d;">{message}</div>'

# "mathjax" is required: without it Bokeh prints the raw LaTeX source of the
# axis labels produced by data_analysis.notation instead of typesetting them.
pn.extension("tabulator", "mathjax", sizing_mode="stretch_width")

_UPLOAD_PROMPT = "Upload a CSV file to begin exploring your data."
_DATABASE_EMPTY_PROMPT = "No uploaded site data is available. Upload a CSV file to begin."
_UPLOAD_CANONICAL_LABELS = [
    label for field, label, _unit in SITE_COLUMN_DEFS
    if field in {"aquifer_thickness", "plume_length", "plume_width", "hydraulic_conductivity", "electron_donor", "electron_acceptor_o2"}
]
_UPLOAD_HELP = (
    "<b>CSV notation:</b> recognized headers are normalized to "
    + ", ".join(ui_label_markup(label) for label in _UPLOAD_CANONICAL_LABELS)
    + ". Custom columns keep their original names."
)
logger = logging.getLogger(__name__)


def _request_argument(name: str) -> str:
    """Read one Panel request argument without trusting it as identity."""
    try:
        request = pn.state.curdoc.session_context.request
        values = request.arguments.get(name)
        if values:
            raw = values[0]
            return (raw.decode() if isinstance(raw, bytes) else str(raw)).strip()
    except Exception:
        pass
    return ""


def _load_aem_job_frame(job_id: str, email: str):
    """Load one completed AEM grid after independently checking its owner."""
    meta = load_job_meta(job_id)
    status = job_status(job_id) if meta else None
    if (
        meta is None
        or meta.get("email") != email
        or meta.get("kind") not in {"aem_forward", "aem_inverse"}
        or status is None
        or status.get("status") != "done"
    ):
        raise ValueError("The requested AEM result is unavailable.")

    try:
        frame = long_form_from_aem_result(fetch_result(job_id))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("The requested AEM result has no usable concentration grid.") from exc

    value_column = "concentration [mg/L]"
    if not np.isfinite(frame[value_column].to_numpy(dtype=float)).all():
        raise ValueError("The requested AEM result has incomplete concentration values.")

    kind = "forward" if meta["kind"] == "aem_forward" else "inverse"
    return frame, f"AEM {kind} result"


def _info_pane(message: str):
    return pn.pane.HTML(info_card(message), sizing_mode="stretch_width")


def _error_pane(exc):
    return pn.pane.HTML(error_card(exc), sizing_mode="stretch_width")


def _plot_pane(fig, min_height: int = 420):
    return pn.pane.Bokeh(fig, sizing_mode="stretch_width", min_height=min_height)


def data_analysis_app():
    # --- per-session state (never persisted) -------------------------------
    state: dict = {"df": None, "grid": None, "source": None}

    # Hidden "version" triggers: bumping these re-fires the pn.bind views even
    # when the widget values themselves are unchanged (e.g. re-uploading a file
    # with the same column names).
    data_version = pn.widgets.IntInput(value=0, visible=False)
    grid_version = pn.widgets.IntInput(value=0, visible=False)

    # ===================================================================== #
    # Data intake
    # ===================================================================== #
    database_btn = pn.widgets.Button(
        name="Refresh site database", button_type="primary", width=190,
    )
    file_input = pn.widgets.FileInput(
        name="Upload another CSV", accept=".csv", multiple=False,
    )
    status_pane = pn.pane.HTML(
        info_card("Loading your site database..."), sizing_mode="stretch_width"
    )
    preview = pn.widgets.Tabulator(
        pd.DataFrame(), height=220, disabled=True, show_index=False,
        layout="fit_columns", name="Data preview", sizing_mode="stretch_width",
    )

    # Column selectors shared across tabs (populated on upload).
    uni_col = pn.widgets.Select(name="Column", options=[])
    biv_x = pn.widgets.Select(name="X column", options=[])
    biv_y = pn.widgets.Select(name="Y column", options=[])
    biv_group = pn.widgets.Select(name="Group by (optional)", options=["(none)"])
    err_col = pn.widgets.Select(name="Error-bar column", options=["(none)"])
    grid_x = pn.widgets.Select(name="Grid X column", options=[])
    grid_y = pn.widgets.Select(name="Grid Y column", options=[])
    grid_v = pn.widgets.Select(name="Grid value column", options=[])

    def _apply_dataframe(df: pd.DataFrame, source_name: str) -> None:
        state["df"] = df
        state["source"] = source_name
        numeric = datasets.numeric_columns(df)
        measurement_numeric = [col for col in numeric if col != "Site Number"] or numeric
        all_cols = list(df.columns)
        summary = datasets.dataset_summary(df)

        # Keep Site Number available as an axis, but default analytical views
        # to an actual measurement rather than a histogram of row numbers.
        uni_col.options = numeric
        biv_x.options = numeric
        biv_y.options = numeric
        if numeric:
            uni_col.value = measurement_numeric[0]
            biv_x.value = "Site Number" if "Site Number" in numeric else numeric[0]
            biv_y.value = measurement_numeric[0]
        # optional numeric selectors with a sentinel
        err_col.options = ["(none)"] + numeric
        err_col.value = "(none)"
        # all-column selectors
        biv_group.options = ["(none)"] + all_cols
        biv_group.value = "(none)"
        for w, idx in ((grid_x, 0), (grid_y, 1), (grid_v, 2)):
            w.options = all_cols
            w.value = all_cols[min(idx, len(all_cols) - 1)]

        # Preview shows two decimals like the rest of the tool; the download
        # and every computation still use the full-precision values.
        preview.value = fmt_mod.format_frame(df.head(10))
        numeric_txt = html.escape(", ".join(summary["numeric_cols"]) or "none")
        status_pane.object = info_card(
            f"<b>Data source:</b> {html.escape(source_name)}<br>"
            f"<b>{summary['rows']} rows × {summary['cols']} columns.</b><br>"
            f"Numeric columns: {numeric_txt}.<br>"
            f"Missing cells: {summary['missing_cells']}."
        )
        # A new grid must be rebuilt for the scientific tab.
        state["grid"] = None
        sci_type.disabled = True
        grid_status.object = info_card(_GRID_PROMPT)
        # Fire every bound view once.
        data_version.value += 1

    def _clear_dataframe(message: str) -> None:
        state.update({"df": None, "grid": None, "source": None})
        for widget in (uni_col, biv_x, biv_y, grid_x, grid_y, grid_v):
            widget.options = []
        biv_group.options = ["(none)"]
        biv_group.value = "(none)"
        err_col.options = ["(none)"]
        err_col.value = "(none)"
        preview.value = pd.DataFrame()
        status_pane.object = info_card(
            f"{html.escape(message)}<br>{_UPLOAD_HELP}"
        )
        sci_type.disabled = True
        grid_status.object = info_card(_GRID_PROMPT)
        data_version.value += 1

    def _load_database(_=None):
        try:
            email = authenticated_email()
            rows = get_user_sites_rows(email) if email else []
            frame = datasets.site_rows_frame(rows)
        except Exception:
            logger.exception("Could not load the site database into the Data Workbench")
            status_pane.object = error_card("Could not load your site database.")
            return
        if frame.empty:
            _clear_dataframe(_DATABASE_EMPTY_PROMPT)
            return
        _apply_dataframe(frame, "Site database")

    def _on_upload(_=None):
        if not file_input.value:
            return
        try:
            df = datasets.load_csv(file_input.value)
        except Exception as exc:
            status_pane.object = error_card(exc)
            return
        filename = file_input.filename or "Uploaded CSV"
        _apply_dataframe(df, f"Temporary CSV - {filename}")

    file_input.param.watch(_on_upload, "value")
    database_btn.on_click(_load_database)

    # ===================================================================== #
    # Tab 1 — Univariate
    # ===================================================================== #
    uni_type = pn.widgets.Select(
        name="Plot type",
        options=["Histogram", "Frequency bar", "PDF & CDF", "Q-Q", "KDE"],
    )
    uni_bins = pn.widgets.IntSlider(name="Bins", start=5, end=100, step=1, value=30)
    uni_dist = pn.widgets.RadioButtonGroup(name="Distribution", options=list(DISTRIBUTIONS))
    uni_kernel = pn.widgets.Select(name="KDE kernel", options=list(KERNELS))
    uni_bw = pn.widgets.Select(name="Bandwidth", options=list(BANDWIDTHS) + ["manual"])
    uni_bw_manual = pn.widgets.FloatInput(name="Manual bandwidth", value=1.0, start=1e-6, visible=False)
    # Scale applies to the value axis. Deliberately hidden for Q-Q (rescaling
    # destroys the straight-line diagnostic) and Frequency bar (X is categorical).
    uni_scale = pn.widgets.Select(name="Value scale", options=list(SCALES))

    _UNI_SCALABLE = ("Histogram", "PDF & CDF", "KDE")

    def _uni_option_visibility(*_):
        t = uni_type.value
        uni_bins.visible = t in ("Histogram", "PDF & CDF")
        uni_dist.visible = t in ("PDF & CDF", "Q-Q")
        uni_kernel.visible = t == "KDE"
        uni_bw.visible = t == "KDE"
        uni_bw_manual.visible = t == "KDE" and uni_bw.value == "manual"
        uni_scale.visible = t in _UNI_SCALABLE

    def _uni_view(_v, col, ptype, bins, dist, kernel, bw, bw_manual, scale):
        df = state["df"]
        if df is None or not col:
            return _info_pane(_UPLOAD_PROMPT)
        try:
            values = datasets.numeric_series(df, col)
            if ptype == "Histogram":
                fig = plots.histogram_figure(values, col, bins=bins, scale=scale)
            elif ptype == "Frequency bar":
                fig = plots.bar_figure(df[col], col)
            elif ptype == "PDF & CDF":
                fig = plots.pdf_cdf_figure(values, col, dist=dist, bins=bins, scale=scale)
            elif ptype == "Q-Q":
                fig = plots.qq_figure(values, col, dist=dist)
            else:  # KDE
                b = bw_manual if bw == "manual" else bw
                fig = plots.kde_figure(values, col, kernel=kernel, bw=b, scale=scale)
            return _plot_pane(fig)
        except Exception as exc:
            return _error_pane(exc)

    uni_output = pn.panel(
        pn.bind(_uni_view, data_version, uni_col, uni_type, uni_bins,
                uni_dist, uni_kernel, uni_bw, uni_bw_manual, uni_scale),
        sizing_mode="stretch_width",
    )
    uni_type.param.watch(_uni_option_visibility, "value")
    uni_bw.param.watch(_uni_option_visibility, "value")

    tab_univariate = pn.Column(
        pn.Row(uni_col, uni_type, uni_scale),
        pn.Row(uni_bins, uni_dist),
        pn.Row(uni_kernel, uni_bw, uni_bw_manual),
        uni_output, sizing_mode="stretch_width",
    )

    # ===================================================================== #
    # Tab 2 — Bivariate
    # ===================================================================== #
    biv_type = pn.widgets.Select(
        name="Plot type", options=["Scatter", "Grouped bars", "Correlation matrix"],
    )
    biv_fit_on = pn.widgets.Checkbox(name="Add fit", value=False)
    biv_fit_kind = pn.widgets.Select(name="Fit type", options=list(FIT_TYPES), visible=False)
    biv_band = pn.widgets.Checkbox(name="95% confidence band", value=False, visible=False)
    # Scatter is the only bivariate plot with two numeric axes to rescale;
    # bars read against a zero baseline and the correlation matrix has no axes.
    biv_x_scale = pn.widgets.Select(name="X scale", options=list(SCALES))
    biv_y_scale = pn.widgets.Select(name="Y scale", options=list(SCALES))

    def _biv_option_visibility(*_):
        t = biv_type.value
        is_scatter = t == "Scatter"
        biv_y.visible = t in ("Scatter", "Grouped bars")
        biv_group.visible = t == "Grouped bars"
        biv_fit_on.visible = is_scatter
        biv_fit_kind.visible = is_scatter and biv_fit_on.value
        biv_band.visible = is_scatter and biv_fit_on.value
        err_col.visible = is_scatter
        biv_x_scale.visible = is_scatter
        biv_y_scale.visible = is_scatter

    def _biv_view(_v, ptype, x, y, group, fit_on, fit_kind, band, error, xs, ys):
        df = state["df"]
        if df is None or not x:
            return _info_pane(_UPLOAD_PROMPT)
        try:
            if ptype == "Scatter":
                kind = fit_kind if fit_on else None
                err = None if error == "(none)" else error
                fig = plots.scatter_figure(df, x, y, fit_kind=kind, with_band=band,
                                           error_col=err, x_scale=xs, y_scale=ys)
            elif ptype == "Grouped bars":
                g = None if group == "(none)" else group
                fig = plots.grouped_bar_figure(df, x, y, group_col=g)
            else:
                fig = plots.correlation_figure(df)
            return _plot_pane(fig, min_height=440)
        except Exception as exc:
            return _error_pane(exc)

    biv_output = pn.panel(
        pn.bind(_biv_view, data_version, biv_type, biv_x, biv_y, biv_group,
                biv_fit_on, biv_fit_kind, biv_band, err_col, biv_x_scale, biv_y_scale),
        sizing_mode="stretch_width",
    )
    biv_type.param.watch(_biv_option_visibility, "value")
    biv_fit_on.param.watch(_biv_option_visibility, "value")

    tab_bivariate = pn.Column(
        pn.Row(biv_x, biv_y, biv_group),
        pn.Row(biv_type, biv_fit_on, biv_fit_kind, biv_band, err_col),
        pn.Row(biv_x_scale, biv_y_scale),
        biv_output, sizing_mode="stretch_width",
    )

    # ===================================================================== #
    # Tab 3 — Scientific (gridded)
    # ===================================================================== #
    _GRID_PROMPT = (
        "Pick X, Y and value columns from your data, then build a regular grid "
        "to enable contour and vector plots."
    )
    grid_btn = pn.widgets.Button(name="Use these columns as a grid", button_type="primary")
    grid_status = pn.pane.HTML(info_card(_GRID_PROMPT))
    sci_type = pn.widgets.Select(
        name="Plot type", options=["Contour", "Gradient vectors", "Profile"], disabled=True,
    )
    sci_levels = pn.widgets.IntSlider(name="Contour levels", start=4, end=30, value=10)
    sci_axis = pn.widgets.RadioButtonGroup(name="Profile along", options=["x", "y"], visible=False)
    sci_colormap = pn.widgets.Select(name="Colour map", options=list(COLORMAPS),
                                     value=DEFAULT_COLORMAP)
    # Which grid line to profile along; "Mean" averages over the other axis.
    _MEAN_LABEL = "Mean (all lines)"
    sci_at = pn.widgets.Select(name="Profile line", options={_MEAN_LABEL: "mean"},
                               value="mean", visible=False)

    def _refresh_profile_lines(*_):
        """Repopulate the profile-line picker with the current grid's coordinates."""
        grid = state["grid"]
        if grid is None:
            sci_at.options = {_MEAN_LABEL: "mean"}
            sci_at.value = "mean"
            return
        axis = sci_axis.value
        other_label = grid.y_label if axis == "x" else grid.x_label
        options = {_MEAN_LABEL: "mean"}
        for coord in profile_line_options(grid, axis):
            options[f"{other_label} = {fmt_mod.fmt(coord)}"] = float(coord)
        sci_at.options = options
        if sci_at.value not in options.values():
            sci_at.value = "mean"

    def _build_grid(_=None):
        df = state["df"]
        if df is None:
            grid_status.object = error_card(_UPLOAD_PROMPT)
            return
        try:
            grid = pivot_gridded(df, grid_x.value, grid_y.value, grid_v.value)
            state["grid"] = grid
            sci_type.disabled = False
            grid_status.object = info_card(
                f"Grid ready: {len(grid.x)} × {len(grid.y)} "
                f"({grid.x_label} × {grid.y_label}, value {grid.value_label})."
            )
            _refresh_profile_lines()
            grid_version.value += 1
        except Exception as exc:
            state["grid"] = None
            sci_type.disabled = True
            grid_status.object = error_card(exc)

    def _sci_option_visibility(*_):
        t = sci_type.value
        sci_levels.visible = t == "Contour"
        sci_axis.visible = t == "Profile"
        sci_at.visible = t == "Profile"
        # Both the contour and the quiver background are heat maps.
        sci_colormap.visible = t in ("Contour", "Gradient vectors")

    def _sci_view(_v, ptype, levels, axis, at, cmap):
        grid = state["grid"]
        if grid is None:
            return _info_pane(_GRID_PROMPT)
        try:
            if ptype == "Contour":
                fig = plots.contour_figure(grid, n_levels=levels, palette_name=cmap)
            elif ptype == "Gradient vectors":
                fig = plots.quiver_figure(grid, palette_name=cmap)
            else:
                at_value = None if at == "mean" else float(at)
                fig = plots.profile_figure(grid, axis=axis, at=at_value)
            return _plot_pane(fig, min_height=440)
        except Exception as exc:
            return _error_pane(exc)

    sci_output = pn.panel(
        pn.bind(_sci_view, grid_version, sci_type, sci_levels, sci_axis, sci_at, sci_colormap),
        sizing_mode="stretch_width",
    )
    grid_btn.on_click(_build_grid)
    sci_type.param.watch(_sci_option_visibility, "value")
    sci_axis.param.watch(_refresh_profile_lines, "value")

    tab_scientific = pn.Column(
        pn.Row(grid_x, grid_y, grid_v, grid_btn),
        grid_status,
        pn.Row(sci_type, sci_colormap, sci_levels),
        pn.Row(sci_axis, sci_at),
        sci_output, sizing_mode="stretch_width",
    )

    # ===================================================================== #
    # Tab 4 — Statistics
    # ===================================================================== #
    def _stats_view(_v):
        df = state["df"]
        if df is None:
            return _info_pane(_UPLOAD_PROMPT)
        try:
            table = stats_mod.describe_frame(df).reset_index(names="column")
            # Displayed to two decimals; the CSV download keeps full precision.
            return pn.widgets.Tabulator(
                fmt_mod.format_frame(table), disabled=True,
                layout="fit_columns", height=340, sizing_mode="stretch_width",
            )
        except Exception as exc:
            return _error_pane(exc)

    stats_output = pn.panel(pn.bind(_stats_view, data_version), sizing_mode="stretch_width")

    def _stats_csv():
        df = state["df"]
        if df is None:
            return io.BytesIO(b"")
        return io.BytesIO(stats_mod.stats_csv_bytes(df))

    def _data_csv():
        df = state["df"]
        if df is None:
            return io.BytesIO(b"")
        return io.BytesIO(stats_mod.frame_csv_bytes(df))

    stats_download = pn.widgets.FileDownload(
        callback=_stats_csv, filename="dataset_statistics.csv",
        label="↓ Download statistics (CSV)", button_type="primary",
    )
    data_download = pn.widgets.FileDownload(
        callback=_data_csv, filename="dataset.csv",
        label="↓ Download dataset (CSV)", button_type="default",
    )

    tab_statistics = pn.Column(
        pn.Row(stats_download, data_download),
        stats_output, sizing_mode="stretch_width",
    )

    # ===================================================================== #
    # Assemble
    # ===================================================================== #
    _uni_option_visibility()
    _biv_option_visibility()
    _sci_option_visibility()

    intake = pn.Column(
        "### 1. Data source",
        pn.Row(database_btn, file_input),
        status_pane, preview,
        data_version, grid_version,
        sizing_mode="stretch_width",
    )
    tabs = pn.Tabs(
        ("Univariate", tab_univariate),
        ("Bivariate", tab_bivariate),
        ("Scientific", tab_scientific),
        ("Statistics", tab_statistics),
    )

    aem_job_id = _request_argument("aem_job")
    if aem_job_id:
        try:
            email = authenticated_email()
            if not email:
                raise ValueError("Authenticated user information is unavailable.")
            frame, source_name = _load_aem_job_frame(aem_job_id, email)
            _apply_dataframe(frame, source_name)
            grid_x.value, grid_y.value, grid_v.value = frame.columns
            _build_grid()
            if state["grid"] is None:
                raise ValueError("The AEM concentration grid could not be prepared.")
            tabs.active = 2
        except Exception:
            logger.exception("Could not load the requested AEM result into the Data Workbench")
            _clear_dataframe("The requested AEM result could not be loaded.")
            status_pane.object = error_card("The requested AEM result could not be loaded.")
    else:
        _load_database()

    return pn.Column(
        intake,
        "### 2. Explore",
        tabs,
        sizing_mode="stretch_width",
        styles={"gap": "12px", "max-width": "1200px", "margin": "0 auto"},
    )


if __name__ == "__main__":
    pn.serve(data_analysis_app, port=5008, show=False, title="Data Analysis Workbench")
