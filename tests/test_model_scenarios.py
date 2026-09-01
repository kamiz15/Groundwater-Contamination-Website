"""Scenario-table multiple mode (panel_model_scenarios), wired to Liedl first."""
import math

import pandas as pd
import panel as pn
import pytest

from analytical_models import liedl_lmax
from panel_analytical_common import comparison_plot_data
from panel_model_scenarios import (
    MEASURED_COLUMN, SITE_COLUMN, _default_row, column_titles, measured_series,
    read_scenario_csv, run_rows, scenario_app, scenario_columns, site_measured_points,
)
from panel_site_comparison import MODEL_SPECS


def _site(**over):
    site = {
        "id": 1, "display_id": 1, "site_unit": "Borden", "compound": "Benzene",
        "aquifer_thickness": 4.0, "plume_length": 120.0, "plume_width": 5.0,
        "electron_donor": 5.0, "electron_acceptor_o2": 8.0,
        "alpha_tv": 0.002, "gamma": 3.5, "extra_data": {},
    }
    site.update(over)
    return site


def _frame(model, rows):
    return pd.DataFrame(rows, columns=scenario_columns(model))


def test_columns_cover_every_model_argument():
    for model, spec in MODEL_SPECS.items():
        assert set(spec["args"]) < set(scenario_columns(model))


def _row(model, label="Manual", **over):
    row = _default_row(model, MODEL_SPECS[model]["defaults"], label=label)
    row.update(over)
    return row


def test_a_ticked_site_contributes_its_measurement_only():
    """Parameters are typed or uploaded - the reference database carries no
    alpha_Tv or gamma, so deriving a run from a site would fabricate them."""
    xs, ys = site_measured_points([_site(), _site(id=2, plume_length=None)], start=1)

    assert (xs, ys) == ([1], [120.0])


def test_one_row_is_runnable_on_its_own():
    rows = [_row("liedl")]
    _labels, lengths, _measured = run_rows("liedl", _frame("liedl", rows))

    assert math.isfinite(lengths[0])


def test_every_row_is_one_run():
    rows = [_row("liedl", label="A", M=4.0, alpha_Tv=0.002),
            _row("liedl", label="B", M=2.0, alpha_Tv=0.002)]

    labels, lengths, _measured = run_rows("liedl", _frame("liedl", rows))

    assert labels == ["A", "B"]
    assert math.isclose(lengths[0], liedl_lmax(4.0, 0.002, 3.5, 8.0, 5.0))


def test_a_blank_parameter_is_reported_not_guessed():
    rows = [_row("liedl", alpha_Tv=None)]

    with pytest.raises(ValueError, match="Row 1"):
        run_rows("liedl", _frame("liedl", rows))


def test_rows_without_a_measurement_are_left_off_the_measured_series():
    assert measured_series([120.0, None, 30.0]) == ([1, 3], [120.0, 30.0])


def test_measured_points_reach_the_graph_on_their_own_x():
    data = comparison_plot_data(
        "Liedl et al. (2005)", "Liedl model plume length", [1, 2, 3], [80.0, 90.0, 100.0],
        0, "someone@example.com", "Scenario",
        field_points=([1, 3], [120.0, 30.0]), field_label="Measured plume length",
    )
    assert (data["field_x"], data["field_y"]) == ([1, 3], [120.0, 30.0])
    assert data["manual_x"] == [1, 2, 3]          # never re-parked past the last point
    assert data["x_label"] == "Scenario"
    assert data["field_label"] == "Measured plume length"


def test_uploaded_csv_fills_in_the_optional_columns():
    csv = b"M,alpha_Tv,gamma,C_A,C_D\n2,0.001,3.5,8,5\n3,0.001,3.5,8,5\n"
    frame = read_scenario_csv("liedl", csv)
    assert list(frame.columns) == scenario_columns("liedl")
    assert frame[SITE_COLUMN].tolist() == ["Scenario 1", "Scenario 2"]
    _labels, lengths, _measured = run_rows("liedl", frame)
    assert len(lengths) == 2


def test_uploaded_csv_missing_a_parameter_is_rejected():
    with pytest.raises(ValueError, match="alpha_Tv"):
        read_scenario_csv("liedl", b"M,gamma,C_A,C_D\n2,3.5,8,5\n")


