"""Shared request-parsing and error guards for model routes.

The model functions deliberately raise (ValueError etc.) on mathematically
invalid inputs. Routes that evaluate a model directly on query parameters
must translate those into a 400 instead of letting them surface as a 500.
"""

from __future__ import annotations

import math
from functools import wraps

from flask import abort, request

# Errors a model evaluation can raise on bad inputs:
# - ValueError: explicit guards and math domain errors
# - TypeError: e.g. negative base ** fractional exponent -> complex -> float()
# - ZeroDivisionError / OverflowError: degenerate or extreme parameters
MODEL_INPUT_ERRORS = (ValueError, TypeError, ZeroDivisionError, OverflowError)


def guard_model_errors(view):
    """Turn model-input errors raised inside a view into a 400 response."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except MODEL_INPUT_ERRORS as exc:
            abort(400, description=f"Invalid model inputs: {exc}")

    return wrapped


def request_finite_float(name: str, default):
    """Float query param; non-numeric and non-finite (inf/nan) fall back."""
    raw = request.args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value):
        return default
    return value


def request_finite_int(name: str, default):
    """Integer query param; non-numeric and non-finite fall back."""
    value = request_finite_float(name, None)
    if value is None:
        return default
    return int(value)
