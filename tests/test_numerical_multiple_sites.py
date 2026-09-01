"""Numerical multiple pages: the scenario table drives the runs.

They are the same page as every other multiple now (panel_model_scenarios): rows
come from the page's Add-row dialog or an uploaded CSV, a ticked site contributes
its measured plume length and nothing else, and Update Graph runs the table.

What stays different is the cost of a row: each one is a full MODFLOW/MT3DMS job,
so a comparison is capped at NUMERICAL_MULTIPLE_MAX_RUNS rather than 200.
"""
import pandas as pd
import panel as pn
import pytest

import panel_numerical_horizontal_multiple as horiz
import panel_numerical_multiple_common as common
import panel_numerical_vertical_multiple as vert
from panel_model_scenarios import MEASURED_COLUMN, SITE_COLUMN

PANELS = [(horiz, "source_thickness"), (vert, "Lz")]


def _site(**over):
    site = {
        "id": 1, "display_id": 1, "site_unit": "Borden", "compound": "Benzene",
        "aquifer_thickness": 2.0, "plume_length": 120.0, "plume_width": 5.0,
        "hydraulic_conductivity": 1e-4, "electron_donor": 5.0,
        "electron_acceptor_o2": 8.0, "electron_acceptor_no3": None,
        "alpha_tv": 0.001, "alpha_th": 0.01, "alpha_t": 0.01, "gamma": 3.5,
        "source_thickness": 3.0, "extra_data": {},
    }
    site.update(over)
    return site


def _app(panel, monkeypatch, sites=(), picked=()):
    monkeypatch.setattr(panel, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(panel, "get_user_sites_rows", lambda _e: list(sites))
    monkeypatch.setattr(panel, "selected_site_ids", lambda: list(picked))
    return panel.numerical_multiple_app(panel) if False else (
        vert.numerical_vertical_multiple_app() if panel is vert
        else horiz.numerical_horizontal_multiple_app())


def _button(app, caption):
    return next(w for w in app.select()
                if getattr(w, "label", None) == caption or getattr(w, "name", None) == caption)


def _update_graph(app, ids="?"):
    """Press Update Graph. Ticking a site is setting the picker widget now -
    the ids used to arrive from the page over a bridge."""
    picker = app.select(pn.widgets.MultiSelect)[0]
    if ids not in ("?", ""):
        picker.value = [int(part) for part in str(ids).split(",") if part.strip().isdigit()]
    elif ids == "":
        picker.value = []
    _button(app, "Update Graph").clicks += 1


@pytest.mark.parametrize("panel,size_key", PANELS)
def test_the_page_opens_empty_like_every_other_multiple(panel, size_key, monkeypatch):
    app = _app(panel, monkeypatch)
    table = app.select(pn.widgets.Tabulator)[0]
    names = [w.name for w in app.select(pn.widgets.Button)]

    assert len(table.value) == 0
    assert table.selectable == "checkbox"
    assert not table.disabled
    assert {"Update Graph", "Delete table"} <= set(names)
    # + and - carry their wording in the tooltip.
    assert {"Add row", "Delete row"} <= {w.description for w in app.select(pn.widgets.Button)}
    assert len(app.select(pn.widgets.MultiSelect)) == 1   # its own site picker
    assert size_key in table.value.columns


@pytest.mark.parametrize("panel,size_key", PANELS)
def test_nothing_at_all_runs_nothing(panel, size_key, monkeypatch):
    app = _app(panel, monkeypatch)
    status = app.select(pn.pane.HTML)[0]

    _update_graph(app)

    assert "Nothing to run" in str(status.object)


@pytest.mark.parametrize("panel,size_key", PANELS)
def test_a_ticked_site_contributes_a_measurement_not_a_run(panel, size_key, monkeypatch):
    """The choice that separates this from the old page: a site is a measured
    point. Its parameters are not borrowed to fabricate a simulation."""
    submitted = []
    monkeypatch.setattr(panel, "submit_job", lambda kind, payload: submitted.append(payload))
    app = _app(panel, monkeypatch, sites=[_site(id=1, plume_length=120.0)])

    _update_graph(app, ids="1")

    assert submitted == []                                # no MODFLOW job queued
    # The slot is nested beside the picker, so it is found by what is in it.
    slot = next(c for c in app.select(pn.Column)
                if isinstance(next(iter(c), None), pn.pane.Bokeh))
    assert isinstance(slot[0], pn.pane.Bokeh)             # but the graph is drawn


@pytest.mark.parametrize("panel,size_key", PANELS)
def test_the_run_cap_counts_table_rows(panel, size_key, monkeypatch):
    """Every row is a full solver job, so the cap survives the redesign - it just
    counts rows now instead of ticked sites."""
    over = common.MAX_MULTIPLE_RUNS + 1
    app = _app(panel, monkeypatch)
    table = app.select(pn.widgets.Tabulator)[0]
    status = app.select(pn.pane.HTML)[0]
    row = {SITE_COLUMN: "S", MEASURED_COLUMN: None, **dict(panel.DEFAULT_ROW)}
    table.value = pd.DataFrame([row] * over, columns=table.value.columns)

    _update_graph(app)

    assert "Too many runs" in str(status.object)
    assert str(common.MAX_MULTIPLE_RUNS) in str(status.object)


@pytest.mark.parametrize("panel,size_key", PANELS)
def test_the_sample_maps_the_reference_sites_to_this_orientation(panel, size_key, monkeypatch):
    frame = common.sample_scenarios(panel)

    assert len(frame) > 100
    assert list(frame.columns) == common.scenario_columns(panel)
    assert frame[size_key].notna().all()
    assert frame[MEASURED_COLUMN].nunique() > 1            # real measured lengths
    # and it goes back in through Upload without editing
    reread = common.read_scenario_frame(
        frame.to_csv(index=False).encode(), panel.SCENARIO_COLUMNS,
        common.scenario_columns(panel))
    assert len(reread) == len(frame)


@pytest.mark.parametrize("panel,size_key", PANELS)
def test_the_add_row_dialog_gets_this_orientations_fields(panel, size_key, monkeypatch):
    specs = common.numerical_field_specs(panel)

    assert [s["key"] for s in specs] == list(panel.SCENARIO_COLUMNS)
    assert all(s["label"] != s["key"] for s in specs)      # headings, not raw keys
    assert all("[" in s["label"] for s in specs)           # with units