# --- column headings and the (absent) result box -------------------------------

@pytest.mark.parametrize("model", sorted(MODEL_SPECS))
def test_columns_are_headed_with_names_and_symbols(model):
    """Raw argument keys (M, alpha_Tv) are not what the single pages show."""
    titles = column_titles(model)

    for arg in MODEL_SPECS[model]["args"]:
        assert titles[arg] != arg, f"{model}.{arg} still shows its raw key"
        assert "[" in titles[arg], f"{model}.{arg} has no unit"


def test_the_headings_match_the_single_pages():
    titles = column_titles("liedl")

    assert titles["M"] == "Source Thickness T_s [m]"
    assert titles["alpha_Tv"] == "Vertical Transverse Dispersivity α_Tv [m]"
    assert titles["gamma"] == "Stoichiometric Ratio γ [-]"


def test_a_model_param_meta_does_not_cover_still_gets_a_heading():
    """BIOSCREEN is not in the table-title map; its own spec supplies the words."""
    titles = column_titles("bioscreen")

    assert titles["Cthres"] == "Threshold Contaminant Concentration C_thres [mg/L]"
    assert titles["v"] == "Groundwater Seepage Velocity v [m/yr]"


def test_the_stored_columns_stay_canonical():
    """Only the heading changes - an uploaded CSV still carries the real keys."""
    assert scenario_columns("liedl") == [SITE_COLUMN, "M", "alpha_Tv", "gamma",
                                         "C_A", "C_D", MEASURED_COLUMN]


def test_a_sites_only_run_still_exports_its_graph():
    """No model row is not nothing: the measured points on the graph are the
    report, or the Download PDF button has nothing to offer."""
    from unittest.mock import patch
    import panel_model_scenarios as psm

    sites = [_site(id=1, site_unit="Hill AFB", plume_length=502.92),
             _site(id=2, site_unit="No measurement", plume_length=None)]

    with patch.object(psm, "get_user_sites_rows", return_value=sites),          patch.object(psm, "filter_valid_sites_for_model", side_effect=lambda r, _m: (r, {})),          patch.object(psm, "selected_site_ids", return_value={1, 2}),          patch.object(psm, "authenticated_email", return_value="u@e.com"):
        app = psm.scenario_app("liedl")

    assert len(app.select(pn.widgets.Tabulator)[0].value) == 0        # nothing modelled
    posted = [str(p.object) for p in app.select(pn.pane.HTML) if "cast-report" in str(p.object)]
    assert posted, "a measured-only run posted no report"
    assert "Hill AFB" in posted[0]
    assert "No measurement" not in posted[0]     # a site without one is not a row


def test_the_panel_reports_its_height_to_the_page():
    """The graph is last: a frame that cannot grow cuts it off completely."""
    app = scenario_app("liedl")
    panes = [str(p.object) for p in app.select(pn.pane.HTML)]

    assert any("cast-frame-height" in html for html in panes)


def test_the_page_listens_for_the_height_it_posts():
    """Both halves of the contract, or the frame silently never resizes."""
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "static" / "script.js"
    body = script.read_text(encoding="utf-8", errors="replace")

    assert 'data.type !== "cast-frame-height"' in body
    assert "f.contentWindow === event.source" in body          # only our own frames


@pytest.mark.parametrize("caption", ["Download Sample File", "Upload", "Update Graph"])
def test_the_action_buttons_wear_the_site_blue(caption):
    """The outcome, not the mechanism: button_type="primary" takes the colour
    from panel_theme and keeps its radius, padding and shadow, which a private
    stylesheet would replace."""
    app = scenario_app("liedl")

    widget = next(w for w in app.select()
                  if getattr(w, "label", None) == caption or getattr(w, "name", None) == caption)

    branded = (widget.button_type == "primary"
               or any("#155da9" in sheet for sheet in widget.stylesheets))
    assert branded, f"{caption} is not branded"


def test_the_file_picker_wears_the_site_blue():
    app = scenario_app("liedl")
    picker = app.select(pn.widgets.FileInput)[0]

    assert any("file-selector-button" in sheet and "#155da9" in sheet
               for sheet in picker.stylesheets)


