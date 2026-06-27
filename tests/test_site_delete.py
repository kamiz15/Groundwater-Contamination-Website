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
