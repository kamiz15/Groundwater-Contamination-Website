from __future__ import annotations

import panel as pn

from settings import PANEL_TRUST_QUERY_EMAIL

# Header injected by the reverse proxy after it has validated the user's login
# session (see nginx `/panel/` -> auth_request -> /auth/check). The proxy always
# overwrites any client-supplied value, so this header cannot be spoofed by the
# browser. It is the ONLY trustworthy source of the caller's identity inside the
# Panel service.
_TRUSTED_EMAIL_HEADER = "X-Auth-Email"


def _query_email() -> str:
    """Read the email from the URL query string (client-controllable)."""
    try:
        req = pn.state.curdoc.session_context.request
        values = req.arguments.get("email")
        if values:
            raw = values[0]
            return (raw.decode() if isinstance(raw, bytes) else str(raw)).strip()
    except Exception:
        pass
    return ""


def authenticated_email() -> str:
    """Return the authenticated user's email for the current Panel session.

    Identity is taken from a reverse-proxy-injected, non-spoofable request header
    derived from the Flask login session - never from a client-controllable query
    parameter. This prevents one logged-in user from reading another user's site
    data by editing `?email=` in the iframe URL.

    The query-string fallback is only consulted when explicitly enabled via the
    PANEL_TRUST_QUERY_EMAIL setting, which exists for running the Panel service
    standalone in local development (no proxy in front). It defaults to off so
    production is secure by default.
    """
    try:
        req = pn.state.curdoc.session_context.request
        headers = getattr(req, "headers", None) or {}
        email = headers.get(_TRUSTED_EMAIL_HEADER)
        if isinstance(email, bytes):
            email = email.decode()
        email = (email or "").strip()
        if email:
            return email
    except Exception:
        email = ""

    if PANEL_TRUST_QUERY_EMAIL:
        return _query_email()
    return ""