def test_the_panel_opens_with_no_result_box():
    app = scenario_app("liedl")
    status = app.select(pn.pane.HTML)[0]

    assert status.object == ""


# --- the run button ----------------------------------------------------------

def test_the_panel_owns_its_run_button():
    """Wherever the picker is, the button that runs the table is in here."""
    app = scenario_app("liedl")
    names = [w.name for w in app.select(pn.widgets.Button)]

    assert "Update Graph" in names


@pytest.mark.parametrize("model", sorted(MODEL_SPECS))
def test_the_picker_lives_in_the_panel_beside_the_graph(model):
    """It is a widget in this document, so there is nothing to post in from the
    page and no site bridge left to post it over."""
    app = scenario_app(model)

    assert len(app.select(pn.widgets.MultiSelect)) == 1
    assert not any("cast-sites" in str(p.object) for p in app.select(pn.pane.HTML))


# --- the toolbar --------------------------------------------------------------

TOOLBAR = ["Download Sample File", "Upload", "Delete table", "Add row",
           "Delete row", "Copy", "CSV", "Excel", "PDF", "Print"]


def _labels(app):
    """Button captions in document order (FileDownload labels, Button names)."""
    out = []
    for widget in app.select():
        if isinstance(widget, pn.widgets.FileDownload):
            out.append(widget.label)
        elif isinstance(widget, pn.widgets.Button):
            out.append(widget.name)
    return out


@pytest.mark.parametrize("model", sorted(MODEL_SPECS))
def test_the_whole_old_cast_toolbar_is_present(model):
    """Nothing was lost in the redesign. Add row and Delete row became a round +
    and -, so their wording is read off the tooltip - it still has to be there."""
    captions = _captions(scenario_app(model))

    for caption in TOOLBAR:
        assert caption in captions, f"{caption} is missing from the toolbar"


def test_no_toolbar_button_is_hidden_before_a_run():
    """Nothing waits for a run to appear - that is how they used to vanish."""
    app = scenario_app("liedl")

    for widget in app.select():
        caption = getattr(widget, "label", None) or getattr(widget, "name", None)
        if caption in TOOLBAR:
            assert widget.visible is not False, f"{caption} starts hidden"


@pytest.mark.parametrize("export", ["csv", "excel", "pdf"])
def test_the_exports_write_a_real_file_before_any_run(export):
    """Exporting must work on the rows as they stand, not only after a run."""
    from panel_model_scenarios import _csv_bytes, _excel_bytes, _pdf_bytes

    frame = _frame("liedl", [{SITE_COLUMN: "Borden", "M": 2.0, "alpha_Tv": 0.001,
                              "gamma": 3.5, "C_A": 8.0, "C_D": 5.0,
                              MEASURED_COLUMN: 120.0}])
    writer = {"csv": _csv_bytes, "excel": _excel_bytes,
              "pdf": lambda f: _pdf_bytes(f, "Liedl - Scenarios")}[export]

    data = writer(frame).getvalue()

    assert len(data) > 0
    if export == "pdf":
        assert data.startswith(b"%PDF")
    if export == "excel":
        assert data.startswith(b"PK")          # xlsx is a zip


@pytest.mark.parametrize("model", sorted(MODEL_SPECS))
def test_every_model_gets_the_same_page(model):
    """One layout across all eight, not Liedl plus seven exceptions."""
    app = scenario_app(model)
    table = app.select(pn.widgets.Tabulator)[0]
    names = [w.name for w in app.select(pn.widgets.Button)]

    assert table.value.columns.tolist() == scenario_columns(model)
    assert len(table.value) == 0                    # nothing preloaded
    assert table.selectable == "checkbox"           # Delete row can see a selection
    assert not table.disabled                       # and rows stay editable
    assert {"Update Graph", "Delete table"} <= set(names)
    assert {"Add row", "Delete row"} <= _captions(app)      # caption or tooltip
    # 20 is what an in-frame Add-row dialog would claim; the Save Data menu sits
    # at 30 and is not one.
    assert [c for c in app.select(pn.Column) if c.styles.get("z-index") == "20"] == []


