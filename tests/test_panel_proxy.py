"""
tests/test_panel_proxy.py

Integration tests: Panel dashboards through the Nginx reverse proxy on port 80.

Requires the Docker Compose stack to be healthy (nginx, flask, panel, db).
The suite skips automatically when http://localhost:80 is not reachable, so
it never blocks the unit-test run in CI environments without Docker.

Run these tests explicitly after `docker compose up -d`:
    pytest tests/test_panel_proxy.py -v -m integration

Evidence captured in this module:
  (a) Wrapper-page iframe src is same-origin /panel/... — no raw :5007 port.
  (b) Authenticated WebSocket handshake to /panel/<app>/ws returns 101.
  (c) Panel extension assets (/static/extensions/panel/...) return 200.
"""
from __future__ import annotations

import base64
import http.cookiejar
import json
import os
import re
import socket
import urllib.error
import urllib.request

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

_HOST = "localhost"
_PORT = 80
_BASE = f"http://{_HOST}:{_PORT}"
_TEST_EMAIL = "proxytest@cast.internal"
_TEST_PASS = "ProxyTest1!"

# Panel app used for all websocket / iframe tests.
_APP_PATH = "panel_liedl_single"
_WS_PATH = f"/panel/{_APP_PATH}/ws"


def _is_stack_running() -> bool:
    """Return True only when the Nginx proxy is reachable on port 80."""
    try:
        with socket.create_connection((_HOST, _PORT), timeout=2):
            return True
    except OSError:
        return False


def _make_opener() -> tuple[urllib.request.OpenerDirector, http.cookiejar.CookieJar]:
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    return opener, jar


def _get_csrf(opener: urllib.request.OpenerDirector, path: str = "/login") -> str:
    resp = opener.open(f"{_BASE}{path}")
    html = resp.read().decode()
    m = re.search(r'name="_csrf_token"\s+value="([^"]+)"', html)
    if not m:
        raise RuntimeError(f"CSRF token not found in {path}")
    return m.group(1)


def _register_and_login(
    opener: urllib.request.OpenerDirector,
    jar: http.cookiejar.CookieJar,
) -> str:
    """Return the Cookie header string for an authenticated session."""
    csrf = _get_csrf(opener, "/register")
    reg = json.dumps(
        {
            "username": "proxytest",
            "email": _TEST_EMAIL,
            "password": _TEST_PASS,
            "confirmPassword": _TEST_PASS,
        }
    ).encode()
    req = urllib.request.Request(
        f"{_BASE}/register",
        data=reg,
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
    )
    try:
        opener.open(req)
    except urllib.error.HTTPError:
        pass  # already registered — ignore

    csrf = _get_csrf(opener, "/login")
    login = json.dumps({"username": _TEST_EMAIL, "password": _TEST_PASS}).encode()
    req = urllib.request.Request(
        f"{_BASE}/login",
        data=login,
        headers={"Content-Type": "application/json", "X-CSRF-Token": csrf},
    )
    resp = opener.open(req)
    body = json.loads(resp.read())
    assert body.get("success"), f"Login failed: {body}"

    return "; ".join(f"{c.name}={c.value}" for c in jar)


# ── Skip marker applied to every test in this module ──────────────────────────

pytestmark = pytest.mark.integration


def _skip_if_no_stack():
    if not _is_stack_running():
        pytest.skip("Docker Compose stack not running on localhost:80")


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_cookie() -> str:
    """Register + login once per module; return the session cookie string."""
    _skip_if_no_stack()
    opener, jar = _make_opener()
    return _register_and_login(opener, jar)


