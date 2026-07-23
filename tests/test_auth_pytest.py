from werkzeug.security import check_password_hash

import app as app_module
import security


TEST_PASSWORD = "correct-horse-battery-staple"


class MemoryCursor:
    def __init__(self, database):
        self.database = database
        self.row = None

    def execute(self, query, params=None):
        params = params or ()
        if "INSERT INTO users" in query:
            username, email, password_hash, country, organisation = params
            if email in self.database.users_by_email:
                raise AssertionError("duplicate registration was not expected")
            user = {
                "id": self.database.next_id,
                "username": username,
                "email": email,
                "password_hash": password_hash,
                "country": country,
                "organisation": organisation,
            }
            self.database.next_id += 1
            self.database.users_by_email[email] = user
            self.database.users_by_id[user["id"]] = user
            return
        if "FROM users WHERE email" in query:
            self.row = self.database.users_by_email.get(params[0])
            return
        if "FROM users WHERE id" in query:
            self.row = self.database.users_by_id.get(int(params[0]))
            return
        raise AssertionError(f"Unexpected SQL in memory auth database: {query}")

    def fetchone(self):
        return dict(self.row) if self.row else None

    def close(self):
        return None


class MemoryConnection:
    def __init__(self, database):
        self.database = database

    def cursor(self, dictionary=False):
        return MemoryCursor(self.database)

    def commit(self):
        return None

    def close(self):
        return None


class MemoryDatabase:
    def __init__(self):
        self.next_id = 1
        self.users_by_email = {}
        self.users_by_id = {}

    def connect(self):
        return MemoryConnection(self)


def _csrf_token(client, path):
    client.get(path)
    with client.session_transaction() as session:
        return session["_csrf_token"]


def _register(client, **overrides):
    payload = {
        "username": "Test User",
        "email": "test.user@example.com",
        "password": TEST_PASSWORD,
        "confirmPassword": TEST_PASSWORD,
    }
    payload.update(overrides)
    return client.post(
        "/register",
        json=payload,
        headers={"X-CSRF-Token": _csrf_token(client, "/register")},
    )


def _login(client, **overrides):
    payload = {"username": "test.user@example.com", "password": TEST_PASSWORD}
    payload.update(overrides)
    return client.post(
        "/login",
        json=payload,
        headers={"X-CSRF-Token": _csrf_token(client, "/login")},
    )


def test_register_login_logout_happy_path(monkeypatch):
    database = MemoryDatabase()
    monkeypatch.setattr(app_module, "get_db_connection", database.connect)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=False)
    security.reset_rate_limits()
    client = app_module.app.test_client()

    registration = _register(client)
    stored_user = database.users_by_email["test.user@example.com"]
    login = _login(client)
    authenticated = client.get("/auth/check")
    logout = client.post(
        "/logout", headers={"X-CSRF-Token": _csrf_token(client, "/")}
    )
    invalidated = client.get("/auth/check")

    assert registration.status_code == 200
    assert registration.get_json()["success"] is True
    assert check_password_hash(stored_user["password_hash"], TEST_PASSWORD)
    assert login.status_code == 200
    assert login.get_json()["success"] is True
    assert authenticated.status_code == 204
    assert logout.status_code == 302
    assert invalidated.status_code == 401


def test_login_rejects_wrong_password(monkeypatch):
    database = MemoryDatabase()
    monkeypatch.setattr(app_module, "get_db_connection", database.connect)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=False)
    security.reset_rate_limits()
    client = app_module.app.test_client()
    _register(client)

    response = _login(client, password="wrong-password")

    assert response.status_code == 401
    assert response.get_json() == {"success": False, "message": "Invalid email or password."}


def test_registration_rejects_password_mismatch(monkeypatch):
    database = MemoryDatabase()
    monkeypatch.setattr(app_module, "get_db_connection", database.connect)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=False)
    security.reset_rate_limits()
    client = app_module.app.test_client()

    response = _register(client, confirmPassword="different-password")

    assert response.status_code == 400
    assert response.get_json() == {"success": False, "message": "Passwords do not match."}
    assert database.users_by_email == {}


def test_me_reflects_session_state(monkeypatch):
    database = MemoryDatabase()
    monkeypatch.setattr(app_module, "get_db_connection", database.connect)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=False)
    security.reset_rate_limits()
    client = app_module.app.test_client()
    _register(client)

    anonymous = client.get("/me")
    _login(client)
    authenticated = client.get("/me")
    client.post("/logout", headers={"X-CSRF-Token": _csrf_token(client, "/")})
    after_logout = client.get("/me")

    assert anonymous.status_code == 401
    assert anonymous.get_json() == {"authenticated": False}
    assert authenticated.status_code == 200
    body = authenticated.get_json()
    assert body["authenticated"] is True
    assert body["username"] == "Test User"
    assert body["email"] == "test.user@example.com"
    assert after_logout.status_code == 401


def test_registration_rejects_missing_json_field(monkeypatch):
    database = MemoryDatabase()
    monkeypatch.setattr(app_module, "get_db_connection", database.connect)
    app_module.app.config.update(TESTING=True, LOGIN_DISABLED=False)
    security.reset_rate_limits()
    client = app_module.app.test_client()

    response = _register(client, email="")
    assert response.status_code == 400
    assert database.users_by_email == {}
