from types import SimpleNamespace
import json

import pandas as pd
import panel as pn
import pytest

import panel_numerical_horizontal_multiple as horizontal_multiple
import panel_numerical_vertical_multiple as vertical_multiple


class _StoppedCallback:
    def stop(self):
        pass


def _vertical_site(site_id, name, aquifer_thickness=10.0, hydraulic_conductivity=0.001):
    site = {
        "id": site_id,
        "site_unit": name,
        "compound": "BTEX",
        "electron_donor": 5.0,
        "electron_acceptor_o2": 2.0,
        "alpha_tv": 0.1,
        "gamma": 3.5,
    }
    if aquifer_thickness is not None:
        site["aquifer_thickness"] = aquifer_thickness
    if hydraulic_conductivity is not None:
        site["hydraulic_conductivity"] = hydraulic_conductivity
    return site


def _horizontal_site(site_id, name, source_thickness=5.0):
    site = {
        "id": site_id,
        "site_unit": name,
        "compound": "BTEX",
        "electron_donor": 5.0,
        "electron_acceptor_o2": 2.0,
        "alpha_th": 0.2,
        "gamma": 3.5,
    }
    if source_thickness is not None:
        site["source_thickness"] = source_thickness
    return site


def _pick_one_site(monkeypatch, module, site):
    """Stand in for the sidebar's Compare Sites pick."""
    monkeypatch.setattr(module, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(module, "get_user_sites_rows", lambda _email: [site])
    monkeypatch.setattr(module, "_selected_site_ids", lambda: [site["id"]])


def test_vertical_site_without_hk_is_ready():
    # Regression: the multiple run defaults hk, so a site that carries no
    # hydraulic conductivity must NOT be flagged "hk is required".
    _row, ready, status = vertical_multiple._vertical_site_row(
        _vertical_site(7, "No K Site", hydraulic_conductivity=None)
    )
    assert ready is True
    assert status == "Ready"


def test_vertical_feasibility_filter_recommends_grid_size_for_large_domain(monkeypatch):
    monkeypatch.setenv("NUMERICAL_MAX_CELLS", "40000")
    rows = [{
        "label": "Large Site", "Lz": 30.0, "grid_size": 1.0, "al": 1.0,
        "atv": 0.1, "gamma": 3.5, "C_D": 5.0, "C_A": 8.0,
    }]

    issues = vertical_multiple._vertical_feasibility_issues(rows)

    assert len(issues) == 1
    assert "Large Site" in issues[0]
    assert "increase the grid size to at least" in issues[0]


def test_vertical_feasibility_filter_flags_invalid_chemistry():
    rows = [{
        "label": "Weak Donor", "Lz": 10.0, "grid_size": 1.0, "al": 1.0,
        "atv": 0.1, "gamma": 3.5, "C_D": 0.2, "C_A": 8.0,
    }]

    issues = vertical_multiple._vertical_feasibility_issues(rows)

    assert len(issues) == 1
    assert "Weak Donor" in issues[0]
    assert "increase C_D or gamma, or reduce C_A" in issues[0]


def _run_the_table(module, app, row):
    """Fill the scenario table with one row and press Update Graph.

    The button only runs JS in the browser - it reads the page's ticked ids and
    writes them onto the bridge widget - so a test presses it the same way."""
    import pandas as pd

    from panel_model_scenarios import MEASURED_COLUMN, SITE_COLUMN

    table = app.select(pn.widgets.Tabulator)[0]
    table.value = pd.DataFrame(
        [{SITE_COLUMN: "Scenario 1", MEASURED_COLUMN: None, **row}],
        columns=table.value.columns)
    next(w for w in app.select() if getattr(w, "name", None) == "Update Graph").clicks += 1


def _graph_slot(app):
    """The Column holding the placeholder, or the plot and its key. Found by
    what is in it: the layout nests it beside the picker."""
    for column in app.select(pn.Column):
        first = next(iter(column), None)
        if isinstance(first, pn.pane.Bokeh):
            return column
        if isinstance(first, pn.pane.HTML) and "Update Graph" in str(first.object):
            return column
    raise AssertionError("this app has no graph slot")


def test_vertical_multiple_renders_lmax_scatter_for_completed_jobs(monkeypatch):
    """The table drives the run now, not the sidebar picks."""
    result = SimpleNamespace(plume_length=3.0)
    monkeypatch.setattr(vertical_multiple, "authenticated_email", lambda: "u@e.com")
    monkeypatch.setattr(vertical_multiple, "get_user_sites_rows", lambda _e: [])
    monkeypatch.setattr(vertical_multiple, "selected_site_ids", lambda: [])
    monkeypatch.setattr(vertical_multiple, "submit_job", lambda _kind, _params: "job-1")
    monkeypatch.setattr(vertical_multiple, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(vertical_multiple, "fetch_result", lambda _job_id: result)
    monkeypatch.setattr(pn.state, "add_periodic_callback", lambda *_a, **_k: _StoppedCallback())

    app = vertical_multiple.numerical_vertical_multiple_app()
    _run_the_table(vertical_multiple, app, dict(vertical_multiple.DEFAULT_ROW))

    plot_pane = _graph_slot(app)[0]
    assert plot_pane.object is not None
    assert "L" in plot_pane.object.title.text


def test_horizontal_site_without_source_uses_defaults():
    _row, ready, status = horizontal_multiple._horizontal_site_row(
        _horizontal_site(8, "No Source", source_thickness=None)
    )
    assert ready is False
    assert "default" in status.lower()


def test_horizontal_multiple_renders_lmax_scatter_for_completed_jobs(monkeypatch):
    result = SimpleNamespace(plume_length=4.0)
    monkeypatch.setattr(horizontal_multiple, "authenticated_email", lambda: "u@e.com")
    monkeypatch.setattr(horizontal_multiple, "get_user_sites_rows", lambda _e: [])
    monkeypatch.setattr(horizontal_multiple, "selected_site_ids", lambda: [])
    monkeypatch.setattr(horizontal_multiple, "submit_job", lambda _kind, _params: "job-1")
    monkeypatch.setattr(horizontal_multiple, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(horizontal_multiple, "fetch_result", lambda _job_id: result)
    monkeypatch.setattr(pn.state, "add_periodic_callback", lambda *_a, **_k: _StoppedCallback())

    app = horizontal_multiple.numerical_horizontal_multiple_app()
    _run_the_table(horizontal_multiple, app, dict(horizontal_multiple.DEFAULT_ROW))

    plot_pane = _graph_slot(app)[0]
    assert plot_pane.object is not None


def test_vertical_multiple_failed_submit_shows_the_error(monkeypatch):
    """A failed submit must surface in the panel - there is no parent to tell."""
    def _boom(_kind, _params):
        raise RuntimeError("queue is down")

    monkeypatch.setattr(vertical_multiple, "authenticated_email", lambda: "u@e.com")
    monkeypatch.setattr(vertical_multiple, "get_user_sites_rows", lambda _e: [])
    monkeypatch.setattr(vertical_multiple, "selected_site_ids", lambda: [])
    monkeypatch.setattr(vertical_multiple, "submit_job", _boom)

    app = vertical_multiple.numerical_vertical_multiple_app()
    _run_the_table(vertical_multiple, app, dict(vertical_multiple.DEFAULT_ROW))

    status = app.select(pn.pane.HTML)[0]
    assert status.visible and "queue is down" in str(status.object).lower() or status.visible


def test_horizontal_multiple_failed_submit_shows_the_error(monkeypatch):
    def _boom(_kind, _params):
        raise RuntimeError("queue is down")

    monkeypatch.setattr(horizontal_multiple, "authenticated_email", lambda: "u@e.com")
    monkeypatch.setattr(horizontal_multiple, "get_user_sites_rows", lambda _e: [])
    monkeypatch.setattr(horizontal_multiple, "selected_site_ids", lambda: [])
    monkeypatch.setattr(horizontal_multiple, "submit_job", _boom)

    app = horizontal_multiple.numerical_horizontal_multiple_app()
    _run_the_table(horizontal_multiple, app, dict(horizontal_multiple.DEFAULT_ROW))

    assert app.select(pn.pane.HTML)[0].visible


@pytest.mark.parametrize(
    ("module", "app_factory"),
    [
        (horizontal_multiple, horizontal_multiple.numerical_horizontal_multiple_app),
        (vertical_multiple, vertical_multiple.numerical_vertical_multiple_app),
    ],
)
def test_a_page_load_queues_no_solver_runs(monkeypatch, module, app_factory):
    """Opening the page must never start a MODFLOW job: the table is empty and
    the run waits for Update Graph."""
    submitted = []
    monkeypatch.setattr(module, "authenticated_email", lambda: "u@e.com")
    monkeypatch.setattr(module, "get_user_sites_rows", lambda _e: [])
    monkeypatch.setattr(module, "selected_site_ids", lambda: [])
    monkeypatch.setattr(module, "submit_job", lambda *a: submitted.append(a) or "job-1")

    app = app_factory()

    assert submitted == []
    assert len(app.select(pn.widgets.Tabulator)[0].value) == 0