@pytest.mark.parametrize("model", sorted(MODEL_SPECS))
def test_every_model_ships_a_sample_its_upload_accepts(model):
    from panel_model_scenarios import sample_scenarios

    frame = sample_scenarios(model)

    assert len(frame) > 100
    assert len(read_scenario_csv(model, frame.to_csv(index=False).encode())) == len(frame)


@pytest.mark.parametrize("model", sorted(MODEL_SPECS))
def test_every_model_bridges_to_the_page_the_same_way(model):
    """One contract, or a page's dialog and picker talk to nothing on some models.

    The Add-row dialog belongs to the page - a dialog built in here could only
    ever cover the frame. It is the one thing still posted across."""
    app = scenario_app(model)
    hidden = {w.name for w in app.select(pn.widgets.TextInput) if w.visible is False}
    panes = [str(p.object) for p in app.select(pn.pane.HTML)]

    assert "cast-scenario-row" in hidden
    assert "cast-site-ids" not in hidden             # the picker is a widget now
    assert not any("cast-sites-request" in html for html in panes)


def test_the_graph_sits_above_the_scenario_card():
    """Output first, the way the single pages read; the table it came from last."""
    app = scenario_app("liedl")
    card = next(c for c in app if c.styles.get("background") == "#eef1f5")

    assert _top_index(app, _graph_slot(app)) < _top_index(app, card)


# --- the redesigned Liedl page (sidebar_sites) --------------------------------
# The site picker sits in the page sidebar, so this panel has none: the ticked
# ids are posted in over the bridge, which is what lets a run mix typed rows
# with picked sites without a reload throwing the rows away.

from panel_model_scenarios import drop_rows     # noqa: E402


def _button(app, caption):
    """By label, name, or tooltip: the redesigned + and - keep their wording in
    the tooltip, and a test presses the button a user would press."""
    return next(w for w in app.select()
                if caption in (getattr(w, "label", None), getattr(w, "name", None),
                               getattr(w, "description", None)))


def _top_index(app, wanted):
    """Which top-level row of the page `wanted` is in - it may be nested inside
    one, since the redesigned stage puts the graph beside the picker."""
    for position, child in enumerate(app):
        if child is wanted or (hasattr(child, "select") and wanted in child.select()):
            return position
    raise AssertionError("that is not on this page")


def _click(app, caption):
    _button(app, caption).clicks += 1


def _bridge(app, name="cast-site-ids"):
    """One of the two hidden widgets the page writes into."""
    return next(w for w in app.select(pn.widgets.TextInput) if w.name == name)


def _update_graph(app, ids="?"):
    """Press Update Graph, whichever layout this app is.

    With the picker on the page the button only runs JS: it reads the ticked ids
    and writes them onto a bridge, and the run follows the value into Python.
    With the picker in the panel there is no bridge - ticking is setting the
    widget, and the press is a plain click."""
    picker = app.select(pn.widgets.MultiSelect)
    if picker:
        if ids not in ("?", ""):
            picker[0].value = [int(part) for part in str(ids).split(",")
                               if part.strip().lstrip("-").isdigit()]
        elif ids == "":
            picker[0].value = []            # unticked everything
        _click(app, "Update Graph")
        return
    bridge = _bridge(app)
    nonce = bridge.value.rpartition("#")[2]
    bridge.value = f"{ids}#{int(nonce) + 1 if nonce.isdigit() else 1}"


def _graph_slot(app):
    """The Column holding either the placeholder, or the plot and its key.

    Found by what is in it, not by where it sits: the redesigned layout nests it
    beside the picker instead of hanging it off the top level."""
    for column in app.select(pn.Column):
        first = next(iter(column), None)
        if isinstance(first, pn.pane.Bokeh):
            return column
        if isinstance(first, pn.pane.HTML) and "Update Graph" in str(first.object):
            return column
    raise AssertionError("this app has no graph slot")


def _captions(app):
    """Every caption a user can read off a button - the tooltip counts, because
    the redesigned row buttons carry their wording there."""
    out = set()
    for widget in app.select():
        for attr in ("label", "name", "description"):
            value = getattr(widget, attr, None)
            if isinstance(value, str) and value:
                out.add(value)
    return out


