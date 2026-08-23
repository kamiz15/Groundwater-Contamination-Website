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
import json
import logging

import pandas as pd
import panel as pn

from data_queries import get_user_sites_rows
from model_site_validation import filter_valid_sites_for_model
from panel_analytical_common import comparison_plot, error_card, info_card, query_float, summary_card
from panel_auth import authenticated_email
from panel_site_comparison import MODEL_SPECS, selected_site_ids, site_label
from panel_theme import report_bridge_html
from symbol_registry import db_to_model

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


def _default_row(model: str, fallback: dict, label: str = "Manual") -> dict:
    row = {SITE_COLUMN: label, MEASURED_COLUMN: None}
    row.update({arg: fallback[arg] for arg in MODEL_SPECS[model]["args"]})
    return row


def seed_rows(model: str, sites, fallback: dict) -> list[dict]:
    """One row per site, its NULL columns filled from `fallback`.

    No sites picked still gives one row, so the page opens on something runnable
    instead of an empty grid.
    """
    rows = []
    for site in sites:
        row = _default_row(model, fallback, label=site_label(site))
        row.update({k: float(v) for k, v in db_to_model(site, model).items()
                    if k in MODEL_SPECS[model]["args"]})
        measured = site.get("plume_length")
        row[MEASURED_COLUMN] = float(measured) if measured not in (None, "") else None
        rows.append(row)
    return rows or [_default_row(model, fallback)]


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


# The parent page owns the site list (and its search box), so the single "Run
# Scenarios" button lives out there. It cannot submit the form - a reload would
# throw away the rows typed in here - so it posts the ticked ids into this
# document instead. The listener writes them onto an off-screen TextInput, and
# the value arriving over the websocket is what starts the run, so there is no
# race between a click and a value that is still in flight.
#
# Bokeh renders every widget inside a shadow root, so the search has to walk into
# each shadowRoot rather than use a plain querySelectorAll.
_RUN_LISTENER_HTML = """
<img src="data:," style="display:none" alt="" onerror='
if (!window.__castScenarioListener__MODEL__) {
  window.__castScenarioListener__MODEL__ = true;
  window.addEventListener("message", function(event) {
    var data = event.data;
    if (!data || data.type !== "run-scenarios" || data.model !== "__MODEL__") return;
    var stack = [document];
    while (stack.length) {
      var root = stack.pop();
      var host = root.querySelector && root.querySelector(".cast-scenario-trigger");
      // css_classes land on the host div; the <input> itself is one shadow root
      // further in, which a plain descendant selector cannot reach.
      var hit = host && host.shadowRoot && host.shadowRoot.querySelector("input");
      if (hit) {
        window.__castScenarioSeq = (window.__castScenarioSeq || 0) + 1;
        hit.value = JSON.stringify({ids: data.site_ids || [], seq: window.__castScenarioSeq});
        hit.dispatchEvent(new Event("input", {bubbles: true}));
        hit.dispatchEvent(new Event("change", {bubbles: true}));
        return;
      }
      var nodes = root.querySelectorAll("*");
      for (var i = 0; i < nodes.length; i++) {
        if (nodes[i].shadowRoot) stack.push(nodes[i].shadowRoot);
      }
    }
  });
}
'>
"""

_OFF_SCREEN = {
    "position": "absolute", "left": "-9999px", "width": "1px", "height": "1px",
    "overflow": "hidden", "opacity": "0",
}

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
_SECTION_TITLE = (
    '<div style="font-size:0.78rem;font-weight:700;letter-spacing:0.08em;'
    'text-transform:uppercase;color:#5b6b7f;border-bottom:2px solid #1f72cd;'
    'display:inline-block;padding-bottom:6px;">%s</div>'
)


def parse_trigger(raw: str):
    """Site ids posted by the page. Anything malformed means no sites."""
    try:
        return [int(i) for i in json.loads(raw).get("ids", [])]
    except (TypeError, ValueError, AttributeError):
        return []


