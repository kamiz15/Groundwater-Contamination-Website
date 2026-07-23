from unittest.mock import patch

import pytest

import app as app_module
from security import csrf_token, reset_rate_limits


@pytest.fixture
def client():
    app_module.app.config.update(TESTING=True)
    reset_rate_limits()
    with app_module.app.test_client() as client:
        yield client
    reset_rate_limits()


def _csrf(client):
    with client.session_transaction() as session:
        with app_module.app.test_request_context():
            token = csrf_token()
            session["_csrf_token"] = token
            return token


def test_contact_accepts_demo_submission_without_smtp(client):
    token = _csrf(client)

    response = client.post(
        "/contact",
        json={"name": "Ada", "email": "ada@example.com", "message": "Hello"},
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_contact_rejects_invalid_email(client):
    token = _csrf(client)

    response = client.post(
        "/contact",
        json={"name": "Ada", "email": "not-email", "message": "Hello"},
        headers={"X-CSRF-Token": token},
    )

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_contact_sends_when_smtp_is_configured(client, monkeypatch):
    token = _csrf(client)
    monkeypatch.setattr(app_module, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(app_module, "CONTACT_EMAIL", "team@example.com")
    monkeypatch.setattr(app_module, "CONTACT_FROM_EMAIL", "no-reply@example.com")

    with patch.object(app_module, "_send_contact_email") as send_contact_email:
        response = client.post(
            "/contact",
            json={"name": "Ada", "email": "ada@example.com", "message": "Hello"},
            headers={"X-CSRF-Token": token},
        )

    assert response.status_code == 200
    assert response.get_json()["message"] == "Thanks. Your message has been sent."
    send_contact_email.assert_called_once_with("Ada", "ada@example.com", "Hello")