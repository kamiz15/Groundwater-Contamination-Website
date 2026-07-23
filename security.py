from __future__ import annotations

import hmac
import re
import secrets
import time
from collections import defaultdict, deque
from functools import wraps
import logging
from threading import Lock

from flask import abort, jsonify, request, session
from mysql.connector import Error as DatabaseError

from settings import TRUST_PROXY_HEADERS


_CSRF_SESSION_KEY = "_csrf_token"
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_rate_limit_buckets = defaultdict(deque)
_rate_limit_lock = Lock()
logger = logging.getLogger(__name__)

GENERIC_DATABASE_ERROR_MESSAGE = "Unable to access data. Please try again later."

# Credential policy. The max password length caps the work the password hasher
# does per request (a very long password is a cheap DoS against pbkdf2).
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 256
MAX_EMAIL_LENGTH = 150        # matches users.email column
MAX_USERNAME_LENGTH = 100     # matches users.username column
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(email) and len(email) <= MAX_EMAIL_LENGTH and _EMAIL_RE.match(email) is not None


def password_policy_error(password: str) -> str | None:
    """Return a human-readable reason the password is unacceptable, or None.

    Follows NIST SP 800-63B guidance: enforce a minimum length and an upper
    bound (to cap hashing cost), but do NOT impose character-composition rules,
    which push users toward weaker, predictable passwords.
    """
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be at most {MAX_PASSWORD_LENGTH} characters."
    return None


def csrf_token() -> str:
    token = session.get(_CSRF_SESSION_KEY)
    if token is None:
        token = secrets.token_urlsafe(32)
        session[_CSRF_SESSION_KEY] = token
    return token


def validate_csrf() -> None:
    expected = session.get(_CSRF_SESSION_KEY)
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("_csrf_token")
    if (
        not isinstance(expected, str)
        or not isinstance(supplied, str)
        or not hmac.compare_digest(expected, supplied)
    ):
        abort(400, description="Invalid CSRF token.")


def csrf_protect(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if request.method in _MUTATING_METHODS:
            validate_csrf()
        return view(*args, **kwargs)

    return wrapped


def json_object_or_400() -> dict:
    if not request.is_json:
        abort(400, description="Expected a JSON request body.")
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, description="Expected a JSON object.")
    return data


def form_data_or_400():
    data = request.form
    if not data:
        abort(400, description="Expected form data.")
    return data


def required_text_fields(data: dict, *fields: str) -> tuple[str, ...]:
    values = []
    for field in fields:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            abort(400, description=f"Missing required field: {field}.")
        values.append(value.strip())
    return tuple(values)


def user_safe_error(error, context: str = "Database operation failed") -> str:
    if isinstance(error, DatabaseError):
        logger.error(
            context,
            exc_info=(type(error), error, error.__traceback__),
        )
        return GENERIC_DATABASE_ERROR_MESSAGE
    return str(error)


def _client_address() -> str:
    # Only trust a proxy-supplied client IP when explicitly configured. The
    # bundled nginx sets X-Real-IP to the real connecting address and overwrites
    # any value the client tried to send, so it cannot be spoofed to evade rate
    # limiting. We deliberately do NOT trust the leftmost X-Forwarded-For entry,
    # which is fully client-controllable.
    if TRUST_PROXY_HEADERS:
        real_ip = request.headers.get("X-Real-IP", "").strip()
        if real_ip:
            return real_ip
    return request.remote_addr or "unknown"


def rate_limit(limit: int, window_seconds: int, methods: set[str] | None = None):
    """Per-IP fixed-window limit. With `methods`, only those verbs count, so a
    GET+POST route can limit uploads without throttling page views."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if methods is not None and request.method not in methods:
                return view(*args, **kwargs)
            key = (request.endpoint or view.__name__, _client_address())
            now = time.monotonic()
            with _rate_limit_lock:
                # Evict fully-expired buckets so the map does not grow without
                # bound across distinct client IPs (one entry per endpoint+IP).
                cutoff = now - window_seconds
                for stale_key in [
                    k for k, b in _rate_limit_buckets.items()
                    if not b or b[-1] <= cutoff
                ]:
                    if stale_key != key:
                        del _rate_limit_buckets[stale_key]
                bucket = _rate_limit_buckets[key]
                while bucket and bucket[0] <= cutoff:
                    bucket.popleft()
                if len(bucket) >= limit:
                    return jsonify(
                        {
                            "success": False,
                            "message": "Too many requests. Please try again later.",
                        }
                    ), 429
                bucket.append(now)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def reset_rate_limits() -> None:
    with _rate_limit_lock:
        _rate_limit_buckets.clear()