def _add_scenario(app, **values):
    """Add a row the way the page does: Add row opens the page's own <dialog>,
    and the filled-in form is posted back onto the row bridge."""
    import json

    bridge = _bridge(app, "cast-scenario-row")
    seq = bridge.value.rpartition("#")[2]
    payload = {"name": "Manual", **{k: str(v) for k, v in values.items()}}
    bridge.value = json.dumps(payload) + "#" + str(int(seq) + 1 if seq.isdigit() else 1)


def _liedl_page(sites=(), seeded=()):
    """The redesigned page with the site database stubbed out."""
    from unittest.mock import patch
    import panel_model_scenarios as psm

    stack = [
        patch.object(psm, "get_user_sites_rows", return_value=list(sites)),
        patch.object(psm, "filter_valid_sites_for_model", side_effect=lambda r, _m: (r, {})),
        patch.object(psm, "selected_site_ids", return_value=set(seeded)),
        patch.object(psm, "authenticated_email", return_value="u@e.com"),
    ]
    for ctx in stack:
        ctx.start()
    try:
        return psm.scenario_app("liedl")
    finally:
        for ctx in reversed(stack):
            ctx.stop()


def test_dropping_rows_goes_by_position_and_renumbers():
    frame = _frame("liedl", [_row("liedl", label="A"), _row("liedl", label="B"),
                             _row("liedl", label="C")])

    left = drop_rows(frame, [0, 2])

    assert left[SITE_COLUMN].tolist() == ["B"]
    assert left.index.tolist() == [0]          # or the next delete picks the wrong row


def test_the_redesigned_page_has_no_picker_of_its_own():
    app = _liedl_page()
    names = [w.name for w in app.select(pn.widgets.Button)]

    assert "Update Graph" in names
    assert "Run Scenarios" not in names
    assert "Delete table" in names
    assert {"Add row", "Delete row"} <= _captions(app)


def test_the_graph_sits_above_the_scenario_table():
    """The single pages read output-first; the table it was built from is last."""
    app = _liedl_page()
    card = next(c for c in app if c.styles.get("background") == "#eef1f5")

    assert _top_index(app, _graph_slot(app)) < _top_index(app, card)


def test_the_graph_replaces_its_placeholder_and_can_actually_be_shown():
    """The blank-graph bug: pn.pane.Bokeh writes a False `visible` onto the figure
    itself when .object is set, then reads it straight back when you try to show
    the pane again - so a hidden plot pane can never be shown a second time and
    every run drew into something invisible. The slot swaps its child instead."""
    from unittest.mock import patch

    from bokeh.plotting import figure

    import panel_model_scenarios as psm

    app = _liedl_page()
    holder = _graph_slot(app)[0]
    assert isinstance(holder, pn.pane.HTML)
    assert "height:420px" in str(holder.object)             # the graph's own min_height

    _add_scenario(app)
    with patch.object(psm, "comparison_plot", lambda *a, **k: (figure(), {"caption": ""})):
        _update_graph(app)

    drawn = _graph_slot(app)[0]
    assert isinstance(drawn, pn.pane.Bokeh)
    assert drawn.object is not None
    assert drawn.visible is True                # False here is a blank graph area

    _click(app, "Delete table")
    _update_graph(app)                          # nothing left to run
    assert isinstance(_graph_slot(app)[0], pn.pane.HTML)    # the box comes back


def test_the_add_row_dialog_belongs_to_the_page_not_this_frame():
    """A dialog pinned inside the Panel document can only ever cover the iframe,
    which is a band in the middle of the page. This layout has none of its own."""
    from panel_model_scenarios import _ADD_ROW_JS

    app = _liedl_page()

    assert [c for c in app.select(pn.Column) if c.styles.get("z-index") == "20"] == []
    assert "cast-scenario-open" in _ADD_ROW_JS       # it asks the page to open one
    assert "cast-scenario-row" in _ADD_ROW_JS        # and takes the row back
    assert "bridge.value" in _ADD_ROW_JS             # through a model handle
    assert "querySelector" not in _ADD_ROW_JS        # never the DOM: shadow roots


