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

import io
import logging

import pandas as pd
import panel as pn

from data_queries import get_user_sites_rows
from model_site_validation import filter_valid_sites_for_model
from panel_analytical_common import comparison_plot, error_card
from panel_auth import authenticated_email
from panel_site_comparison import (
    FORM_ALIASES, MODEL_SPECS, manual_fallback, selected_site_ids, site_label,
)
from param_meta import table_titles
from panel_theme import frame_height_bridge_html, report_bridge_html
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


def read_scenario_csv(model: str, data: bytes) -> pd.DataFrame:
    """Parse an uploaded scenario CSV, keeping only the columns of this model.

    Missing optional columns (Site, Measured) are filled in; a missing *parameter*
    column is an error, because a silent default would be a made-up simulation.
    """
    frame = pd.read_csv(io.BytesIO(data))
    frame.columns = [str(c).strip() for c in frame.columns]
    missing = [arg for arg in MODEL_SPECS[model]["args"] if arg not in frame.columns]
    if missing:
        raise ValueError(f"CSV is missing the column(s): {', '.join(missing)}. Download the template.")
    if SITE_COLUMN not in frame.columns:
        frame[SITE_COLUMN] = [f"Scenario {i}" for i in range(1, len(frame) + 1)]
    if MEASURED_COLUMN not in frame.columns:
        frame[MEASURED_COLUMN] = None
    return frame[scenario_columns(model)]


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


def site_options(sites) -> dict:
    """{label: id} for the picker, with duplicate site units kept apart.

    Two sites can carry the same unit name; collapsing them into one option
    would silently drop a site from the list.
    """
    options, seen = {}, {}
    for site in sites:
        label = site_label(site)
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = f"{label} (#{site.get('display_id') or site['id']})"
        options[label] = int(site["id"])
    return options


def visible_options(options: dict, query: str, picked) -> dict:
    """Options matching `query`, plus whatever is already picked.

    Filtering must never unpick a site: the picked ids are the run, and an
    option that disappears takes its selection with it.
    """
    text = (query or "").strip().lower()
    chosen = set(picked or ())
    return {label: value for label, value in options.items()
            if not text or text in label.lower() or value in chosen}


