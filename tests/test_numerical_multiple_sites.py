"""Numerical multiple pages: sidebar site picks -> one solver run per site.

Unlike the analytical/empirical pages these start with nothing selected, because
each picked site queues a full MODFLOW/MT3DMS job.
"""
import pytest

import panel_numerical_horizontal_multiple as horiz
import panel_numerical_vertical_multiple as vert
from route_guards import compare_site_ids
from settings import NUMERICAL_MULTIPLE_MAX_RUNS

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


@pytest.mark.parametrize("panel,size_key", PANELS)
def test_nothing_picked_runs_nothing(panel, size_key, monkeypatch):
    monkeypatch.setattr(panel, "_selected_site_ids", lambda: [])
    with pytest.raises(ValueError, match="Pick at least one site"):
        panel._scenarios_from_sites()


@pytest.mark.parametrize("panel,size_key", PANELS)
def test_one_scenario_per_picked_site_labelled_by_unit(panel, size_key, monkeypatch):
    sites = [_site(id=1, site_unit="Borden"), _site(id=2, site_unit="Vejen"), _site(id=3, site_unit="Ott")]
    monkeypatch.setattr(panel, "get_user_sites_rows", lambda _e: sites)
    monkeypatch.setattr(panel, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(panel, "_selected_site_ids", lambda: [3, 1])

    rows = panel._scenarios_from_sites()

    assert [r["label"] for r in rows] == ["Ott", "Borden"]   # picking order is kept
    assert all(r[size_key] > 0 for r in rows)


@pytest.mark.parametrize("panel,size_key", PANELS)
def test_run_cap_is_enforced(panel, size_key, monkeypatch):
    over = NUMERICAL_MULTIPLE_MAX_RUNS + 1
    sites = [_site(id=i, site_unit=f"S{i}") for i in range(1, over + 1)]
    monkeypatch.setattr(panel, "get_user_sites_rows", lambda _e: sites)
    monkeypatch.setattr(panel, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(panel, "_selected_site_ids", lambda: [s["id"] for s in sites])

    with pytest.raises(ValueError, match="Too many runs"):
        panel._scenarios_from_sites()


@pytest.mark.parametrize("panel,size_key", PANELS)
def test_unknown_site_ids_are_dropped(panel, size_key, monkeypatch):
    monkeypatch.setattr(panel, "get_user_sites_rows", lambda _e: [_site(id=1, site_unit="Borden")])
    monkeypatch.setattr(panel, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(panel, "_selected_site_ids", lambda: [1, 999])

    assert [r["label"] for r in panel._scenarios_from_sites()] == ["Borden"]

    monkeypatch.setattr(panel, "_selected_site_ids", lambda: [999])
    with pytest.raises(ValueError, match="None of the picked sites"):
        panel._scenarios_from_sites()


def test_numerical_pages_default_to_no_selection():
    """default_all=False is what keeps a page load from queueing 336 solver runs."""
    import app as flask_app

    usable = [{"id": 1}, {"id": 2}]
    with flask_app.app.test_request_context("/numerical/vertical/multiple"):
        assert compare_site_ids(usable, default_all=False) == []
        assert compare_site_ids(usable) == [1, 2]          # analytical pages unchanged
    with flask_app.app.test_request_context("/numerical/vertical/multiple?compare_sites=2"):
        assert compare_site_ids(usable, default_all=False) == [2]
