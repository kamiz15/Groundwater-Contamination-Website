"""Scenario-table multiple simulation for the analytical / empirical models.

The old CAST multiple page was a *list of parameter sets*: typed in through the
"Add Data" modal or uploaded as a CSV, kept in a table, and plotted against the
measured plume lengths of the sites. panel_site_comparison only runs the sites
ticked in the sidebar and draws no measured series, so this module restores that
mode:

  * scenarios are added through a dialog, or uploaded as CSV (template provided)
  * one run covers both: the sites ticked in the sidebar AND the typed rows
  * the graph draws each modelled Lmax against the measured value of its site
  * results download as CSV, and the report bridge carries the run to the PDF

The single "Run Scenarios" button lives on the page, not in here - see
_RUN_LISTENER_HTML for how the ticked site ids reach this document.

Model-agnostic - everything per-model comes from panel_site_comparison.MODEL_SPECS.
Wired to Liedl first; the other models are one call each.
"""
from __future__ import annotations

import html as _html
import io
import json
import logging

import pandas as pd
import panel as pn

from data_queries import get_user_sites_rows, reference_sites_rows
from model_site_validation import filter_valid_sites_for_model
from panel_analytical_common import (
    MEASURED_COLOR, SITE_COLOR, comparison_plot, error_card,
)
from panel_auth import authenticated_email
from panel_site_comparison import (
    FORM_ALIASES, MODEL_SPECS, manual_fallback, selected_site_ids, site_label,
)
from param_meta import table_titles
from symbol_registry import db_to_model
from panel_theme import COMPONENT_CSS, frame_height_bridge_html, report_bridge_html
from pdf_report import dataframe_pdf

pn.extension("tabulator", sizing_mode="stretch_width")

logger = logging.getLogger(__name__)

SITE_COLUMN = "Site"
MEASURED_COLUMN = "Measured Lmax [m]"
RESULT_COLUMN = "Model Lmax [m]"

# ponytail: a flat cap rather than paging. These models are closed-form, so the
# limit is about a readable graph and a sane PDF, not compute. Raise it if a user
# genuinely needs more rows on one chart.
MAX_SCENARIOS = 200

# The graph box, and the stage row around it. One number rather than three: the
# picker on the left is built to _STAGE_HEIGHT so its list ends exactly where
# the graph does, which is the whole point of putting them side by side.
_GRAPH_HEIGHT = 420
_RUN_ROW_HEIGHT = 46
_STAGE_HEIGHT = _GRAPH_HEIGHT + _RUN_ROW_HEIGHT

# How the picker and the graph share the stage row. The picker holds 340px and
# never grows; the graph takes what is left. Below the two min-widths (plus the
# 14px gap, so about 574px of frame) they stop fitting and the graph wraps under
# the picker - which is the whole point, since a phone frame is ~350px wide.
_PICKER_FLEX = {"flex": "0 1 340px", "min-width": "260px", "max-width": "100%"}
_GRAPH_FLEX = {"flex": "1 1 420px", "min-width": "300px", "max-width": "100%"}


def scenario_columns(model: str) -> list[str]:
    return [SITE_COLUMN, *MODEL_SPECS[model]["args"], MEASURED_COLUMN]


def column_titles(model: str) -> dict:
    """Header text per column: the names and symbols the single pages use.

    The stored column keys stay canonical (what the model function takes and
    what an uploaded CSV must carry); only the display changes. param_meta
    holds the wording, keyed by the single page's field names, so the canonical
    key is translated through FORM_ALIASES to look it up. Models it does not
    cover - BIOSCREEN - fall back to their own report spec, which carries the
    same three pieces: name, symbol, unit.
    """
    spec = MODEL_SPECS[model]
    aliases = FORM_ALIASES.get(model, {})
    form_names = {arg: aliases.get(arg, arg) for arg in spec["args"]}
    known = table_titles(list(form_names.values()), context=model)

    spelled = {key: f"{name} {symbol} [{unit}]" for key, symbol, name, unit in spec["report"]}
    titles = {arg: known.get(form_names[arg]) or spelled.get(arg, arg) for arg in spec["args"]}
    titles[SITE_COLUMN] = SITE_COLUMN
    titles[MEASURED_COLUMN] = MEASURED_COLUMN
    return titles


def _default_row(model: str, fallback: dict, label: str = "Manual") -> dict:
    row = {SITE_COLUMN: label, MEASURED_COLUMN: None}
    row.update({arg: fallback[arg] for arg in MODEL_SPECS[model]["args"]})
    return row


def site_measured_points(sites, start: int):
    """(x, y) for the measured plume length of each ticked site, numbered from `start`.

    A site contributes a measurement and nothing else. Old CAST never derived
    model parameters from a site - the parameters were always typed or uploaded -
    and this database is the reason why: it carries neither alpha_Tv nor gamma
    for any of its 112 reference sites. Seeding a run from a site therefore meant
    running the model on a fabricated dispersivity, and because Lmax scales as
    M^2/alpha_Tv the fabricated value decided the answer (alpha_Tv=0.001 turned
    Hill AFB's measured 503 m into a modelled 5962 m).
    """
    values = [float(site["plume_length"]) for site in sites
              if site.get("plume_length") not in (None, "")]
    return list(range(start, start + len(values))), values


