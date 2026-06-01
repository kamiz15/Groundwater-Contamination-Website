from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict, deque
from functools import wraps
import logging
from threading import Lock

from flask import abort, jsonify, request, session
from mysql.connector import Error as DatabaseError


_CSRF_SESSION_KEY = "_csrf_token"
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_rate_limit_buckets = defaultdict(deque)
_rate_limit_lock = Lock()
logger = logging.getLogger(__name__)

GENERIC_DATABASE_ERROR_MESSAGE = "Unable to access data. Please try again later."


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
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    return request.remote_addr or "unknown"


def rate_limit(limit: int, window_seconds: int):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            key = (request.endpoint or view.__name__, _client_address())
            now = time.monotonic()
            with _rate_limit_lock:
                bucket = _rate_limit_buckets[key]
                cutoff = now - window_seconds
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
