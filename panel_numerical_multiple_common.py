"""Shared engine for the horizontal/vertical numerical multiple panels.

Same page as the analytical and hybrid multiples (panel_model_scenarios): the
run button and the graph on top, the export buttons under it, and the scenario
table at the bottom. The site picker and the Add-row dialog belong to the page
around this document, and reach it over the postMessage bridges, so nothing
here reloads and typed rows survive a change of sites.

Every primitive - the toolbar JS, the placeholder, the key, the CSV reader, the
printable table - is imported from panel_model_scenarios rather than copied, so
the two page families cannot drift apart.

What is genuinely different, and why this is not just scenario_app:

  * a row is a full MODFLOW/MT3DMS job, not a closed-form call, so the run
    submits and then polls instead of returning a number;
  * MAX_MULTIPLE_RUNS caps a comparison at a handful of rows rather than 200;
  * the vertical orientation checks feasibility before it queues anything.

The two orientation modules are identical except for wording, scenario columns,
job kind and that check, so the panel lives here once. Each passes itself
(``sys.modules[__name__]``) and the engine resolves every dependency through
that module's namespace - tests monkeypatch ``submit_job``, ``job_status``,
``fetch_result``, ``authenticated_email`` and ``get_user_sites_rows`` on the
orientation modules, and late ``mod.*`` lookups keep those seams working.

Required module attributes: ORIENTATION, TITLE, JOB_KIND, SCENARIO_COLUMNS,
COLUMN_TITLES, DEFAULT_ROW, SITE_ROW. Optional: VALIDATE_ROWS(rows).
"""

import json
import logging

import pandas as pd
import panel as pn

from data_queries import reference_sites_rows
from numerical_input_validation import user_instruction
from panel_analytical_common import (
    MEASURED_COLOR, comparison_plot, error_card, summary_card,
)
from panel_model_scenarios import (
    MEASURED_COLUMN, ROUND_BUTTON, SITE_COLUMN, _ADD_ROW_JS, _BRAND_FILE_CSS,
    _CARD, _PLACEHOLDER_HTML, _PRINT_JS, _SECTION_TITLE, _csv_bytes,
    _excel_bytes, _legend_html, _optional_float, _pdf_bytes, drop_rows,
    field_specs, measured_series, printable_table_html, read_scenario_frame,
    row_from_payload, save_data_menu, scenario_layout, site_measured_points,
    site_picker_widgets,
)
from panel_theme import frame_height_bridge_html, report_bridge_html

pn.extension("tabulator", sizing_mode="stretch_width")

logger = logging.getLogger(__name__)

# Each row triggers a full MODFLOW run, so cap how many a single comparison can
# queue to keep one user from flooding the job worker.
MAX_MULTIPLE_RUNS = 12


def scenario_columns(mod) -> list[str]:
    return [SITE_COLUMN, *mod.SCENARIO_COLUMNS, MEASURED_COLUMN]


def numerical_field_specs(mod) -> list[dict]:
    """What the page's Add-row dialog renders for this orientation."""
    return field_specs(mod.COLUMN_TITLES, dict(mod.DEFAULT_ROW))


def sample_scenarios(mod) -> pd.DataFrame:
    """The shipped reference sites as scenario rows: what Download Sample File
    hands back, mapped through the orientation's own SITE_ROW.

    The full dataset, the same as every other model's sample. It is longer than
    MAX_MULTIPLE_RUNS on purpose - the file is a starting point to cut down, and
    the run says plainly how many rows it will take.
    """
    columns = scenario_columns(mod)
    rows = []
    for site in reference_sites_rows():
        row, _ready, _status = mod.SITE_ROW(site)
        rows.append({
            SITE_COLUMN: site.get("site_unit") or f"Site {site.get('display_id') or site.get('id')}",
            MEASURED_COLUMN: _optional_float(site.get("plume_length")),
            **row,
        })
    return pd.DataFrame(rows, columns=columns)