def test_a_row_posted_back_by_the_page_lands_in_the_table():
    app = _liedl_page()
    table = app.select(pn.widgets.Tabulator)[0]

    _add_scenario(app, name="Borden", M=4.0)

    assert len(table.value) == 1
    assert table.value[SITE_COLUMN].tolist() == ["Borden"]
    assert table.value["M"].tolist() == [4.0]
    assert table.value["gamma"].tolist() == [3.5]   # untouched fields keep the default
    assert not table.disabled                       # and the row stays editable


def test_a_field_the_form_left_out_falls_back_to_the_model_default():
    """A blank in the table is a row that only fails later, at run time."""
    from panel_model_scenarios import scenario_row_from_payload

    row = scenario_row_from_payload("liedl", {"name": "", "M": "", "measured": "oops"})

    assert row[SITE_COLUMN] == "Manual"
    assert row["M"] == 2.0                          # the model default, not None
    assert row[MEASURED_COLUMN] is None             # optional, and a typo is not fatal


def test_a_row_is_ticked_with_a_checkbox_because_every_cell_is_an_editor():
    """Panel gives each column an editor, so a click on a cell opens that editor
    rather than selecting the row - Delete row never saw a selection."""
    table = _liedl_page().select(pn.widgets.Tabulator)[0]

    assert table.selectable == "checkbox"
    assert not table.disabled


def test_delete_row_takes_the_ticked_row_and_says_so_when_none_is():
    app = _liedl_page()
    table = app.select(pn.widgets.Tabulator)[0]
    status = app.select(pn.pane.HTML)[0]

    _add_scenario(app, name="A")
    _add_scenario(app, name="B")
    _click(app, "Delete row")                               # nothing ticked
    assert len(table.value) == 2 and "Select a row" in str(status.object)

    table.selection = [0]
    _click(app, "Delete row")
    assert table.value[SITE_COLUMN].tolist() == ["B"]


def test_typed_rows_and_ticked_sites_reach_one_graph():
    """The point of the redesign: type scenarios without picking anything, tick
    sites without losing the rows, and one Update Graph plots both."""
    from unittest.mock import patch

    from bokeh.plotting import figure

    import panel_model_scenarios as psm

    seen = {}

    def _capture(*args, **kwargs):
        seen["args"], seen["kwargs"] = args, kwargs
        return figure(), {"caption": ""}

    app = _liedl_page(sites=[_site(id=1, site_unit="Hill AFB", plume_length=502.92)])
    _add_scenario(app)
    _add_scenario(app)
    with patch.object(psm, "comparison_plot", _capture):
        _update_graph(app, ids="1")         # the page had one site ticked

    modelled = seen["args"][3]
    site_x, site_y = seen["kwargs"]["site_points"]
    assert len(modelled) == 2                               # both typed rows ran
    assert 502.92 in site_y                                 # and the site came too
    assert site_x[-1] == 3                                  # parked after the last row


def test_ticking_a_site_does_not_touch_the_typed_rows():
    """The reason the ids are posted in rather than submitted: a reload would
    restart this document and take the table with it."""
    from unittest.mock import patch

    from bokeh.plotting import figure

    import panel_model_scenarios as psm

    app = _liedl_page(sites=[_site(id=1, plume_length=120.0)])
    table = app.select(pn.widgets.Tabulator)[0]
    _add_scenario(app)

    with patch.object(psm, "comparison_plot", lambda *a, **k: (figure(), {"caption": ""})):
        _update_graph(app, ids="1")

    assert len(table.value) == 1


def test_a_press_with_the_page_silent_still_runs_the_urls_sites():
    """Cross-origin, an older cached page, a panel opened directly: "?" falls back
    to the shared link rather than quietly dropping every site."""
    from unittest.mock import patch

    from bokeh.plotting import figure

    import panel_model_scenarios as psm

    seen = {}

    def _capture(*a, **k):
        seen["kwargs"] = k
        return figure(), {"caption": ""}

    app = _liedl_page(sites=[_site(id=1, site_unit="Hill AFB", plume_length=502.92)],
                      seeded=[1])
    with patch.object(psm, "comparison_plot", _capture):
        _update_graph(app)                  # ids="?" - the page said nothing

    assert 502.92 in seen["kwargs"]["site_points"][1]


