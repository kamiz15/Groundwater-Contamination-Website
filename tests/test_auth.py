from __future__ import annotations

import html
import unittest
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

from mysql.connector import Error
from werkzeug.security import generate_password_hash

import analytical_routes
import app as app_module
import security
import site_routes


TEST_PASSWORD = "correct-horse-battery-staple"
TEST_USER = {
    "id": 7,
    "username": "Test User",
    "email": "test.user@example.com",
    "password_hash": generate_password_hash(TEST_PASSWORD),
}


class FakeCursor:
    def __init__(self):
        self._row = None

    def execute(self, query, params=None):
        params = params or ()
        if "FROM users WHERE email" in query:
            self._row = TEST_USER if params == (TEST_USER["email"],) else None
        elif "FROM users WHERE id" in query:
            self._row = TEST_USER if str(params[0]) == str(TEST_USER["id"]) else None
        else:
            raise AssertionError(f"Unexpected SQL in authentication test: {query}")

    def fetchone(self):
        return dict(self._row) if self._row else None

    def close(self):
        return None


class FakeConnection:
    def cursor(self, dictionary=False):
        return FakeCursor()

    def close(self):
        return None


class AuthenticationFlowTests(unittest.TestCase):
    def setUp(self):
        app_module.app.config.update(TESTING=True, SECRET_KEY="test-secret-key")
        security.reset_rate_limits()
        self.client = app_module.app.test_client()
        self.connection_patch = patch.object(
            app_module,
            "get_db_connection",
            side_effect=lambda: FakeConnection(),
        )
        self.connection_patch.start()

    def tearDown(self):
        self.connection_patch.stop()

    def csrf_token(self, path="/login"):
        self.client.get(path)
        with self.client.session_transaction() as session:
            return session["_csrf_token"]

    def login(self):
        token = self.csrf_token()
        return self.client.post(
            "/login",
            json={"username": TEST_USER["email"], "password": TEST_PASSWORD},
            headers={"X-CSRF-Token": token},
        )

    def test_protected_route_redirects_when_unauthenticated(self):
        response = self.client.get("/analytical")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?next=", response.headers["Location"])

    def test_login_allows_access_to_same_protected_route(self):
        login_response = self.login()
        protected_response = self.client.get("/analytical")

        self.assertEqual(login_response.status_code, 200)
        self.assertTrue(login_response.get_json()["success"])
        self.assertEqual(protected_response.status_code, 200)

    def test_logout_invalidates_access(self):
        self.login()
        with self.client.session_transaction() as session:
            token = session["_csrf_token"]
        logout_response = self.client.post("/logout", headers={"X-CSRF-Token": token})
        protected_response = self.client.get("/analytical")

        self.assertEqual(logout_response.status_code, 302)
        self.assertEqual(protected_response.status_code, 302)
        self.assertIn("/login?next=", protected_response.headers["Location"])

    def test_proxy_auth_check_uses_flask_login_session(self):
        unauthenticated_response = self.client.get("/auth/check")
        self.login()
        authenticated_response = self.client.get("/auth/check")

        self.assertEqual(unauthenticated_response.status_code, 401)
        self.assertEqual(authenticated_response.status_code, 204)

    def test_site_reads_use_current_user_email(self):
        with (
            patch.object(site_routes, "get_user_sites_rows", return_value=[]) as get_rows,
        ):
            self.login()
            response = self.client.get("/sites")

        self.assertEqual(response.status_code, 200)
        # The page renders from a single query, scoped to the session user.
        get_rows.assert_called_once_with(TEST_USER["email"])

    def test_panel_iframe_email_cannot_be_overridden_by_query_string(self):
        with patch.object(analytical_routes, "get_user_sites_rows", return_value=[]):
            self.login()
            response = self.client.get("/liedl/single?email=other@example.com")

        page = response.get_data(as_text=True)
        iframe_src = html.unescape(page.split('iframe src="', 1)[1].split('"', 1)[0])
        iframe_query = parse_qs(urlparse(iframe_src).query)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(iframe_query["email"], [TEST_USER["email"]])

    def test_malformed_json_login_returns_400(self):
        token = self.csrf_token()

        response = self.client.post(
            "/login",
            data="{",
            content_type="application/json",
            headers={"X-CSRF-Token": token},
        )

        self.assertEqual(response.status_code, 400)

    def test_forged_site_post_without_csrf_token_is_rejected(self):
        self.login()

        response = self.client.post(
            "/sites",
            data={"action": "manual", "site_unit": "A", "compound": "B"},
        )

        self.assertEqual(response.status_code, 400)

    def test_registration_db_error_returns_generic_message(self):
        token = self.csrf_token("/register")
        private_detail = "private database detail"

        with self.assertLogs(app_module.logger, level="ERROR") as logs:
            with patch.object(
                app_module,
                "get_db_connection",
                side_effect=Error(private_detail),
            ):
                response = self.client.post(
                    "/register",
                    json={
                        "username": "New User",
                        "email": "new.user@example.com",
                        "password": TEST_PASSWORD,
                        "confirmPassword": TEST_PASSWORD,
                    },
                    headers={"X-CSRF-Token": token},
                )

        response_text = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["message"],
            "Unable to create account. Please try again later.",
        )
        self.assertNotIn(private_detail, response_text)
        self.assertIn(private_detail, "\n".join(logs.output))

    def test_login_rate_limit_rejects_excess_attempts(self):
        token = self.csrf_token()
        payload = {"username": "unknown@example.com", "password": "wrong-password"}

        responses = [
            self.client.post("/login", json=payload, headers={"X-CSRF-Token": token})
            for _ in range(6)
        ]

        self.assertTrue(all(response.status_code == 401 for response in responses[:5]))
        self.assertEqual(responses[5].status_code, 429)


if __name__ == "__main__":
    unittest.main()