@pytest.fixture(scope="module")
def authed_opener(auth_cookie) -> urllib.request.OpenerDirector:
    opener, jar = _make_opener()
    # Seed jar from the pre-authenticated cookie string
    for part in auth_cookie.split("; "):
        if "=" in part:
            name, _, value = part.partition("=")
            c = http.cookiejar.Cookie(
                version=0, name=name, value=value,
                port=None, port_specified=False,
                domain="localhost", domain_specified=False, domain_initial_dot=False,
                path="/", path_specified=True, secure=False,
                expires=None, discard=True, comment=None, comment_url=None, rest={},
            )
            jar.set_cookie(c)
    return opener


# ── (a) iframe src is same-origin /panel/... ──────────────────────────────────

def test_wrapper_page_iframe_src_is_same_origin(auth_cookie):
    """
    (a) Authenticated GET /liedl/single through port 80 must contain an iframe
    whose src starts with /panel/ and contains no raw :5007 port reference.
    """
    _skip_if_no_stack()
    opener, _ = _make_opener()
    req = urllib.request.Request(
        f"{_BASE}/liedl/single",
        headers={"Cookie": auth_cookie},
    )
    html = opener.open(req).read().decode()

    m = re.search(r'<iframe[^>]+src="([^"]+)"', html)
    assert m, "No <iframe src=...> found on wrapper page"
    src = m.group(1)

    assert src.startswith("/panel/"), (
        f"iframe src should start with /panel/ but got: {src[:80]}"
    )
    assert ":5007" not in src, (
        f"iframe src must not contain bare :5007 port: {src[:80]}"
    )
    assert "run=1" in src, "iframe src should include run=1 for auto-execution"


# ── (b) WebSocket handshake returns 101 Switching Protocols ───────────────────

def test_authenticated_websocket_upgrade_returns_101(auth_cookie):
    """
    (b) Authenticated WebSocket handshake to /panel/<app>/ws through the Nginx
    proxy on port 80 MUST receive HTTP/1.1 101 Switching Protocols.

    A 302  → session cookie not forwarded by Nginx (auth_request misconfigured).
    A 403  → origin not in PANEL_ALLOW_ORIGINS.
    A 404  → app path or /ws suffix wrong.
    Only 101 proves the full proxy pipeline is working end-to-end.
    """
    _skip_if_no_stack()
    ws_key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET {_WS_PATH} HTTP/1.1\r\n"
        f"Host: {_HOST}\r\n"
        f"Cookie: {auth_cookie}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {ws_key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        f"Origin: http://{_HOST}\r\n"
        "\r\n"
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect((_HOST, _PORT))
        sock.sendall(handshake.encode())
        raw = b""
        while b"\r\n\r\n" not in raw:
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk
    finally:
        sock.close()

    status_line = raw.split(b"\r\n")[0].decode("ascii", errors="replace")
    assert "101" in status_line, (
        f"Expected 101 Switching Protocols but got: {status_line!r}\n"
        "Diagnose: 302=cookie not forwarded, 403=origin not in PANEL_ALLOW_ORIGINS, "
        "404=wrong ws path"
    )


# ── (c) Panel extension assets return 200 through port 80 ─────────────────────

@pytest.mark.parametrize(
    "asset_path",
    [
        # Relative path resolves through /panel/ Nginx location
        "/panel/static/extensions/panel/panel.min.js",
        # Absolute /static/extensions/panel/ routed by the Nginx workaround block
        "/static/extensions/panel/bundled/reactiveesm/"
        "es-module-shims@^1.10.0/dist/es-module-shims.min.js",
    ],
)
def test_panel_extension_asset_returns_200(asset_path, auth_cookie):
    """
    (c) Panel JS extension files must be served with HTTP 200 through port 80,
    whether they are reached via the /panel/ prefix route or the explicit
    /static/extensions/panel/ Nginx workaround location.
    """
    _skip_if_no_stack()
    req = urllib.request.Request(
        f"{_BASE}{asset_path}",
        headers={"Cookie": auth_cookie},
    )
    resp = urllib.request.urlopen(req, timeout=8)
    assert resp.status == 200, (
        f"Expected 200 for {asset_path} but got {resp.status}"
    )