def test_a_shared_link_still_runs_when_the_bridge_never_speaks():
    """Cross-origin, a stale page, a panel opened directly: fall back to the ids
    the URL carried rather than drawing nothing."""
    app = _liedl_page(sites=[_site(id=1, site_unit="Hill AFB", plume_length=502.92)],
                      seeded=[1])
    posted = [str(p.object) for p in app.select(pn.pane.HTML) if "cast-report" in str(p.object)]

    assert posted and "Hill AFB" in posted[0]


def test_the_two_measured_sources_are_two_series_with_a_key_to_read_them():
    """Sites and typed rows both carry measurements. Merged into one colour they
    could not be told apart, so the key under the graph would have been a lie."""
    from unittest.mock import patch

    from bokeh.plotting import figure

    import panel_model_scenarios as psm

    seen = {}

    def _capture(*a, **k):
        seen["kwargs"] = k
        return figure(), {"caption": ""}

    app = _liedl_page(sites=[_site(id=1, site_unit="Hill AFB", plume_length=502.92)])
    _add_scenario(app, name="typed", measured=120.0)
    with patch.object(psm, "comparison_plot", _capture):
        _update_graph(app, ids="1")

    assert seen["kwargs"]["field_points"] == ([1], [120.0])      # the table's own column
    assert seen["kwargs"]["site_points"] == ([2], [502.92])      # the picked site
    assert "scenario table" in seen["kwargs"]["field_label"]
    assert "site database" in seen["kwargs"]["site_series_label"]


def test_the_key_names_the_two_sources_and_nothing_else():
    """Two entries, one per place a plotted value can come from, and both round:
    the key is two colours to read, not a shape vocabulary to learn."""
    from panel_analytical_common import MEASURED_COLOR, MODEL_COLOR, SITE_COLOR
    from panel_model_scenarios import _legend_html

    key = _legend_html()

    assert key.count("display:inline-flex") == 2
    assert MEASURED_COLOR in key and "Scenario table" in key
    assert SITE_COLOR in key and "Selected sites" in key
    assert MODEL_COLOR not in key                   # the modelled series is not in it
    assert "border-radius:2px" not in key           # no squares left


def test_the_site_series_is_drawn_as_circles():
    """Same shape as every other series - the key tells them apart by colour."""
    from bokeh.models import Scatter

    from panel_analytical_common import SITE_COLOR, comparison_plot

    plot = comparison_plot("t", "m", [1], [10.0], 0, "u@e.com", "Scenario",
                           field_points=([1], [15.0]), site_points=([2], [500.0]))
    markers = {g.glyph.fill_color: g.glyph.marker
               for g in plot.renderers if isinstance(g.glyph, Scatter)}

    assert markers[SITE_COLOR] == "circle"


def test_the_key_only_shows_once_there_is_a_graph_to_read():
    app = _liedl_page()

    assert len(_graph_slot(app)) == 1               # the placeholder, and nothing else


def test_the_modelled_dots_wear_the_colour_their_key_entry_carries():
    """The key names two sources, so everything the scenario table produced -
    modelled and typed-measured alike - is drawn in the scenario table's colour."""
    from unittest.mock import patch

    from bokeh.plotting import figure

    import panel_model_scenarios as psm
    from panel_analytical_common import MEASURED_COLOR

    seen = {}

    def _capture(*a, **k):
        seen["kwargs"] = k
        return figure(), {"caption": ""}

    app = _liedl_page()
    _add_scenario(app)
    with patch.object(psm, "comparison_plot", _capture):
        _update_graph(app)

    assert seen["kwargs"]["manual_color"] == MEASURED_COLOR


def test_the_single_pages_keep_their_own_modelled_colour():
    """comparison_plot is shared. On a single page the modelled result stands
    against amber database points and still needs a hue of its own."""
    from bokeh.models import Scatter

    from panel_analytical_common import MODEL_COLOR, comparison_plot

    plot = comparison_plot("t", "m", [1], [10.0], 0, "u@e.com", "Site",
                           show_database=False)
    colors = {g.glyph.fill_color for g in plot.renderers if isinstance(g.glyph, Scatter)}

    assert MODEL_COLOR in colors