def run_rows(model: str, frame: pd.DataFrame):
    """(labels, modelled Lmax, measured Lmax) for every row of the table."""
    spec = MODEL_SPECS[model]
    if frame.empty:
        raise ValueError("Add at least one scenario row before running.")
    if len(frame) > MAX_SCENARIOS:
        raise ValueError(f"Too many rows: the limit is {MAX_SCENARIOS} per run (you have {len(frame)}).")

    labels, lengths, measured = [], [], []
    for position, (_index, raw) in enumerate(frame.iterrows(), start=1):
        try:
            values = [float(raw[arg]) for arg in spec["args"]]
        except (TypeError, ValueError, KeyError):
            raise ValueError(f"Row {position} has a missing or non-numeric parameter.")
        labels.append(str(raw.get(SITE_COLUMN) or f"Scenario {position}"))
        lengths.append(float(spec["fn"](*values)))
        value = raw.get(MEASURED_COLUMN)
        measured.append(float(value) if pd.notna(value) else None)
    return labels, lengths, measured


def extra_columns(model: str, frame: pd.DataFrame) -> dict:
    """Result columns beyond Lmax, for a model that produces more than one.

    Empty for every model but Koehler, whose Eq. (14) gives a second number the
    graph has nothing to plot it against - a time in years, next to a length in
    metres. Keyed by column name with one value per row, ready for
    DataFrame.assign, so the table, the exports and the PDF all pick it up
    without a second path through any of them.
    """
    spec = MODEL_SPECS[model]
    extra = spec.get("extra")
    if extra is None or frame.empty:
        return {}
    rows = [extra(*(float(raw[arg]) for arg in spec["args"]))
            for _index, raw in frame.iterrows()]
    return {column: [row[column] for row in rows] for column in rows[0]}


def measured_series(measured):
    """Measured points as (x, y), skipping the rows that carry no measurement."""
    xs = [i for i, value in enumerate(measured, start=1) if value is not None]
    ys = [value for value in measured if value is not None]
    return xs, ys


def _csv_bytes(frame: pd.DataFrame) -> io.BytesIO:
    return io.BytesIO(frame.to_csv(index=False).encode("utf-8"))


def _excel_bytes(frame: pd.DataFrame) -> io.BytesIO:
    buffer = io.BytesIO()
    frame.to_excel(buffer, index=False, sheet_name="Scenarios")
    buffer.seek(0)
    return buffer


def _pdf_bytes(frame: pd.DataFrame, title: str) -> io.BytesIO:
    return io.BytesIO(dataframe_pdf(frame, title))


def read_scenario_frame(data: bytes, params, columns) -> pd.DataFrame:
    """Parse an uploaded scenario CSV against an explicit column list.

    Missing optional columns (Site, Measured) are filled in; a missing *parameter*
    column is an error, because a silent default would be a made-up simulation.

    Model-free so the numerical pages parse their own columns through the same
    reader rather than growing a second one.
    """
    frame = pd.read_csv(io.BytesIO(data))
    frame.columns = [str(c).strip() for c in frame.columns]
    missing = [arg for arg in params if arg not in frame.columns]
    if missing:
        raise ValueError(f"CSV is missing the column(s): {', '.join(missing)}. Download the sample file.")
    if SITE_COLUMN not in frame.columns:
        frame[SITE_COLUMN] = [f"Scenario {i}" for i in range(1, len(frame) + 1)]
    if MEASURED_COLUMN not in frame.columns:
        frame[MEASURED_COLUMN] = None
    return frame[list(columns)]


def read_scenario_csv(model: str, data: bytes) -> pd.DataFrame:
    """Parse an uploaded scenario CSV, keeping only the columns of this model."""
    return read_scenario_frame(data, MODEL_SPECS[model]["args"], scenario_columns(model))


# Old CAST kept the scenario table and its buttons on a card under the graph;
# these hold that shape in the current palette.
_CARD = {
    "background": "#eef1f5", "border": "1px solid #e3e8ef", "border-radius": "10px",
    "padding": "16px 18px", "gap": "10px", "box-shadow": "0 1px 3px rgba(16,24,40,0.07)",
    "position": "relative",
    # Reserves room for the dialog while it is open. Always present, because a
    # style dropped from the dict is not cleared off the element - it lingers,
    # and the card keeps the dialog's height after it closes.
    "min-height": "0",
}
# The site's own button blue (--brand-600 / --brand-700 on hover, what
# .primary-btn uses). Carried by the actions that start something: the sample
# file, the file picker, Upload and Run Scenarios.
#
# Those four ask for it with button_type="primary" rather than a stylesheet of
# their own. A per-widget `stylesheets` REPLACES panel_theme's, so a private
# sheet costs the shared radius, padding and shadow - which is exactly how these
# ended up a different shape from every other button on the card. The file input
# has no button_type, so it still needs a sheet; it repeats the theme's metrics
# so its picker matches.
_BRAND = "#155da9"
_BRAND_DARK = "#114b88"
_BRAND_FILE_CSS = f"""
input[type="file"]::file-selector-button {{
  background: {_BRAND};
  border: 1px solid {_BRAND};
  color: #fff;
  font-weight: 600;
  font-size: 14px;
  border-radius: 8px;
  padding: 9px 16px;
  margin-right: 8px;
  cursor: pointer;
}}
input[type="file"]::file-selector-button:hover {{
  background: {_BRAND_DARK};
  border-color: {_BRAND_DARK};
}}
"""

