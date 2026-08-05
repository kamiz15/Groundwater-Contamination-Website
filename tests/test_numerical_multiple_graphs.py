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
    assert "40,000-cell limit" in issues[0]
    assert "Use grid_size >=" in issues[0]


def test_vertical_feasibility_filter_flags_invalid_chemistry():
    rows = [{
        "label": "Weak Donor", "Lz": 10.0, "grid_size": 1.0, "al": 1.0,
        "atv": 0.1, "gamma": 3.5, "C_D": 0.2, "C_A": 8.0,
    }]

    issues = vertical_multiple._vertical_feasibility_issues(rows)

    assert len(issues) == 1
    assert "Weak Donor" in issues[0]
    assert "invalid vertical domain length" in issues[0]


def test_vertical_multiple_renders_lmax_scatter_for_completed_jobs(monkeypatch):
    result = SimpleNamespace(plume_length=3.0)

    monkeypatch.setattr(
        vertical_multiple,
        "query_int",
        lambda name, default: 1 if name in {"output_only", "run"} else default,
    )
    monkeypatch.setattr(vertical_multiple, "query_str", lambda name, default="": "")
    _pick_one_site(monkeypatch, vertical_multiple, _vertical_site(7, "Vejen"))
    monkeypatch.setattr(vertical_multiple, "submit_job", lambda _kind, _params: "job-1")
    monkeypatch.setattr(vertical_multiple, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(vertical_multiple, "fetch_result", lambda _job_id: result)
    monkeypatch.setattr(pn.state, "add_periodic_callback", lambda *_args, **_kwargs: _StoppedCallback())

    app = vertical_multiple.numerical_vertical_multiple_app()
    plot_pane = app.objects[1]

    assert plot_pane.object is not None
    assert "L_max" in plot_pane.object.title.text


def test_horizontal_site_without_source_uses_defaults():
    _row, ready, status = horizontal_multiple._horizontal_site_row(
        _horizontal_site(8, "No Source", source_thickness=None)
    )
    assert ready is False
    assert "default" in status.lower()


def test_horizontal_multiple_renders_lmax_scatter_for_completed_jobs(monkeypatch):
    result = SimpleNamespace(plume_length=4.0)

    monkeypatch.setattr(
        horizontal_multiple,
        "query_int",
        lambda name, default: 1 if name in {"output_only", "run"} else default,
    )
    monkeypatch.setattr(horizontal_multiple, "query_str", lambda name, default="": "")
    _pick_one_site(monkeypatch, horizontal_multiple, _horizontal_site(7, "Borden"))
    monkeypatch.setattr(horizontal_multiple, "submit_job", lambda _kind, _params: "job-1")
    monkeypatch.setattr(horizontal_multiple, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(horizontal_multiple, "fetch_result", lambda _job_id: result)
    monkeypatch.setattr(pn.state, "add_periodic_callback", lambda *_args, **_kwargs: _StoppedCallback())

    app = horizontal_multiple.numerical_horizontal_multiple_app()
    plot_pane = app.objects[1]

    assert plot_pane.object is not None
    assert "L_max" in plot_pane.object.title.text


def test_vertical_multiple_failed_submit_shows_the_error(monkeypatch):
    # A failed submit must surface in the panel; there is no longer a parent
    # page relaying it, so the panel itself has to say what went wrong.
    monkeypatch.setattr(
        vertical_multiple,
        "query_int",
        lambda name, default: 1 if name in {"output_only", "run"} else default,
    )
    monkeypatch.setattr(vertical_multiple, "query_str", lambda name, default="": "")
    _pick_one_site(monkeypatch, vertical_multiple, _vertical_site(7, "Vejen"))

    def _broken_submit(_kind, _params):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(vertical_multiple, "submit_job", _broken_submit)

    app = vertical_multiple.numerical_vertical_multiple_app()
    result_pane, plot_pane = app.objects[0], app.objects[1]

    assert "Error" in result_pane.object
    assert plot_pane.object is None

def test_horizontal_multiple_failed_submit_shows_the_error(monkeypatch):
    # A failed submit must surface in the panel; there is no longer a parent
    # page relaying it, so the panel itself has to say what went wrong.
    monkeypatch.setattr(
        horizontal_multiple,
        "query_int",
        lambda name, default: 1 if name in {"output_only", "run"} else default,
    )
    monkeypatch.setattr(horizontal_multiple, "query_str", lambda name, default="": "")
    _pick_one_site(monkeypatch, horizontal_multiple, _horizontal_site(7, "Borden"))

    def _broken_submit(_kind, _params):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(horizontal_multiple, "submit_job", _broken_submit)

    app = horizontal_multiple.numerical_horizontal_multiple_app()
    result_pane, plot_pane = app.objects[0], app.objects[1]

    assert "Error" in result_pane.object
    assert plot_pane.object is None


@pytest.mark.parametrize(
    ("module", "app_factory"),
    [
        (horizontal_multiple, horizontal_multiple.numerical_horizontal_multiple_app),
        (vertical_multiple, vertical_multiple.numerical_vertical_multiple_app),
    ],
)
def test_panel_prompts_when_no_site_is_picked(monkeypatch, module, app_factory):
    submitted = []
    monkeypatch.setattr(module, "query_int", lambda name, default: 1 if name == "output_only" else 0)
    monkeypatch.setattr(module, "query_str", lambda name, default="": "")
    monkeypatch.setattr(module, "submit_job", lambda *a: submitted.append(a) or "job-1")

    app = app_factory()

    assert submitted == []                       # a page load must not queue solver runs
    assert "Compare Sites" in app.objects[0].object