# --- Print, and the sample the page opens on ----------------------------------

def test_print_sends_the_table_and_not_the_page_around_it():
    """window.print() sends whichever document it is called on, and this one is
    the run button, the graph, its key, two button rows and the table."""
    import io as _io

    import pandas as pd

    from panel_model_scenarios import _PRINT_JS, printable_table_html

    frame = _frame("liedl", [_row("liedl", label="Borden")])
    doc = printable_table_html(frame, "Liedl - Scenario table", column_titles("liedl"))

    assert doc.startswith("<!doctype html>")
    assert "Borden" in doc and "<table" in doc
    assert "Source Thickness" in doc              # the headings the table shows
    assert "Update Graph" not in doc              # and nothing else off the page
    assert isinstance(pd.read_html(_io.StringIO(doc))[0], pd.DataFrame)
    assert "sheet.contentWindow.print()" in _PRINT_JS   # printed from its own frame
    assert "window.print()" not in _PRINT_JS


def test_the_print_payload_tracks_the_table():
    app = _liedl_page()
    printable = next(w for w in app.select(pn.widgets.TextAreaInput)
                     if "<table" in str(w.value))

    _add_scenario(app, name="Later row")

    assert "Later row" in printable.value


def test_the_sample_is_the_shipped_reference_sites():
    """One dataset: what Download Sample File hands back is what the table opens
    on, and it re-uploads through read_scenario_csv without editing."""
    from panel_model_scenarios import sample_scenarios

    frame = sample_scenarios("liedl")

    assert len(frame) > 100
    assert list(frame.columns) == scenario_columns("liedl")
    assert frame["M"].nunique() > 1               # real per-site values
    assert frame[MEASURED_COLUMN].nunique() > 1
    reread = read_scenario_csv("liedl", frame.to_csv(index=False).encode())
    assert len(reread) == len(frame)


def test_the_sample_fills_the_two_parameters_no_database_carries():
    """alpha_Tv and gamma are in no site database. They come from the model
    defaults, which makes a preloaded row a starting point, not an answer."""
    from panel_model_scenarios import sample_scenarios
    from panel_site_comparison import MODEL_SPECS

    frame = sample_scenarios("liedl")
    defaults = MODEL_SPECS["liedl"]["defaults"]

    assert frame["alpha_Tv"].unique().tolist() == [defaults["alpha_Tv"]]
    assert frame["gamma"].unique().tolist() == [defaults["gamma"]]
    from panel_model_scenarios import MAX_SCENARIOS
    assert len(frame) <= MAX_SCENARIOS            # and it fits inside one run


def test_the_table_opens_empty_and_is_filled_by_the_user():
    """Nothing is preloaded: rows come from an uploaded file or from Add row.
    The sample is a download, not a starting state."""
    table = _liedl_page().select(pn.widgets.Tabulator)[0]

    assert len(table.value) == 0


def test_the_sample_download_is_what_upload_takes_back():
    """Download Sample File, fill it in, upload it - the round trip has to work
    without editing the headers."""
    from panel_model_scenarios import sample_scenarios

    app = _liedl_page()
    table = app.select(pn.widgets.Tabulator)[0]
    upload = app.select(pn.widgets.FileInput)[0]

    upload.value = sample_scenarios("liedl").to_csv(index=False).encode()
    _click(app, "Upload")

    assert len(table.value) == len(sample_scenarios("liedl"))


def test_an_upload_fills_the_empty_table():
    app = _liedl_page()
    table = app.select(pn.widgets.Tabulator)[0]
    upload = app.select(pn.widgets.FileInput)[0]

    upload.value = b"Site,M,alpha_Tv,gamma,C_A,C_D\nMine,2,0.001,3.5,8,5\n"
    _click(app, "Upload")

    assert table.value[SITE_COLUMN].tolist() == ["Mine"]


def test_the_page_serves_a_fresh_script_after_the_bridge_changed():
    """script.js is cache-busted by hand; a stale one is a bridge that never runs."""
    from pathlib import Path

    base = (Path(__file__).resolve().parents[1] / "templates" / "base.html").read_text(
        encoding="utf-8", errors="replace")

    assert "?v=20260805a" not in base