_SECTION_TITLE = (
    '<div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;'
    'text-transform:uppercase;color:#5b6b7f;border-bottom:2px solid #1f72cd;'
    'display:inline-block;padding-bottom:6px;">%s</div>'
)

# Add row and Delete row as a round + and -, the way the layout sketch draws
# them. COMPONENT_CSS comes first because a per-widget stylesheet REPLACES
# panel_theme's rather than adding to it - drop it and these two lose the
# font, the colour and the hover the rest of the toolbar has.
ROUND_BTN_CSS = """
.bk-btn {
  width: 38px;
  height: 38px;
  min-width: 38px;
  padding: 0;
  border-radius: 50%;
  font-size: 20px;
  line-height: 1;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
"""

# What Add row and Delete row are built with, here and on the numerical pages.
ROUND_BUTTON = {"width": 38, "sizing_mode": "fixed", "button_type": "primary",
                "stylesheets": [COMPONENT_CSS, ROUND_BTN_CSS]}

# The Save Data drop-down. Absolute inside its own wrapper, so it hangs under
# the button that opened it rather than at the end of the toolbar. z-index 30,
# not 20: 20 is what an in-frame Add-row dialog would have claimed, and two
# tests watch for one.
_SAVE_MENU_STYLES = {
    "position": "absolute", "top": "44px", "left": "0", "z-index": "30",
    "background": "#ffffff", "border": "1px solid #d7dfea", "border-radius": "10px",
    "padding": "8px", "gap": "6px",
    "box-shadow": "0 6px 18px rgba(16,24,40,0.16)",
}


def drop_rows(frame: pd.DataFrame, positions) -> pd.DataFrame:
    """`frame` without the rows at these positions, renumbered from zero.

    Positions rather than index labels: Tabulator reports what the user ticked
    by position, and a table that has already lost a row no longer carries an
    index those positions would match.
    """
    unwanted = set(positions or ())
    keep = [i for i in range(len(frame)) if i not in unwanted]
    return frame.iloc[keep].reset_index(drop=True)


def field_specs(titles: dict, defaults: dict) -> list[dict]:
    """[{key, label, value}] per parameter, for a page rendering its own Add-row
    form. Model-free: the numerical pages pass their own titles and defaults."""
    return [{"key": key, "label": titles.get(key, key), "value": value}
            for key, value in defaults.items()]


def scenario_field_specs(model: str) -> list[dict]:
    """field_specs for one of the closed-form models."""
    return field_specs(column_titles(model), dict(MODEL_SPECS[model]["defaults"]))


def sample_scenarios(model: str) -> pd.DataFrame:
    """The shipped reference sites as scenario rows: what Download Sample File
    hands back.

    The table itself starts empty - it fills from an uploaded file or from rows
    added by hand. This is the file to upload if you want somewhere to start.

    Read through reference_sites_rows, the same loader the site database uses, so
    a sample row carries exactly what an uploaded site would and the download
    goes back through the Upload button without editing.

    ponytail: alpha_Tv and gamma come from the model defaults, because no site
    database carries them - not this one, not an uploaded one. A downloaded row
    is therefore a starting point to edit, not an answer: Lmax scales as
    M^2/alpha_Tv, so until those two are replaced it is the default that decides
    the number. Drop the fallback and give them their own columns the day the
    database grows them.
    """
    defaults = MODEL_SPECS[model]["defaults"]
    rows = []
    for site in reference_sites_rows():
        mapped = db_to_model(site, model)
        row = {SITE_COLUMN: site_label(site),
               MEASURED_COLUMN: _optional_float(site.get("plume_length"))}
        for arg in MODEL_SPECS[model]["args"]:
            value = _optional_float(mapped.get(arg))
            row[arg] = defaults[arg] if value is None else value
        rows.append(row)
    return pd.DataFrame(rows, columns=scenario_columns(model))