def scenario_app(model: str):
    spec = MODEL_SPECS[model]
    columns = scenario_columns(model)
    titles = column_titles(model)
    email = authenticated_email()

    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
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
    # Keeps the page's iframe the height of this document - the graph sits at
    # the bottom, so a frame that cannot grow cuts it off entirely.
    height_bridge = pn.pane.HTML(frame_height_bridge_html(), height=0, margin=0,
                                 sizing_mode="fixed")

    # manual_fallback, not a plain read: a link written with the old CAST field
    # names (?tv=, ?Ca=) still has to land on the right parameters.
    fallback = manual_fallback(model)

    # The site list lives on this card, not on the page: the page has no sidebar
    # any more, and a picker in here can run without a reload throwing away the
    # rows typed into the table.
    try:
        sites, _invalid = filter_valid_sites_for_model(get_user_sites_rows(email), model)
    except Exception:
        logger.exception("Sites could not be loaded for the %s scenario page", model)
        sites = []
    by_id = {int(site["id"]): site for site in sites}
    all_options = site_options(sites)
    # ?compare_sites=1,2 still seeds the picker, so a shared link opens on its run.
    seeded = [i for i in sorted(selected_site_ids()) if i in by_id]

    def _picked_sites():
        return [by_id[i] for i in site_select.value if i in by_id]

    # The table holds the user's own scenarios only; site rows are rebuilt at run
    # time, so ticking a different site never rewrites what was typed in here.
    # No fixed height: an empty table is a header strip, not 220px of blank card.
    # It grows with the rows and starts scrolling at max_height.
    # titles only renames the headers; the stored keys stay canonical. Guarded
    # because it is passed by name: requirements pin panel 1.4.5 while dev runs
    # newer, and a rejected keyword would take the whole page down over headings.
    heading_kwargs = {"titles": titles} if "titles" in pn.widgets.Tabulator.param else {}
    table = pn.widgets.Tabulator(
        pd.DataFrame([], columns=columns), show_index=False, max_height=320,
        layout="fit_columns", sizing_mode="stretch_width",
        name=f"{spec['title']} scenarios", **heading_kwargs,
    )

    site_search = pn.widgets.TextInput(placeholder="Search sites…", sizing_mode="stretch_width")
    site_select = pn.widgets.MultiSelect(
        options=dict(all_options), value=seeded, size=8, sizing_mode="stretch_width",
    )
    run_btn = pn.widgets.Button(name="Run Scenarios", width=160, sizing_mode="fixed",
                                button_type="primary")

    # The old CAST toolbar, in its original order and wording. Every one of these
    # stays put and stays enabled for the life of the page: they sit above the
    # site list so a finished run growing the document cannot push them out of
    # sight, and none of them is hidden until a run has happened.
    add_btn = pn.widgets.Button(name="Add Data", width=130, sizing_mode="fixed")
    clear_btn = pn.widgets.Button(name="Delete table data", width=150, sizing_mode="fixed")
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

    template_btn = pn.widgets.FileDownload(
        callback=lambda: _csv_bytes(pd.DataFrame([_default_row(model, spec["defaults"])], columns=columns)),
        filename=f"{model}_scenarios_template.csv", label="Download Sample File",
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

    # Copy and Print are browser-side. The clipboard text is kept on an off-screen
    # widget because the button's JS runs in the browser and cannot call back here.
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
    print_btn = pn.widgets.Button(name="Print", width=80, sizing_mode="fixed")
    print_btn.js_on_click(code="window.print()")

    # --- "Add row" dialog -----------------------------------------------------
    # A Column pinned over the card rather than pn.Modal: Modal needs Panel >= 1.5
    # (requirements pin 1.4.5), and a card pinned to the section opens next to the
    # button that summoned it - which a viewport-centred dialog cannot do inside
    # an iframe the page has stretched to its full content height.
    name_input = pn.widgets.TextInput(name="Scenario name", value="Manual")
    # Fixed width so the parameters wrap two-abreast: stretched inputs stack into
    # one tall column, and a dialog taller than the card it sits on gets clipped.
    param_inputs = {
        arg: pn.widgets.FloatInput(name=titles[arg], value=float(fallback[arg]), step=0.01,
                                   width=250, sizing_mode="fixed")
        for arg in spec["args"]
    }
    measured_input = pn.widgets.TextInput(
        name=MEASURED_COLUMN, value="", placeholder="optional - measured plume length",
    )
    confirm_btn = pn.widgets.Button(name="Add scenario", button_type="primary", width=140, sizing_mode="fixed")
    cancel_btn = pn.widgets.Button(name="Cancel", width=100, sizing_mode="fixed")

    dialog = pn.Column(
        pn.Column(
            pn.pane.HTML(_SECTION_TITLE % "Add scenario", sizing_mode="stretch_width"),
            name_input,
            pn.FlexBox(*param_inputs.values(), flex_wrap="wrap", styles={"gap": "6px 16px"}),
            measured_input,
            pn.Row(confirm_btn, cancel_btn, styles={"gap": "8px"}),
            sizing_mode="stretch_width",
            styles={"background": "#ffffff", "border": "1px solid #e3e8ef",
                    "border-radius": "10px", "padding": "18px 20px", "gap": "10px",
                    "box-shadow": "0 10px 30px rgba(16,24,40,0.18)", "max-width": "620px"},
        ),
        visible=False,
        sizing_mode="stretch_width",
        styles={"position": "absolute", "inset": "0", "z-index": "20",
                "background": "rgba(11,44,79,0.35)", "border-radius": "10px",
                "padding": "18px", "align-items": "center", "justify-content": "flex-start"},
    )

    # The dialog is absolutely positioned, so it adds no height of its own: the
    # card has to make room for it or the buttons fall outside the iframe.
    def _open_dialog(_=None):
        scenario_card.styles = {**_CARD, "min-height": "540px"}
        dialog.visible = True

    def _close_dialog(_=None):
        dialog.visible = False
        scenario_card.styles = {**_CARD, "min-height": "0"}

    def _confirm(_=None):
        measured = measured_input.value.strip()
        row = {SITE_COLUMN: name_input.value.strip() or "Manual",
               MEASURED_COLUMN: float(measured) if measured else None}
        row.update({arg: widget.value for arg, widget in param_inputs.items()})
        current = pd.DataFrame(table.value, columns=columns)
        table.value = pd.concat([current, pd.DataFrame([row])], ignore_index=True)[columns]
        _close_dialog()
        clear_error()               # the new row in the table is the feedback

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
                raise ValueError("Nothing to run: add a scenario row, or pick a site "
                                 "to plot its measured plume length.")

            # The model series is the table, and only the table. Ticked sites add
            # their measured plume length to the right of the last row.
            labels, lengths, measured = run_rows(model, frame) if not frame.empty else ([], [], [])
            row_x, row_y = measured_series(measured)
            site_x, site_y = site_measured_points(picked, len(lengths) + 1)
            plot, plot_data = comparison_plot(
                spec["title"], f"{spec['title']} model plume length",
                list(range(1, len(lengths) + 1)), lengths,
                0, email, "Scenario / Site", return_data=True,
                field_points=(row_x + site_x, row_y + site_y),
                field_label="Measured plume length",
            )
            plot_pane.object = plot
            clear_error()           # a drawn graph needs no box to announce it

            results["frame"] = frame.assign(**{RESULT_COLUMN: lengths}) if lengths else None
            _refresh_clipboard()
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
                    for label, (_index, row), length in zip(labels, frame.iterrows(), lengths)
                    for entry in (
                        *({"symbol": symbol, "name": name, "value": row[key], "unit": unit,
                           "site": label} for key, symbol, name, unit in spec["report"]),
                        {"symbol": "L_max", "name": "Model Plume Length", "value": length,
                         "unit": "m", "site": label},
                    )
                ],
                outputs=[],
                plot_data=plot_data,
            )
        except Exception as exc:
            logger.exception("%s scenario run failed", model)
            show_error(exc)
            plot_pane.object = None
            report_bridge.object = report_bridge_html(clear=True)

    def _filter_sites(event):
        site_select.options = visible_options(all_options, event.new, site_select.value)

    def _refresh_clipboard(*_events):
        """Keep the Copy button's payload in step with what is on screen."""
        copy_src.value = _export_frame().to_csv(index=False)

    add_btn.on_click(_open_dialog)
    cancel_btn.on_click(_close_dialog)
    confirm_btn.on_click(_confirm)
    clear_btn.on_click(_clear)
    run_btn.on_click(_run)
    upload_btn.on_click(_on_upload)
    site_search.param.watch(_filter_sites, "value")
    table.param.watch(_refresh_clipboard, "value")
    _refresh_clipboard()

    if seeded:
        # Sites arrived in the page URL (a shared link): draw them straight away
        # rather than opening on an empty graph.
        _run()

    sites_note = ("Ctrl/Cmd-click to pick several. A picked site plots its measured "
                  "plume length only - the model runs on the scenario table below, "
                  "because the database carries no dispersivity or stoichiometry. "
                  "Filtering does not clear what is already picked.")
    scenario_card = pn.Column(
        # One wrapping row rather than four fixed ones: stacked rows left a band
        # of empty card beside each short row. FlexBox wraps only when the width
        # actually runs out. It stays at the top of the card, ahead of the site
        # list, so it holds its place whether or not a graph has been drawn.
        pn.FlexBox(template_btn, upload, upload_btn, clear_btn, add_btn,
                   copy_btn, csv_btn, excel_btn, pdf_btn, print_btn,
                   flex_wrap="wrap", align_items="center",
                   sizing_mode="stretch_width", styles={"gap": "8px"}),

        pn.pane.HTML(_SECTION_TITLE % "Sites", sizing_mode="stretch_width"),
        site_search,
        site_select,
        pn.pane.HTML(f'<span style="font-size:0.78rem;color:#5b6b7f;">{sites_note}</span>',
                     sizing_mode="stretch_width"),
        pn.pane.HTML(_SECTION_TITLE % "Scenario table", sizing_mode="stretch_width"),
        table,
        pn.Row(run_btn, sizing_mode="stretch_width", styles={"padding-top": "4px"}),
        copy_src,
        dialog,
        sizing_mode="stretch_width",
        styles=dict(_CARD),
    )

    # Inputs first, graph underneath: the graph is the output of everything on
    # the card, and putting it last means drawing one never moves the controls.
    #
    # stretch_width, not stretch_both: the page grows the iframe to fit this
    # document, so a height that tries to fill the frame instead of the content
    # leaves the buttons under the fold.
    return pn.Column(
        status,
        scenario_card,
        plot_pane,
        report_bridge,
        height_bridge,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
