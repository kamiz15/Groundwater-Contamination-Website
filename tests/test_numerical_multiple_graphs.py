from types import SimpleNamespace
import json

import pandas as pd
import panel as pn

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


def _vertical_table():
    return pn.widgets.Tabulator(
        pd.DataFrame(
            [{"Site": "Manual", "Lz": 10.0, "grid_size": 1.0, "al": 1.0, "atv": 0.1, "gamma": 3.5, "C_D": 5.0, "C_A": 8.0}],
            columns=vertical_multiple.SCENARIO_COLUMNS,
        )
    )


def _horizontal_table():
    return pn.widgets.Tabulator(
        pd.DataFrame(
            [{"Site": "Manual", "source_thickness": 5.0, "grid_size": 1.0, "al": 1.0, "at": 0.2, "gamma": 3.5, "C_D": 5.0, "C_A": 8.0}],
            columns=horizontal_multiple.SCENARIO_COLUMNS,
        )
    )


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

    monkeypatch.setattr(vertical_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        vertical_multiple,
        "query_int",
        lambda name, default: 1 if name in {"output_only", "run"} else default,
    )
    monkeypatch.setattr(vertical_multiple, "query_str", lambda name, default="": "")
    monkeypatch.setattr(vertical_multiple, "submit_job", lambda _kind, _params: "job-1")
    monkeypatch.setattr(vertical_multiple, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(vertical_multiple, "fetch_result", lambda _job_id: result)
    monkeypatch.setattr(pn.state, "add_periodic_callback", lambda *_args, **_kwargs: _StoppedCallback())

    app = vertical_multiple.numerical_vertical_multiple_app()
    plot_pane = app.objects[1]

    assert plot_pane.object is not None
    assert "Lmax" in plot_pane.object.title.text


def test_vertical_multiple_output_mode_renders_posted_jobs(monkeypatch):
    result = SimpleNamespace(plume_length=3.0)
    rows = [{"label": "#7 Valid", "Lz": 10.0, "grid_size": 1.0, "al": 1.0, "atv": 0.1, "gamma": 3.5, "C_D": 5.0, "C_A": 2.0}]

    monkeypatch.setattr(vertical_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        vertical_multiple,
        "query_int",
        lambda name, default: 1 if name == "output_only" else 0,
    )
    monkeypatch.setattr(
        vertical_multiple,
        "query_str",
        lambda name, default="": json.dumps(["job-1"]) if name == "job_ids" else json.dumps(rows),
    )
    monkeypatch.setattr(vertical_multiple, "fetch_result", lambda _job_id: result)

    app = vertical_multiple.numerical_vertical_multiple_app()
    result_pane = app.objects[0]
    plot_pane = app.objects[1]

    assert plot_pane.object is not None
    assert "#7 Valid" in result_pane.object


def test_vertical_multiple_input_mode_lists_site_picker(monkeypatch):
    monkeypatch.setattr(vertical_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        vertical_multiple,
        "query_int",
        lambda name, default: 1 if name == "input_only" else default,
    )
    monkeypatch.setattr(vertical_multiple, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(vertical_multiple, "get_user_sites_rows", lambda _email: [_vertical_site(7, "Valid")])

    app = vertical_multiple.numerical_vertical_multiple_app()

    # title, scenario table, site section, result pane, hidden run button, job bridge, run listener
    assert len(app.objects) == 7
    assert "Vertical Numerical Model - Multiple" in app.objects[0].object
    assert app.objects[1].height == 160
    assert app.objects[3].object == ""  # input panel result box stays empty (errors only)
    assert app.objects[4].height == 0
    assert app.objects[5].object == ""
    assert "run-numerical-multiple" in app.objects[6].object


def test_vertical_site_picker_orders_ready_first_and_click_adds(monkeypatch):
    monkeypatch.setattr(vertical_multiple, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(
        vertical_multiple,
        "get_user_sites_rows",
        # Non-ready first in the DB order; the picker must surface the Ready one first.
        lambda _email: [_vertical_site(8, "No Thickness", aquifer_thickness=None), _vertical_site(7, "Ready Site")],
    )

    table = _vertical_table()
    widget, note = vertical_multiple._build_site_picker(table)

    assert note is None
    assert list(widget.value["ID"]) == [7, 8]

    # Clicking the first (Ready) row appends it to the scenario table above.
    widget.selection = [0]
    updated = pd.DataFrame(table.value)
    assert len(updated) == 2
    assert "Site" not in updated.columns
    expected, _ready, _status = vertical_multiple._vertical_site_row(_vertical_site(7, "Ready Site"))
    for col in vertical_multiple.SCENARIO_COLUMNS:
        assert updated.iloc[1][col] == expected[col]
    assert widget.selection == []


def test_vertical_site_picker_displays_current_database_number(monkeypatch):
    monkeypatch.setattr(vertical_multiple, "authenticated_email", lambda: "user@example.com")
    site = _vertical_site(1577, "Current Site")
    site["display_id"] = 1
    monkeypatch.setattr(vertical_multiple, "get_user_sites_rows", lambda _email: [site])

    widget, note = vertical_multiple._build_site_picker(_vertical_table())

    assert note is None
    assert list(widget.value["ID"]) == [1]


def test_horizontal_site_without_source_uses_defaults():
    _row, ready, status = horizontal_multiple._horizontal_site_row(
        _horizontal_site(8, "No Source", source_thickness=None)
    )
    assert ready is False
    assert "default" in status.lower()


def test_horizontal_multiple_renders_lmax_scatter_for_completed_jobs(monkeypatch):
    result = SimpleNamespace(plume_length=4.0)

    monkeypatch.setattr(horizontal_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        horizontal_multiple,
        "query_int",
        lambda name, default: 1 if name in {"output_only", "run"} else default,
    )
    monkeypatch.setattr(horizontal_multiple, "query_str", lambda name, default="": "")
    monkeypatch.setattr(horizontal_multiple, "submit_job", lambda _kind, _params: "job-1")
    monkeypatch.setattr(horizontal_multiple, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(horizontal_multiple, "fetch_result", lambda _job_id: result)
    monkeypatch.setattr(pn.state, "add_periodic_callback", lambda *_args, **_kwargs: _StoppedCallback())

    app = horizontal_multiple.numerical_horizontal_multiple_app()
    plot_pane = app.objects[1]

    assert plot_pane.object is not None
    assert "Lmax" in plot_pane.object.title.text


def test_horizontal_multiple_input_mode_lists_site_picker(monkeypatch):
    monkeypatch.setattr(horizontal_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        horizontal_multiple,
        "query_int",
        lambda name, default: 1 if name == "input_only" else default,
    )
    monkeypatch.setattr(horizontal_multiple, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(horizontal_multiple, "get_user_sites_rows", lambda _email: [_horizontal_site(7, "Valid")])

    app = horizontal_multiple.numerical_horizontal_multiple_app()

    assert len(app.objects) == 7
    assert "Horizontal Numerical Model - Multiple" in app.objects[0].object
    assert app.objects[1].height == 160
    assert app.objects[3].object == ""  # input panel result box stays empty (errors only)
    assert app.objects[4].height == 0
    assert app.objects[5].object == ""
    assert "run-numerical-multiple" in app.objects[6].object


def test_run_listener_walks_shadow_roots():
    # Regression: Bokeh 3 renders the hidden run button inside shadow DOM, so a
    # light-DOM querySelectorAll("button") never found it and the template's
    # Run click silently did nothing.
    for module in (vertical_multiple, horizontal_multiple):
        assert "shadowRoot" in module._external_run_listener_html()


def test_vertical_multiple_failed_submit_posts_error_to_parent(monkeypatch):
    # A failed run must still message the parent page, otherwise its Run button
    # stays disabled on "Running..." forever.
    monkeypatch.setattr(vertical_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        vertical_multiple,
        "query_int",
        lambda name, default: 1 if name == "input_only" else default,
    )
    monkeypatch.setattr(vertical_multiple, "authenticated_email", lambda: None)

    def _broken_submit(_kind, _params):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(vertical_multiple, "submit_job", _broken_submit)

    app = vertical_multiple.numerical_vertical_multiple_app()
    run_btn = app.objects[4]
    run_btn.clicks += 1

    job_bridge = app.objects[5]
    assert "numerical-multiple-result" in job_bridge.object
    assert "queue unavailable" in job_bridge.object
    assert not run_btn.disabled


def test_horizontal_multiple_failed_submit_posts_error_to_parent(monkeypatch):
    monkeypatch.setattr(horizontal_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        horizontal_multiple,
        "query_int",
        lambda name, default: 1 if name == "input_only" else default,
    )
    monkeypatch.setattr(horizontal_multiple, "authenticated_email", lambda: None)

    def _broken_submit(_kind, _params):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(horizontal_multiple, "submit_job", _broken_submit)

    app = horizontal_multiple.numerical_horizontal_multiple_app()
    run_btn = app.objects[4]
    run_btn.clicks += 1

    job_bridge = app.objects[5]
    assert "numerical-multiple-result" in job_bridge.object
    assert "queue unavailable" in job_bridge.object
    assert not run_btn.disabled


def test_horizontal_site_picker_click_adds_row(monkeypatch):
    monkeypatch.setattr(horizontal_multiple, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(
        horizontal_multiple,
        "get_user_sites_rows",
        lambda _email: [_horizontal_site(7, "Ready Site")],
    )

    table = _horizontal_table()
    widget, note = horizontal_multiple._build_site_picker(table)

    assert note is None
    widget.selection = [0]
    updated = pd.DataFrame(table.value)
    assert len(updated) == 2
    assert "Site" not in updated.columns
    expected, _ready, _status = horizontal_multiple._horizontal_site_row(_horizontal_site(7, "Ready Site"))
    for col in horizontal_multiple.SCENARIO_COLUMNS:
        assert updated.iloc[1][col] == expected[col]
