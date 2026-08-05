from contextlib import ExitStack
from unittest.mock import patch

import pytest

import app as app_module
import site_routes


@pytest.fixture
def site_client():
    previous_login_disabled = app_module.app.config.get("LOGIN_DISABLED", False)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)
    with ExitStack() as patches:
        patches.enter_context(
            patch.object(site_routes, "_current_email", return_value="user@example.com")
        )
        yield app_module.app.test_client(), patches
    app_module.app.config["LOGIN_DISABLED"] = previous_login_disabled


def _csrf_token(client):
    client.get("/login")
    with client.session_transaction() as session:
        return session["_csrf_token"]


def test_delete_site_row_is_scoped_to_owner_and_redirects(site_client):
    client, patches = site_client
    calls = []

    def fake_delete(email, site_id):
        calls.append((email, site_id))
        return True

    patches.enter_context(patch.object(site_routes, "delete_site", fake_delete))

    response = client.post(
        "/sites/7/delete", headers={"X-CSRF-Token": _csrf_token(client)}
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/sites")
    assert calls == [("user@example.com", 7)]


def test_delete_missing_or_foreign_site_returns_404(site_client):
    client, patches = site_client
    patches.enter_context(
        patch.object(site_routes, "delete_site", lambda _email, _site_id: False)
    )

    response = client.post(
        "/sites/999/delete", headers={"X-CSRF-Token": _csrf_token(client)}
    )

    assert response.status_code == 404


def test_delete_without_csrf_token_is_rejected(site_client):
    client, _patches = site_client

    response = client.post("/sites/7/delete")

    assert response.status_code == 400


def test_clear_site_database_is_scoped_to_current_user_and_redirects(site_client):
    client, patches = site_client
    calls = []

    def fake_clear(email):
        calls.append(email)
        return 12

    patches.enter_context(patch.object(site_routes, "delete_user_sites", fake_clear))

    response = client.post(
        "/sites/clear", headers={"X-CSRF-Token": _csrf_token(client)}
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/sites")
    assert calls == ["user@example.com"]


def test_clear_database_without_csrf_token_is_rejected(site_client):
    client, _patches = site_client

    response = client.post("/sites/clear")

    assert response.status_code == 400


def test_site_table_displays_compact_user_ids_but_deletes_by_primary_key(site_client):
    client, patches = site_client
    rows = [
        {"id": 1577, "site_unit": "Brand", "compound": "1,2,4-TMB", "extra_data": {}},
        {"id": 1578, "site_unit": "Brand", "compound": "Ethyltoluol", "extra_data": {}},
        {"id": 1579, "site_unit": "Metlen", "compound": "MTBE", "extra_data": {}},
    ]
    patches.enter_context(patch.object(site_routes, "get_owned_sites_rows", return_value=rows))

    page = client.get("/sites").get_data(as_text=True)

    assert "Delete site #1 (Brand)?" in page
    assert "Delete site #2 (Brand)?" in page
    assert "Delete site #3 (Metlen)?" in page
    assert "/sites/1579/delete" in page


def test_site_database_typesets_shared_parameter_labels(site_client):
    client, patches = site_client
    rows = [{
        "id": 7,
        "site_unit": "Demo",
        "compound": "BTEX",
        "aquifer_thickness": 10.0,
        "alpha_tv": 0.1,
        "cthres": 0.5,
        "extra_data": {},
    }]
    patches.enter_context(patch.object(site_routes, "get_owned_sites_rows", return_value=rows))

    page = client.get("/sites").get_data(as_text=True)

    assert "Aquifer Thickness <i>T</i><sub>A</sub> [m]" in page
    assert "Vertical Transverse Dispersivity &alpha;<sub>Tv</sub> [m]" in page
    assert "Threshold Concentration <i>C</i><sub>thres</sub> [mg/L]" in page
    assert 'name="electron_acceptor_no3"' in page
    assert 'aria-label="Recognized CSV columns"' not in page
    assert "Download Sample File" in page
    assert "Plume Width <i>W</i><sub>p</sub> [m]" in page
    assert "<code>site_unit, compound" not in page