def printable_table_html(frame: pd.DataFrame, title: str, headings=None) -> str:
    """A standalone document holding the scenario table and nothing else.

    window.print() sends whichever document it is called on, and this one is the
    run button, the graph, its key, two rows of buttons and the table. So Print
    builds this instead and prints it from a frame of its own.
    """
    shown = frame.rename(columns=dict(headings or {}))
    table = shown.to_html(index=False, na_rep="", border=0, justify="left")
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\">"
        f"<title>{_html.escape(title)}</title><style>"
        "body{font:13px/1.45 system-ui,-apple-system,Segoe UI,sans-serif;color:#0b2c4f;"
        "margin:24px;}"
        "h1{font-size:15px;margin:0 0 14px;}"
        "table{border-collapse:collapse;width:100%;}"
        "th,td{border:1px solid #c6d0dc;padding:6px 9px;text-align:left;"
        "white-space:nowrap;}"
        "th{background:#eef1f5;font-weight:600;}"
        "@page{size:landscape;margin:14mm;}"
        "</style></head><body>"
        f"<h1>{_html.escape(title)}</h1>{table}</body></html>"
    )


def _optional_float(value):
    """A number, or None for anything blank or unparseable. A measured plume
    length is optional, and a typo in it must not cost the whole row."""
    text = str(value if value is not None else "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def row_from_payload(data: dict, defaults: dict) -> dict:
    """One table row from what the page's Add-scenario form posted back.

    Parameters missing from the payload fall back to the default rather than
    landing in the table as blanks that only fail later, at run time.
    """
    row = {SITE_COLUMN: str(data.get("name") or "").strip() or "Manual",
           MEASURED_COLUMN: _optional_float(data.get("measured"))}
    for arg, fallback in defaults.items():
        value = _optional_float(data.get(arg))
        row[arg] = fallback if value is None else value
    return row


def scenario_row_from_payload(model: str, data: dict) -> dict:
    """row_from_payload for one of the closed-form models."""
    return row_from_payload(data, dict(MODEL_SPECS[model]["defaults"]))


# The key under the graph: the two places a plotted value can have come from.
# The colours are panel_analytical_common's own constants, the ones the scatter
# draws with, so a swatch cannot drift off the dots it stands for.
def _legend_html(table_label: str = "Scenario table",
                 site_label_text: str = "Selected sites") -> str:
    entries = (
        (MEASURED_COLOR, table_label),
        (SITE_COLOR, site_label_text),
    )
    dots = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:7px;">'
        f'<span style="width:11px;height:11px;border-radius:50%;'
        f'background:{color};flex:0 0 auto;"></span>{text}</span>'
        for color, text in entries
    )
    return ('<div style="display:flex;flex-wrap:wrap;gap:8px 22px;padding:8px 2px 0;'
            'font-size:0.78rem;color:#5b6b7f;">' + dots + "</div>")


# Holds the graph's space before the first run. Same height as plot_pane's
# min_height, so drawing a graph swaps one for the other without the buttons and
# the table under them jumping up the page.
_PLACEHOLDER_HTML = (
    f'<div style="height:{_GRAPH_HEIGHT}px;display:flex;align-items:center;justify-content:center;'
    'border:1px dashed #c6d0dc;border-radius:10px;background:#f7f9fc;color:#5b6b7f;'
    'font-size:0.92rem;text-align:center;padding:0 24px;">'
    'Add a scenario row or tick a site, then press '
    '<strong style="margin:0 4px;">Update Graph</strong>.</div>'
)


# What Print runs in the browser. A frame of its own rather than window.print():
# print sends the whole document it is called on, which here is the graph and
# every control around it. The frame is torn down after the dialog closes.
_PRINT_JS = """
const html = src.value || "";
if (html) {
  const sheet = document.createElement("iframe");
  sheet.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
  document.body.appendChild(sheet);
  const doc = sheet.contentWindow.document;
  doc.open(); doc.write(html); doc.close();
  sheet.contentWindow.focus();
  sheet.contentWindow.print();
  setTimeout(() => sheet.remove(), 1000);
}
"""

# What Add row runs in the browser. The dialog itself belongs to the page: a
# Column pinned inside this document can only ever cover the iframe, and the
# iframe is a band in the middle of the page. So the button asks the page to open
# its own modal and waits for the filled-in row to come back.
#
# The listener is registered once and keeps `bridge` - a real Bokeh model handle
# from args= - alive in its closure. That is what lets an answer arriving later
# still reach Python; nothing here can touch the widget through the DOM, which
# Bokeh keeps inside a shadow root.
_ADD_ROW_JS = """
if (!window.__castRowListener) {
  window.__castRowListener = true;
  window.addEventListener("message", function (e) {
    const d = e.data;
    if (!d || d.type !== "cast-scenario-row") return;
    window.__castRowSeq = (window.__castRowSeq || 0) + 1;
    bridge.value = JSON.stringify(d.row) + "#" + window.__castRowSeq;
  });
}
window.parent.postMessage({type: "cast-scenario-open"}, "*");
"""

