from contextlib import ExitStack
from unittest.mock import patch

import pytest

import analytical_routes
import app as app_module
import empirical_routes
import numerical_routes
from numerical_jobs import save_job_meta


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("NUMERICAL_JOB_ROOT", str(tmp_path / "jobs"))
    previous_login_disabled = app_module.app.config.get("LOGIN_DISABLED", False)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=True)
    with ExitStack() as patches:
        for module in (analytical_routes, empirical_routes, numerical_routes):
            patches.enter_context(patch.object(module, "_current_email", return_value="user@example.com"))
            patches.enter_context(patch.object(module, "get_user_sites_rows", return_value=[]))
        yield app_module.app.test_client()
    app_module.app.config["LOGIN_DISABLED"] = previous_login_disabled


# Mathematically invalid model inputs must be a 400, not a 500.
@pytest.mark.parametrize(
    "path",
    [
        "/liedl/single/export?alpha_Tv=0",
        "/liedl/single/export?C_EA0=0",
        "/liedl/single/export?M=1e300",
        "/chu/single/export?epsilon=8",
        "/ham/single/export?alpha_T=0",
        "/cirpka/single/export?Sw=0",
        "/empirical/maier/single/export?tv=0",
        "/empirical/maier/single/export?g=-1",   # complex result -> TypeError
        "/empirical/birla/single/export?g=-100",  # log of non-positive
        "/bioscreen/single/export?ng=0",
    ],
)
def test_invalid_model_inputs_return_400(path, client):
    response = client.get(path)

    assert response.status_code == 400


# inf/nan query parameters fall back to defaults instead of crashing.
@pytest.mark.parametrize(
    "path",
    [
        "/numerical/vertical/single/export?ncol=inf",
        "/numerical/vertical/single/export?perlen=nan",
    ],
)
def test_non_finite_numerical_params_fall_back_to_defaults(path, client, monkeypatch):
    monkeypatch.setattr(numerical_routes, "submit_job", lambda _kind, _params: "job-123")

    response = client.get(path)

    assert response.status_code == 202


def test_non_finite_analytical_params_fall_back_to_defaults(client):
    response = client.get("/bioscreen/single/export?time=inf")

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"


def test_done_job_with_missing_result_file_returns_410(client, monkeypatch):
    save_job_meta("done-job", {"email": "user@example.com"})
    monkeypatch.setattr(numerical_routes, "job_status", lambda _job_id: {"status": "done"})

    response = client.get("/numerical/jobs/done-job/report")

    assert response.status_code == 410
    assert "no longer available" in response.get_json()["message"]


def test_login_rejects_oversized_password_without_hashing(monkeypatch):
    import security

    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=False)
    security.reset_rate_limits()
    client = app_module.app.test_client()
    client.get("/login")
    with client.session_transaction() as session:
        token = session["_csrf_token"]

    def fail_hash(*_args, **_kwargs):
        raise AssertionError("oversized password must not be hashed")

    monkeypatch.setattr(app_module, "check_password_hash", fail_hash)
    monkeypatch.setattr(app_module, "get_db_connection", fail_hash)

    response = client.post(
        "/login",
        json={"username": "user@example.com", "password": "x" * 10_000},
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 401
    assert response.get_json() == {"success": False, "message": "Invalid email or password."}