def numerical_multiple_app(mod):
    orientation = mod.ORIENTATION
    word = orientation.capitalize()
    columns = scenario_columns(mod)
    params = list(mod.SCENARIO_COLUMNS)

    plot_pane = pn.pane.Bokeh(sizing_mode="stretch_width", min_height=420)
    placeholder = pn.pane.HTML(_PLACEHOLDER_HTML, sizing_mode="stretch_width", margin=0)
    legend = pn.pane.HTML(_legend_html(), sizing_mode="stretch_width", margin=0)
    # One slot, swapped by replacing its children - never by toggling `visible`.
    # See panel_model_scenarios: a hidden pn.pane.Bokeh can never be shown again.
    graph_slot = pn.Column(placeholder, sizing_mode="stretch_width")

    def show_graph(drawn: bool):
        wanted = [plot_pane, legend] if drawn else [placeholder]
        if list(graph_slot) != wanted:
            graph_slot[:] = wanted

    status = pn.pane.HTML("", sizing_mode="stretch_width", margin=0, visible=False)

    def show_status(html):
        status.object = html
        status.visible = True

    def show_error(exc):
        show_status(error_card(user_instruction(exc)))

    def clear_error():
        status.object = ""
        status.visible = False

    report_bridge = pn.pane.HTML("", height=0, margin=0, sizing_mode="fixed")
    height_bridge = pn.pane.HTML(frame_height_bridge_html(), height=0, margin=0,
                                 sizing_mode="fixed")
    try:
        email = mod.authenticated_email()
        sites = mod.get_user_sites_rows(email) if email else []
    except Exception:
        logger.exception("Sites could not be loaded for the %s numerical page", orientation)
        sites = []
    by_id = {int(site["id"]): site for site in sites}
    seeded = [i for i in sorted(mod.selected_site_ids()) if i in by_id]

    site_picker, site_search = site_picker_widgets(sites, seeded)
    row_input = pn.widgets.TextInput(name="cast-scenario-row", value="", visible=False)

    def _picked_sites():
        return [by_id[i] for i in site_picker.value if i in by_id]

    heading_kwargs = ({"titles": dict(mod.COLUMN_TITLES)}
                      if "titles" in pn.widgets.Tabulator.param else {})
    table = pn.widgets.Tabulator(
        pd.DataFrame([], columns=columns), show_index=False, max_height=320,
        layout="fit_columns", sizing_mode="stretch_width", selectable="checkbox",
        name=f"{word} numerical scenarios", **heading_kwargs,
    )

    # Same three shapes as the analytical multiples: the run button spans the
    # graph under it, and the row buttons are a round + and - carrying their
    # wording in the tooltip.
    run_btn = pn.widgets.Button(name="Update Graph", button_type="primary",
                                sizing_mode="stretch_width")
    add_btn = pn.widgets.Button(name="+", description="Add row", **ROUND_BUTTON)
    del_row_btn = pn.widgets.Button(name="−", description="Delete row",
                                    **ROUND_BUTTON)
    clear_btn = pn.widgets.Button(name="Delete table", width=150,
                                  sizing_mode="fixed", button_type="primary")
    upload = pn.widgets.FileInput(accept=".csv", width=230, sizing_mode="fixed",
                                  stylesheets=[_BRAND_FILE_CSS])
    upload_btn = pn.widgets.Button(name="Upload", width=110, sizing_mode="fixed",
                                   button_type="primary")

    results = {"frame": None}
    state = {}
    poller = {"callback": None}

    def _export_frame() -> pd.DataFrame:
        if results["frame"] is not None:
            return results["frame"]
        return pd.DataFrame(table.value, columns=columns)

    def _sample_frame() -> pd.DataFrame:
        try:
            frame = sample_scenarios(mod)
        except Exception:
            logger.exception("The scenario sample could not be read for %s", orientation)
            frame = pd.DataFrame([], columns=columns)
        if frame.empty:
            frame = pd.DataFrame(
                [{SITE_COLUMN: "Manual", MEASURED_COLUMN: None, **dict(mod.DEFAULT_ROW)}],
                columns=columns)
        return frame

    template_btn = pn.widgets.FileDownload(
        callback=lambda: _csv_bytes(_sample_frame()),
        filename=f"numerical_{orientation}_scenarios_sample.csv",
        label="Download Sample File", button_type="primary", width=190,
        sizing_mode="fixed",
    )
    csv_btn = pn.widgets.FileDownload(
        callback=lambda: _csv_bytes(_export_frame()),
        filename=f"numerical_{orientation}_scenarios.csv", label="CSV",
        button_type="default", width=80, sizing_mode="fixed",
    )
    excel_btn = pn.widgets.FileDownload(
        callback=lambda: _excel_bytes(_export_frame()),
        filename=f"numerical_{orientation}_scenarios.xlsx", label="Excel",
        button_type="default", width=80, sizing_mode="fixed",
    )
    pdf_btn = pn.widgets.FileDownload(
        callback=lambda: _pdf_bytes(_export_frame(), f"{mod.TITLE} - Scenarios"),
        filename=f"numerical_{orientation}_scenarios.pdf", label="PDF",
        button_type="default", width=80, sizing_mode="fixed",
    )

    copy_src = pn.widgets.TextAreaInput(value="", visible=False, sizing_mode="fixed",
                                        width=0, height=0)
    copy_btn = pn.widgets.Button(name="Copy", width=80, sizing_mode="fixed")
    copy_btn.js_on_click(args={"src": copy_src}, code="""
    const text = src.value || "";
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text);
    } else {
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

    def _refresh_exports(*_events):
        frame = _export_frame()
        copy_src.value = frame.to_csv(index=False)
        print_src.value = printable_table_html(
            frame, f"{mod.TITLE} - Scenario table", dict(mod.COLUMN_TITLES))

    def _row_from_page(event):
        payload = str(event.new).rpartition("#")[0]
        if not payload:
            return
        try:
            data = json.loads(payload)
        except ValueError:
            logger.warning("Unreadable scenario row from the page: %r", payload)
            return
        current = pd.DataFrame(table.value, columns=columns)
        row = row_from_payload(data, dict(mod.DEFAULT_ROW))
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
        if not upload.value:
            show_error(ValueError("Choose a CSV file first, then press Upload."))
            return
        try:
            table.value = read_scenario_frame(upload.value, params, columns)
            clear_error()
        except Exception as exc:
            logger.exception("Scenario CSV upload failed for %s", orientation)
            show_error(exc)

    def _collect_scenarios(frame):
        """Every row in the table is one MODFLOW run; the Site cell labels it."""
        rows = []
        for position, (_index, raw) in enumerate(frame.iterrows(), start=1):
            try:
                row = {key: float(raw[key]) for key in params}
            except (TypeError, ValueError, KeyError):
                raise ValueError(f"Row {position} has a missing or non-numeric input.")
            row["label"] = str(raw.get(SITE_COLUMN) or f"Scenario {position}")
            rows.append(row)
        if len(rows) > MAX_MULTIPLE_RUNS:
            raise ValueError(
                f"Too many runs: the limit is {MAX_MULTIPLE_RUNS} rows per comparison "
                f"(you have {len(rows)}). Every row is a full numerical simulation - "
                f"tick the rows you do not need and press Delete row."
            )
        validate = getattr(mod, "VALIDATE_ROWS", None)
        if validate is not None:
            validate(rows)
        return rows

    def _stop_polling():
        # disabled only, never the caption: Button.name is a constant parameter
        # on some Panel builds, and the queue counts in the status card already
        # say what is happening.
        run_btn.disabled = False
        if poller["callback"] is not None:
            poller["callback"].stop()
            poller["callback"] = None

    def _draw(scenario_rows, values, picked):
        """The finished runs, plotted the way every other multiple page plots."""
        labels = [row.get("label", f"Run {i + 1}") for i, row in enumerate(scenario_rows)]
        frame = pd.DataFrame(table.value, columns=columns)
        measured = [_optional_float(v) for v in frame[MEASURED_COLUMN].tolist()]
        row_x, row_y = measured_series(measured)
        site_x, site_y = site_measured_points(picked, len(values) + 1)

        plot, plot_data = comparison_plot(
            f"{mod.TITLE} - Lₘₐₓ by scenario / site",
            "Numerical plume length",
            list(range(1, len(values) + 1)), values,
            0, "", "Scenario / Site", return_data=True,
            field_points=(row_x, row_y), site_points=(site_x, site_y),
            field_label="Measured plume length (scenario table)",
            site_series_label="Measured plume length (site database)",
            manual_color=MEASURED_COLOR,
        )
        plot_pane.object = plot
        show_graph(True)

        outputs = [{"label": f"{labels[i]} Lₘₐₓ", "value": f"{value:.2f}",
                    "unit": "m"} for i, value in enumerate(values)]
        show_status(summary_card(
            [(item["label"], f"{item['value']} {item['unit']}") for item in outputs],
            title=f"{len(values)} {word} Run(s) Complete",
        ))
        results["frame"] = frame.assign(**{"Model Lmax [m]": values}) if values else None
        _refresh_exports()

        state.update({
            "parameters": [{"symbol": "Runs", "name": "Run Count", "value": len(values),
                            "unit": "-"}],
            "outputs": outputs,
            "plot_data": plot_data,
        })
        report_bridge.object = report_bridge_html(
            f"{mod.TITLE} - Multiple Simulation", mod.TITLE,
            f"numerical_{orientation}_multiple_report.pdf",
            parameters=state["parameters"], outputs=state["outputs"],
            plot_data=state["plot_data"],
        )

    def _run(_=None):
        plot_pane.object = None
        show_graph(False)
        report_bridge.object = report_bridge_html(clear=True)
        try:
            frame = pd.DataFrame(table.value, columns=columns)
            picked = _picked_sites()
            if frame.empty and not picked:
                raise ValueError("Nothing to run: add a scenario row, upload a CSV, "
                                 "or pick a site to plot its measured plume length.")
            if frame.empty:
                # Measured points only - no simulation to queue, but the sites on
                # screen are real, so plot them.
                _draw([], [], picked)
                return

            scenario_rows = _collect_scenarios(frame)
            run_btn.disabled = True
            job_ids = [
                mod.submit_job(mod.JOB_KIND, {
                    **{key: row[key] for key in params if key not in ("C_D", "C_A")},
                    "cd": row["C_D"],
                    "ca": row["C_A"],
                })
                for row in scenario_rows
            ]

            def _poll():
                statuses = [mod.job_status(job_id) for job_id in job_ids]
                counts = {}
                for entry in statuses:
                    counts[entry["status"]] = counts.get(entry["status"], 0) + 1
                show_status(summary_card(
                    [(key, str(value)) for key, value in sorted(counts.items())],
                    title=f"{len(job_ids)} {word} Run(s)",
                ))
                if any(entry["status"] == "failed" for entry in statuses):
                    failed = next(e for e in statuses if e["status"] == "failed")
                    show_status(error_card(user_instruction(failed.get("error"))))
                    _stop_polling()
                elif all(entry["status"] == "done" for entry in statuses):
                    values = [float(mod.fetch_result(job_id).plume_length)
                              for job_id in job_ids]
                    _draw(scenario_rows, values, picked)
                    _stop_polling()

            poller["callback"] = pn.state.add_periodic_callback(_poll, 2000, start=True)
            _poll()
        except Exception as exc:
            logger.exception("%s numerical scenario run failed", word)
            show_error(exc)
            plot_pane.object = None
            show_graph(False)
            report_bridge.object = report_bridge_html(clear=True)
            _stop_polling()

    add_btn.js_on_click(args={"bridge": row_input}, code=_ADD_ROW_JS)
    row_input.param.watch(_row_from_page, "value")
    run_btn.on_click(_run)
    del_row_btn.on_click(_delete_rows)
    clear_btn.on_click(_clear)
    upload_btn.on_click(_on_upload)
    table.param.watch(_refresh_exports, "value")
    table.on_edit(_refresh_exports)
    _refresh_exports()

    return scenario_layout(
        status=status, picker=site_picker, search=site_search, run_btn=run_btn,
        graph_slot=graph_slot, toolbar=(template_btn, upload, upload_btn),
        save_btn=save_btn, save_menu=save_menu, table=table,
        row_buttons=(add_btn, del_row_btn, clear_btn),
        hidden=(copy_src, print_src, row_input),
        bridges=(report_bridge, height_bridge),
    )