def scenario_app(model: str):
    spec = MODEL_SPECS[model]
    columns = scenario_columns(model)
    email = authenticated_email()

    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    status = pn.pane.HTML(
        info_card("Tick sites on the left, or add scenarios below, then press Run Scenarios."),
        sizing_mode="stretch_width", margin=0,
    )
    report_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")

    fallback = {key: query_float(key, value) for key, value in spec["defaults"].items()}
    # Ticked sites are resolved fresh on every run, so re-ticking needs no reload.
    picked = {"ids": sorted(selected_site_ids())}

    def _picked_sites():
        if not picked["ids"]:
            return []
        try:
            sites, _invalid = filter_valid_sites_for_model(get_user_sites_rows(email), model)
        except Exception:
            logger.exception("Sites could not be loaded for the %s scenario run", model)
            return []
        wanted = set(picked["ids"])
        return [site for site in sites if int(site["id"]) in wanted]

    # The table holds the user's own scenarios only; site rows are rebuilt at run
    # time, so ticking a different site never rewrites what was typed in here.
    table = pn.widgets.Tabulator(
        pd.DataFrame([], columns=columns), show_index=False, height=220,
        layout="fit_columns", sizing_mode="stretch_width",
        name=f"{spec['title']} scenarios",
    )

    add_btn = pn.widgets.Button(name="+ Add row", width=120, sizing_mode="fixed")
    clear_btn = pn.widgets.Button(name="Clear rows", width=120, sizing_mode="fixed")
    upload = pn.widgets.FileInput(accept=".csv", sizing_mode="stretch_width")
    trigger = pn.widgets.TextInput(value="", css_classes=["cast-scenario-trigger"],
                                   styles=_OFF_SCREEN, sizing_mode="fixed", width=1)
    run_listener = pn.pane.HTML(_RUN_LISTENER_HTML.replace("__MODEL__", model),
                                height=0, margin=0, sizing_mode="fixed")
    results = {"frame": None}

    template_btn = pn.widgets.FileDownload(
        callback=lambda: _csv_bytes(pd.DataFrame([_default_row(model, spec["defaults"])], columns=columns)),
        filename=f"{model}_scenarios_template.csv", label="↓ CSV template",
        button_type="default", width=150, sizing_mode="fixed",
    )
    results_btn = pn.widgets.FileDownload(
        callback=lambda: _csv_bytes(results["frame"] if results["frame"] is not None else pd.DataFrame()),
        filename=f"{model}_scenario_results.csv", label="↓ Results CSV",
        button_type="default", width=150, sizing_mode="fixed", visible=False,
    )

    # --- "Add row" dialog -----------------------------------------------------
    # A Column pinned over the card rather than pn.Modal: Modal needs Panel >= 1.5
    # (requirements pin 1.4.5), and a card pinned to the section opens next to the
    # button that summoned it - which a viewport-centred dialog cannot do inside
    # an iframe the page has stretched to its full content height.
    name_input = pn.widgets.TextInput(name="Scenario name", value="Manual")
    # Fixed width so the parameters wrap two-abreast: stretched inputs stack into
    # one tall column, and a dialog taller than the card it sits on gets clipped.
    param_inputs = {
        arg: pn.widgets.FloatInput(name=arg, value=float(fallback[arg]), step=0.01,
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
        status.object = info_card(
            f"{len(table.value)} scenario row(s) ready. Press Run Scenarios to compute them."
        )

    def _clear(_=None):
        table.value = pd.DataFrame([], columns=columns)

    def _on_upload(_=None):
        if not upload.value:
            return
        try:
            table.value = read_scenario_csv(model, upload.value)
            status.object = info_card(
                f"Loaded {len(table.value)} row(s) from {upload.filename}. Press Run Scenarios."
            )
        except Exception as exc:
            logger.exception("Scenario CSV upload failed for %s", model)
            status.object = error_card(exc)

    def _run(_=None):
        try:
            site_rows = seed_rows(model, _picked_sites(), fallback) if picked["ids"] else []
            manual = pd.DataFrame(table.value, columns=columns)
            frame = pd.concat([pd.DataFrame(site_rows, columns=columns), manual], ignore_index=True)
            if frame.empty:
                raise ValueError("Nothing to run: tick a site on the left, or add a scenario row.")

            labels, lengths, measured = run_rows(model, frame)
            plot, plot_data = comparison_plot(
                spec["title"], f"{spec['title']} model plume length",
                list(range(1, len(lengths) + 1)), lengths,
                0, email, "Scenario", return_data=True,
                field_points=measured_series(measured),
                field_label="Measured plume length",
            )
            plot_pane.object = plot
            status.object = summary_card(
                [("Runs", str(len(lengths))),
                 ("Sites", str(len(site_rows))),
                 ("Manual rows", str(len(manual))),
                 ("Max Lmax", f"{max(lengths):.2f} m"),
                 ("Min Lmax", f"{min(lengths):.2f} m")],
                title=f"{spec['title']} - {len(lengths)} scenario(s)",
            )

            results["frame"] = frame.assign(**{RESULT_COLUMN: lengths})
            results_btn.visible = True
            report_bridge.object = report_bridge_html(
                f"{spec['title']} - Multiple Simulation", spec["title"],
                f"{model}_multiple_report.pdf",
                parameters=[
                    {"symbol": symbol, "name": name, "value": row[key], "unit": unit, "site": label}
                    for label, (_index, row) in zip(labels, frame.iterrows())
                    for key, symbol, name, unit in spec["report"]
                ],
                outputs=[{"label": f"{label} Lmax", "value": f"{value:.2f}", "unit": "m"}
                         for label, value in zip(labels, lengths)],
                plot_data=plot_data,
            )
        except Exception as exc:
            logger.exception("%s scenario run failed", model)
            status.object = error_card(exc)
            plot_pane.object = None
            results_btn.visible = False
            report_bridge.object = report_bridge_html(clear=True)

    def _on_trigger(event):
        picked["ids"] = parse_trigger(event.new)
        _run()

    add_btn.on_click(_open_dialog)
    cancel_btn.on_click(_close_dialog)
    confirm_btn.on_click(_confirm)
    clear_btn.on_click(_clear)
    upload.param.watch(_on_upload, "value")
    trigger.param.watch(_on_trigger, "value")

    if picked["ids"]:
        # Sites arrived in the page URL (a Load Site submit, or a shared link):
        # draw them straight away rather than opening on an empty graph.
        _run()

    scenario_card = pn.Column(
        pn.pane.HTML(_SECTION_TITLE % "Scenario table", sizing_mode="stretch_width"),
        table,
        pn.Row(add_btn, clear_btn, template_btn, results_btn,
               sizing_mode="stretch_width", styles={"gap": "8px", "flex-wrap": "wrap"}),
        pn.Row(pn.pane.HTML('<span style="font-size:0.85rem;color:#5b6b7f;font-weight:600;">'
                            'Upload scenarios (CSV)</span>', sizing_mode="fixed", width=190),
               upload, sizing_mode="stretch_width",
               styles={"align-items": "center", "gap": "8px"}),
        dialog,
        sizing_mode="stretch_width",
        styles=dict(_CARD),
    )

    # stretch_width, not stretch_both: the page grows the iframe to fit this
    # document, so a height that tries to fill the frame instead of the content
    # leaves the buttons under the fold.
    return pn.Column(
        status,
        plot_pane,
        scenario_card,
        trigger,
        run_listener,
        report_bridge,
        sizing_mode="stretch_width",
        styles={"gap": "14px"},
    )