def site_picker_widgets(sites, seeded):
    """(picker, search) for the site list that stands beside the graph.

    A MultiSelect rather than the tag-box MultiChoice: this is a real list box,
    so it keeps its scrollbar, and it can be given the stage's height and end
    level with the graph. Shared, because the numerical multiples draw exactly
    the same card.
    """
    options = {site_label(site): int(site["id"]) for site in sites}
    search = pn.widgets.TextInput(placeholder="Search sites...",
                                  sizing_mode="stretch_width")
    picker = pn.widgets.MultiSelect(options=dict(options), value=list(seeded),
                                    sizing_mode="stretch_both")

    def _filter(event):
        """Narrow the list without ever dropping a site already ticked - the
        page's own search box had the same rule."""
        needle = str(event.new or "").strip().lower()
        atm = list(picker.value)
        picker.options = {label: i for label, i in options.items()
                          if needle in label.lower() or i in atm}
        picker.value = atm

    search.param.watch(_filter, "value")
    return picker, search


def save_data_menu(*exports):
    """(button, menu) putting the export widgets behind one Save Data button.

    The menu is a real Panel Column, so every download keeps the callback it
    already had - the button only flips its visibility, through a Bokeh model
    handle rather than the DOM (every widget renders inside a shadow root).
    Shared with the numerical multiples, which carry the same five.
    """
    menu = pn.Column(*exports, width=150, sizing_mode="fixed", visible=False,
                     styles=dict(_SAVE_MENU_STYLES))
    button = pn.widgets.Button(name="Save Data", width=140, sizing_mode="fixed",
                               button_type="primary")
    button.js_on_click(args={"menu": menu}, code="menu.visible = !menu.visible")
    return button, menu


def scenario_layout(*, status, picker, search, run_btn, graph_slot, toolbar,
                    save_btn, save_menu, table, row_buttons, hidden, bridges):
    """The redesigned scenario page: picker beside the graph, one toolbar under
    the two of them, the table below that.

    The whole page is a single Panel document here, which is what makes the
    first row work: the picker is simply built to the stage's height, and there
    is no second layout engine on the other side of an iframe boundary that has
    to be told about it or kept in step with it.
    """
    for button in save_menu:
        button.width = 118              # the menu is narrower than the toolbar

    picker_card = pn.Column(
        pn.pane.HTML(_SECTION_TITLE % "Site data", sizing_mode="stretch_width"),
        search,
        picker,
        height=_STAGE_HEIGHT, sizing_mode="stretch_width",
        # flex-basis 340px with no grow is the old fixed width while the two fit
        # side by side; max-width keeps it inside a frame narrower than that.
        styles={**_CARD, **_PICKER_FLEX},
    )
    # FlexBox, not Row: a Row never wraps, so on a phone the 340px picker and the
    # graph beside it demanded more than the frame had and were clipped at both
    # edges. Wrapped, they sit side by side exactly as before while they fit and
    # stack when they do not - the two min-widths are what decide "do not",
    # because without them the pair would squeeze to unreadable slivers instead.
    # Same shape the single pages already use for their controls/plot split.
    stage = pn.FlexBox(
        picker_card,
        pn.Column(
            pn.Row(run_btn, sizing_mode="stretch_width", height=_RUN_ROW_HEIGHT),
            graph_slot,
            sizing_mode="stretch_width", styles=dict(_GRAPH_FLEX),
        ),
        flex_wrap="wrap", sizing_mode="stretch_width", styles={"gap": "14px"},
    )
    # The wrapper is what position: absolute in the menu resolves against, so
    # the drop-down hangs under Save Data instead of off the end of the toolbar.
    save = pn.Column(save_btn, save_menu, width=150, sizing_mode="fixed",
                     styles={"position": "relative"})
    return pn.Column(
        status,
        stage,
        pn.FlexBox(*toolbar, save, flex_wrap="wrap", align_items="center",
                   sizing_mode="stretch_width", styles={"gap": "8px"}),
        pn.Column(
            pn.pane.HTML(_SECTION_TITLE % "Scenario table", sizing_mode="stretch_width"),
            table,
            pn.FlexBox(*row_buttons, flex_wrap="wrap", align_items="center",
                       justify_content="flex-end", sizing_mode="stretch_width",
                       styles={"gap": "8px"}),
            *hidden,
            sizing_mode="stretch_width", styles=dict(_CARD),
        ),
        *bridges,
        sizing_mode="stretch_width", styles={"gap": "14px"},
    )


