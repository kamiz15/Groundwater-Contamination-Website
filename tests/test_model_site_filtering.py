from contextlib import ExitStack
from unittest.mock import patch

import pytest

import analytical_routes
import app as app_module
import empirical_routes
import numerical_routes
from model_site_validation import filter_valid_sites_for_model, site_issues_for_model


def _site(**overrides):
    base = {
        "id": 1,
        "site_unit": "Site A",
        "compound": "BTEX",
        "aquifer_thickness": 10.0,
        "plume_length": 100.0,
        "plume_width": 5.0,
        "hydraulic_conductivity": 0.001,
        "electron_donor": 5.0,
        "electron_acceptor_o2": 8.0,
        "electron_acceptor_no3": 0.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Unit: per-model restrictions
# ---------------------------------------------------------------------------

def test_fully_populated_site_is_valid_for_every_model():
    site = _site()
    for model in ("liedl", "liedl3d", "chu", "ham", "cirpka", "bioscreen", "maier", "birla", "numerical_horizontal"):
        assert site_issues_for_model(site, model) == [], model


def test_zero_electron_acceptor_invalidates_models_that_divide_by_ca():
    site = _site(electron_acceptor_o2=0.0)
    for model in ("liedl", "liedl3d", "chu", "ham", "cirpka", "maier", "birla"):
        assert site_issues_for_model(site, model), model
    # BIOSCREEN and the horizontal numerical model do not divide by C_A.
    assert site_issues_for_model(site, "bioscreen") == []
    assert site_issues_for_model(site, "numerical_horizontal") == []


def test_zero_plume_width_only_affects_models_that_use_source_width():
    site = _site(id=2, plume_width=0.0)
    for model in ("chu", "cirpka", "bioscreen", "numerical_horizontal"):
        assert site_issues_for_model(site, model), model
    for model in ("liedl", "liedl3d", "ham", "maier", "birla"):
        assert site_issues_for_model(site, model) == [], model


def test_missing_fields_are_not_violations():
    site = _site(
        aquifer_thickness=None,
        plume_width=None,
        hydraulic_conductivity=None,
        electron_donor=None,
        electron_acceptor_o2=None,
    )
    for model in ("liedl", "liedl3d", "chu", "ham", "cirpka", "bioscreen", "maier", "birla", "numerical_horizontal"):
        assert site_issues_for_model(site, model) == [], model


def test_out_of_band_hydraulic_conductivity_hides_site_from_horizontal_numerical_only():
    # 0.026 m/s -> 2246.4 m/d, beyond the configured solver band.
    site = _site(id=3, hydraulic_conductivity=0.026)
    assert site_issues_for_model(site, "numerical_horizontal")
    assert site_issues_for_model(site, "liedl") == []


def test_filter_splits_valid_and_invalid_with_issue_map():
    good = _site(id=1)
    bad = _site(id=2, electron_acceptor_o2=0.0)
    valid, invalid = filter_valid_sites_for_model([good, bad], "liedl")
    assert [s["id"] for s in valid] == [1]
    assert list(invalid) == [2]


# ---------------------------------------------------------------------------
# Routes: invalid sites disappear from that model's drop-down only
# ---------------------------------------------------------------------------

@pytest.fixture
def model_pages_client():
    previous_login_disabled = app_module.app.config.get("LOGIN_DISABLED", False)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)
    sites = [
        _site(id=1, site_unit="Good Site"),
        _site(id=2, site_unit="No Acceptor", electron_acceptor_o2=0.0),
        _site(id=3, site_unit="No Width", plume_width=0.0),
    ]
    with ExitStack() as patches:
        for module in (analytical_routes, empirical_routes, numerical_routes):
            patches.enter_context(patch.object(module, "_current_email", return_value="user@example.com"))
            patches.enter_context(patch.object(module, "get_user_sites_rows", return_value=sites))
        yield app_module.app.test_client()
    app_module.app.config["LOGIN_DISABLED"] = previous_login_disabled


def test_liedl_dropdown_hides_zero_acceptor_but_keeps_zero_width(model_pages_client):
    page = model_pages_client.get("/liedl/single").get_data(as_text=True)
    assert "Good Site" in page
    assert "No Acceptor" not in page
    assert "No Width" in page  # plume_width is irrelevant to Liedl


def test_chu_dropdown_hides_both_invalid_sites(model_pages_client):
    page = model_pages_client.get("/chu/single").get_data(as_text=True)
    assert "Good Site" in page
    assert "No Acceptor" not in page
    assert "No Width" not in page


def test_maier_dropdown_hides_zero_acceptor(model_pages_client):
    page = model_pages_client.get("/empirical/maier/single").get_data(as_text=True)
    assert "Good Site" in page
    assert "No Acceptor" not in page
    assert "No Width" in page


def test_hidden_site_id_in_query_string_is_ignored(model_pages_client):
    # Navigating directly with a hidden site's id must not load its data.
    page = model_pages_client.get("/liedl/single?site_id=2").get_data(as_text=True)
    assert 'value="2" selected' not in page


def test_model_dropdown_displays_current_database_number_but_submits_primary_key(monkeypatch):
    rows = [
        _site(id=1577, display_id=1, site_unit="First Current Site"),
        _site(id=1578, display_id=2, site_unit="Second Current Site"),
    ]
    monkeypatch.setattr(analytical_routes, "_current_email", lambda: "user@example.com")
    monkeypatch.setattr(analytical_routes, "get_user_sites_rows", lambda _email: rows)

    previous_login_disabled = app_module.app.config.get("LOGIN_DISABLED", False)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)
    try:
        page = app_module.app.test_client().get("/liedl/single").get_data(as_text=True)
    finally:
        app_module.app.config["LOGIN_DISABLED"] = previous_login_disabled

    assert '<option value="1577" >#1 - First Current Site (BTEX)</option>' in page
    assert '<option value="1578" >#2 - Second Current Site (BTEX)</option>' in page
    assert "#1577 -" not in page
    assert "#1578 -" not in page
