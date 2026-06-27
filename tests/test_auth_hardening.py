"""Regression tests for the authentication/authorization hardening pass.

Covers the gaps fixed in the security review:
- registration input validation (email format, password length)
- login user-enumeration resistance (constant-time dummy hash path)
- rate-limit client identification no longer trusts spoofable X-Forwarded-For
- session/remember cookie hardening flags
- Panel identity comes from the trusted proxy header, never the query string
"""

import app as app_module
import security
from panel_auth import authenticated_email

from test_auth_pytest import MemoryDatabase, _register, _csrf_token, TEST_PASSWORD


def _client(monkeypatch):
    database = MemoryDatabase()
    monkeypatch.setattr(app_module, "get_db_connection", database.connect)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=False)
    security.reset_rate_limits()
    return app_module.app.test_client(), database


def test_registration_rejects_invalid_email(monkeypatch):
    client, database = _client(monkeypatch)
    response = _register(client, email="not-an-email")
    assert response.get_json()["success"] is False
    assert "valid email" in response.get_json()["message"].lower()
    assert database.users_by_email == {}


def test_registration_rejects_short_password(monkeypatch):
    client, database = _client(monkeypatch)
    response = _register(client, password="short", confirmPassword="short")
    assert response.get_json()["success"] is False
    assert "at least" in response.get_json()["message"].lower()
    assert database.users_by_email == {}


def test_registration_accepts_strong_passphrase(monkeypatch):
    client, database = _client(monkeypatch)
    response = _register(client)
    assert response.get_json()["success"] is True
    assert "test.user@example.com" in database.users_by_email


def test_login_for_unknown_user_runs_hash_check(monkeypatch):
    """Unknown accounts must still exercise a password hash comparison so the
    response is indistinguishable (timing-wise) from a wrong-password attempt."""
    client, _ = _client(monkeypatch)
    calls = {"n": 0}
    real_check = app_module.check_password_hash

    def counting_check(pw_hash, password):
        calls["n"] += 1
        return real_check(pw_hash, password)

    monkeypatch.setattr(app_module, "check_password_hash", counting_check)

    resp = client.post(
        "/login",
        json={"username": "ghost@example.com", "password": "whatever-password"},
        headers={"X-CSRF-Token": _csrf_token(client, "/login")},
    )
    assert resp.get_json() == {"success": False, "message": "Invalid email or password."}
    assert calls["n"] == 1  # dummy hash comparison ran even with no such user


def test_rate_limit_ignores_spoofed_forwarded_for(monkeypatch):
    """A client cannot dodge the login rate limit by rotating X-Forwarded-For."""
    client, _ = _client(monkeypatch)
    monkeypatch.setattr(security, "TRUST_PROXY_HEADERS", True)
    last = None
    for i in range(7):
        last = client.post(
            "/login",
            json={"username": "a@b.com", "password": "x-very-long-password"},
            headers={
                "X-CSRF-Token": _csrf_token(client, "/login"),
                "X-Forwarded-For": f"10.0.0.{i}",  # spoofed, must be ignored
            },
        )
    assert last.status_code == 429  # limit of 5/min enforced despite rotating XFF


def test_session_cookie_flags_are_hardened():
    cfg = app_module.app.config
    assert cfg["SESSION_COOKIE_HTTPONLY"] is True
    assert cfg["SESSION_COOKIE_SAMESITE"] == "Lax"
    assert cfg["REMEMBER_COOKIE_HTTPONLY"] is True


def test_panel_identity_prefers_trusted_header(monkeypatch):
    """authenticated_email must use the proxy-injected header, not ?email=."""
    import panel_auth

    class _Req:
        headers = {"X-Auth-Email": "real.user@example.com"}

        class arguments:
            @staticmethod
            def get(_):
                return [b"attacker@evil.com"]

    class _Ctx:
        request = _Req()

    class _Doc:
        session_context = _Ctx()

    monkeypatch.setattr(panel_auth.pn.state, "curdoc", _Doc(), raising=False)
    assert authenticated_email() == "real.user@example.com"


def test_panel_identity_ignores_query_when_untrusted(monkeypatch):
    """With no trusted header and query trust disabled, no identity leaks."""
    import panel_auth

    class _Req:
        headers = {}

        class arguments:
            @staticmethod
            def get(_):
                return [b"attacker@evil.com"]

    class _Ctx:
        request = _Req()

    class _Doc:
        session_context = _Ctx()

    monkeypatch.setattr(panel_auth.pn.state, "curdoc", _Doc(), raising=False)
    monkeypatch.setattr(panel_auth, "PANEL_TRUST_QUERY_EMAIL", False)
    assert authenticated_email() == ""