def scenario_app(model: str):
    """The multiple-simulation card for `model`.

    The page around it is the single-simulation shell: its sidebar carries the
    site picker where a single page carries its input fields, and its own
    <dialog> collects a new scenario row. This document holds the run button, the
    graph and its key, the export buttons and the scenario table.

    Nothing here reloads the page. The ticked site ids and the filled-in Add-row
    form both arrive by postMessage, because a reload restarts this document and
    throws away every row the user typed - and typed rows and ticked sites have
    to survive together, since one run plots both.
    """
    spec = MODEL_SPECS[model]
    columns = scenario_columns(model)
    titles = column_titles(model)
    email = authenticated_email()
    # The redesigned page keeps its site picker in here, so nothing has to be
    # posted in from the page and the picker can be built to the graph's height.

    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=_GRAPH_HEIGHT)
    placeholder = pn.pane.HTML(_PLACEHOLDER_HTML, sizing_mode="stretch_width", margin=0)
    legend = pn.pane.HTML(_legend_html(), sizing_mode="stretch_width", margin=0)
    # One slot, swapped by replacing its children - never by toggling `visible`.
    # pn.pane.Bokeh keeps the layout properties you set as "overrides" and writes
    # them onto the figure itself the moment .object is assigned; setting
    # visible=True afterwards drops it back out of the overrides, so the value is
    # read straight off the figure it just made invisible (panel/pane/plot.py,
    # _sync_properties). A hidden Bokeh pane can never be shown a second time,
    # and every run drew into a pane nothing could see.
    graph_slot = pn.Column(placeholder, sizing_mode="stretch_width")

    def show_graph(drawn: bool):
        """Put the graph and its key, or the box holding their place, in the slot.

        The key only appears with a graph: two colours explained under an empty
        box are two colours nobody can see."""
        wanted = [plot_pane, legend] if drawn else [placeholder]
        if list(graph_slot) != wanted:
            graph_slot[:] = wanted

    # No result box. It carries errors only - anything else it had to say (row
    # counts, min and max) is already on the table and the graph, and a card
    # standing there permanently just pushed the controls down.
    # Hidden, not merely empty: an empty pane still counts as a child of the
    # Column, so its 14px gap sat between the panel heading and the card as a
    # strip of iframe background - a lighter shade than the card around it.
    status = pn.pane.HTML("", sizing_mode="stretch_width", margin=0, visible=False)

    def show_error(exc):
        status.object = error_card(exc)
        status.visible = True

    def clear_error():
        status.object = ""
        status.visible = False

    report_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")
    # Keeps the page's iframe the height of this document.
    height_bridge = pn.pane.HTML(frame_height_bridge_html(), height=0, margin=0,
                                 sizing_mode="fixed")
    # manual_fallback, not a plain read: a link written with the old CAST field
    # names (?tv=, ?Ca=) still has to land on the right parameters.
    fallback = manual_fallback(model)

    try:
        sites, _invalid = filter_valid_sites_for_model(get_user_sites_rows(email), model)
    except Exception:
        logger.exception("Sites could not be loaded for the %s scenario page", model)
        sites = []
    by_id = {int(site["id"]): site for site in sites}
    # ?compare_sites=1,2 seeds the run, so a shared link opens on its sites.
    seeded = [i for i in sorted(selected_site_ids()) if i in by_id]

    site_picker, site_search = site_picker_widgets(sites, seeded)

    # Where the page writes the row its Add-scenario dialog collected. Hidden and
    # never touched by hand: Add row writes it in the browser through a
    # js_on_click model handle, and the work follows the value into Python.
    row_input = pn.widgets.TextInput(name="cast-scenario-row", value="", visible=False)

    def _picked_sites():
        return [by_id[i] for i in site_picker.value if i in by_id]

    # The table holds the user's own scenarios only; site rows are rebuilt at run
    # time, so ticking a different site never rewrites what was typed in here.
    # No fixed height: an empty table is a header strip, not 220px of blank card.
    #
    # selectable="checkbox": the rows stay editable, and Panel gives every column
    # an editor, so a click on a cell opens that editor instead of selecting the
    # row - table.selection stayed empty and Delete row could only ever answer
    # "select a row first". A checkbox column separates picking a row from typing
    # in it.
    #
    # titles only renames the headers; the stored keys stay canonical. Guarded
    # because it is passed by name: requirements pin panel 1.4.5 while dev runs
    # newer, and a rejected keyword would take the whole page down over headings.
    heading_kwargs = {"titles": titles} if "titles" in pn.widgets.Tabulator.param else {}
    table = pn.widgets.Tabulator(
        pd.DataFrame([], columns=columns), show_index=False, max_height=320,
        layout="fit_columns", sizing_mode="stretch_width", selectable="checkbox",
        name=f"{spec['title']} scenarios", **heading_kwargs,
    )

    # The button sits directly above the graph in the same column, so it
    # stretches to exactly the graph's width.
    run_btn = pn.widgets.Button(name="Update Graph", button_type="primary",
                                sizing_mode="stretch_width")
    # The old CAST toolbar, in its original order. Every one of these stays put
    # and stays enabled for the life of the page: none is hidden until a run has
    # happened.
    # Round + and -, with the caption moved into the tooltip; the wording is
    # the same, so nothing loses its label to a reader who hovers or to a screen
    # reader.
    add_btn = pn.widgets.Button(name="+", description="Add row", **ROUND_BUTTON)
    del_row_btn = pn.widgets.Button(name="−", description="Delete row",
                                    **ROUND_BUTTON)
    # It stands with the round + and -, and the three of them are one row of blue.
    clear_btn = pn.widgets.Button(name="Delete table", width=150,
                                  sizing_mode="fixed", button_type="primary")
    # Fixed, not stretch_width: a stretching file input claimed the whole row and
    # pushed every button after it onto a line of its own.
    upload = pn.widgets.FileInput(accept=".csv", width=230, sizing_mode="fixed",
                                  stylesheets=[_BRAND_FILE_CSS])
    upload_btn = pn.widgets.Button(name="Upload", width=110, sizing_mode="fixed",
                                   button_type="primary")
    results = {"frame": None}

    def _export_frame() -> pd.DataFrame:
        """What the export buttons write: the last run if there is one, else the
        rows as they stand. Never nothing - the buttons work before a run too."""
        if results["frame"] is not None:
            return results["frame"]
        return pd.DataFrame(table.value, columns=columns)

    def _sample_frame() -> pd.DataFrame:
        """The shipped sample, or a one-row template if it cannot be read."""
        try:
            frame = sample_scenarios(model)
        except Exception:
            logger.exception("The scenario sample could not be read for %s", model)
            frame = pd.DataFrame([], columns=columns)
        if frame.empty:
            frame = pd.DataFrame([_default_row(model, spec["defaults"])], columns=columns)
        return frame

    template_btn = pn.widgets.FileDownload(
        callback=lambda: _csv_bytes(_sample_frame()),
        filename=f"{model}_scenarios_sample.csv", label="Download Sample File",
        button_type="primary", width=190, sizing_mode="fixed",
    )
    csv_btn = pn.widgets.FileDownload(
        callback=lambda: _csv_bytes(_export_frame()),
        filename=f"{model}_scenarios.csv", label="CSV",
        button_type="default", width=80, sizing_mode="fixed",
    )
    excel_btn = pn.widgets.FileDownload(
        callback=lambda: _excel_bytes(_export_frame()),
        filename=f"{model}_scenarios.xlsx", label="Excel",
        button_type="default", width=80, sizing_mode="fixed",
    )
    pdf_btn = pn.widgets.FileDownload(
        callback=lambda: _pdf_bytes(_export_frame(), f"{spec['title']} - Scenarios"),
        filename=f"{model}_scenarios.pdf", label="PDF",
        button_type="default", width=80, sizing_mode="fixed",
    )

    # Copy and Print are browser-side. Their payloads are kept on off-screen
    # widgets because the buttons' JS runs in the browser and cannot call back
    # here for them.
    copy_src = pn.widgets.TextAreaInput(value="", visible=False, sizing_mode="fixed", width=0, height=0)
    copy_btn = pn.widgets.Button(name="Copy", width=80, sizing_mode="fixed")
    copy_btn.js_on_click(args={"src": copy_src}, code="""
    const text = src.value || "";
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text);
    } else {
      // Older browsers, and any context the Clipboard API refuses.
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    """)
    print_src = pn.widgets.TextAreaInput(value="", visible=False, sizing_mode="fixed",
                                         width=0, height=0)
    print_btn = pn.widgets.Button(name="Print", width=80, sizing_mode="fixed")
    print_btn.js_on_click(args={"src": print_src}, code=_PRINT_JS)

    save_btn, save_menu = save_data_menu(copy_btn, csv_btn, excel_btn, pdf_btn, print_btn)

    def _row_from_page(event):
        """A row the page's Add-scenario dialog collected and posted back."""
        payload = str(event.new).rpartition("#")[0]
        if not payload:
            return
        try:
            data = json.loads(payload)
        except ValueError:
            logger.warning("Unreadable scenario row from the page: %r", payload)
            return
        current = pd.DataFrame(table.value, columns=columns)
        row = scenario_row_from_payload(model, data)
        table.value = pd.concat([current, pd.DataFrame([row])], ignore_index=True)[columns]
        clear_error()

    def _delete_rows(_=None):
        picked = list(table.selection or ())
        if not picked:
            show_error(ValueError("Select a row first - tick its checkbox in the "
                                  "table, then press Delete row."))
            return
        table.value = drop_rows(pd.DataFrame(table.value, columns=columns), picked)
        table.selection = []
        clear_error()

    def _clear(_=None):
        table.value = pd.DataFrame([], columns=columns)

    def _on_upload(_=None):
        # Wired to the Upload button, not to picking a file: old CAST chose the
        # file first and uploaded on a second, deliberate click.
        if not upload.value:
            show_error(ValueError("Choose a CSV file first, then press Upload."))
            return
        try:
            table.value = read_scenario_csv(model, upload.value)
            clear_error()           # the loaded rows are the feedback
        except Exception as exc:
            logger.exception("Scenario CSV upload failed for %s", model)
            show_error(exc)

    def _run(_=None):
        try:
            frame = pd.DataFrame(table.value, columns=columns)
            picked = _picked_sites()
            if frame.empty and not picked:
                raise ValueError("Nothing to run: add a scenario row, upload a CSV, "
                                 "or pick a site to plot its measured plume length.")

            # The model series is the table, and only the table. Ticked sites add
            # their measured plume length to the right of the last row.
            labels, lengths, measured = run_rows(model, frame) if not frame.empty else ([], [], [])
            row_x, row_y = measured_series(measured)
            site_x, site_y = site_measured_points(picked, len(lengths) + 1)
            plot, plot_data = comparison_plot(
                spec["title"], f"{spec['title']} model plume length",
                list(range(1, len(lengths) + 1)), lengths,
                0, email, "Scenario / Site", return_data=True,
                field_points=(row_x, row_y), site_points=(site_x, site_y),
                field_label="Measured plume length (scenario table)",
                site_series_label="Measured plume length (site database)",
                # The key names the two SOURCES, so everything the scenario table
                # produced - the modelled points included - wears its colour.
                manual_color=MEASURED_COLOR,
            )
            plot_pane.object = plot
            show_graph(True)
            clear_error()           # a drawn graph needs no box to announce it

            extras = extra_columns(model, frame) if lengths else {}
            results["frame"] = (
                frame.assign(**{RESULT_COLUMN: lengths}, **extras) if lengths else None
            )
            if extras:
                # A model with a second output has nowhere else to show it: the
                # graph carries Lmax, and the run's numbers belong on the table
                # anyway. Only the input columns are stored, so every read of
                # table.value elsewhere still narrows back to `columns`.
                table.value = results["frame"]
            _refresh_exports()
            if not lengths:
                # Measured points only. No model ran, but the graph on screen is
                # real, so the report carries what it plots: the measurements.
                measured_only = [(site_label(site), float(site["plume_length"]))
                                 for site in picked
                                 if site.get("plume_length") not in (None, "")]
                if not measured_only:
                    report_bridge.object = report_bridge_html(clear=True)
                    return
                report_bridge.object = report_bridge_html(
                    f"{spec['title']} - Measured Plume Lengths", spec["title"],
                    f"{model}_measured_report.pdf",
                    parameters=[{"symbol": "L_measured", "name": "Measured Plume Length",
                                 "value": value, "unit": "m", "site": label}
                                for label, value in measured_only],
                    outputs=[],
                    # The stock caption compares against a model result there is
                    # none of here.
                    plot_data={**plot_data,
                               "caption": "Measured plume lengths from the site database."},
                )
                return
            report_bridge.object = report_bridge_html(
                f"{spec['title']} - Multiple Simulation", spec["title"],
                f"{model}_multiple_report.pdf",
                # The modelled Lmax rides along as a column of the site table.
                # One metric card per site filled a page on its own, so the
                # report drops the results grid (outputs=[]) and keeps the
                # number where it can be read against its inputs.
                parameters=[
                    entry
                    for position, (label, (_index, row), length)
                    in enumerate(zip(labels, frame.iterrows(), lengths))
                    for entry in (
                        *({"symbol": symbol, "name": name, "value": row[key], "unit": unit,
                           "site": label} for key, symbol, name, unit in spec["report"]),
                        {"symbol": "L_max", "name": "Model Plume Length", "value": length,
                         "unit": "m", "site": label},
                        *({"symbol": symbol, "name": name, "value": extras[column][position],
                           "unit": unit, "site": label}
                          for column, symbol, name, unit in spec.get("extra_report", ())),
                    )
                ],
                outputs=[],
                plot_data=plot_data,
            )
        except Exception as exc:
            logger.exception("%s scenario run failed", model)
            show_error(exc)
            plot_pane.object = None
            show_graph(False)
            report_bridge.object = report_bridge_html(clear=True)

    def _refresh_exports(*_events):
        """Keep the Copy and Print payloads in step with what is on screen."""
        frame = _export_frame()
        copy_src.value = frame.to_csv(index=False)
        print_src.value = printable_table_html(
            frame, f"{spec['title']} - Scenario table", titles)

    # Add row asks the PAGE to open its dialog and waits for the row to come
    # back: a dialog built in here can only cover the iframe.
    add_btn.js_on_click(args={"bridge": row_input}, code=_ADD_ROW_JS)
    row_input.param.watch(_row_from_page, "value")
    # The picker is a widget in this document, so the run is a plain Python
    # click: there are no ids to fetch from the page and no bridge to race.
    run_btn.on_click(_run)
    del_row_btn.on_click(_delete_rows)
    clear_btn.on_click(_clear)
    upload_btn.on_click(_on_upload)
    table.param.watch(_refresh_exports, "value")
    # A cell edited in place mutates table.value without rebinding it, so the
    # watcher above never fires and the payloads would go stale.
    table.on_edit(_refresh_exports)
    _refresh_exports()

    if seeded:
        # Sites arrived in the page URL (a shared link): draw them straight away
        # rather than opening on an empty graph.
        _run()

    return scenario_layout(
        status=status, picker=site_picker, search=site_search, run_btn=run_btn,
        graph_slot=graph_slot, toolbar=(template_btn, upload, upload_btn),
        save_btn=save_btn, save_menu=save_menu, table=table,
        row_buttons=(add_btn, del_row_btn, clear_btn),
        hidden=(copy_src, print_src, row_input),
        bridges=(report_bridge, height_bridge),
    )
