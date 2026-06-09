from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


SECONDS_PER_DAY = 86400.0
DB_K_M_PER_S_TO_NUMERICAL_HK_M_PER_D = SECONDS_PER_DAY


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    value: Any
    reason: str


def _float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def vertical_validation_config() -> dict[str, float | int]:
    return {
        "hk_min": _float_env("NUMERICAL_HK_MIN_M_PER_DAY", 1e-6),
        # This upper bound is a scientific screening choice, not an engineering fact.
        # Orlando needs to sign off before treating high-K sites such as coarse gravel as invalid.
        "hk_max": _float_env("NUMERICAL_HK_MAX_M_PER_DAY", 1000.0),
        "ncol_min": _int_env("VERTICAL_NUMERICAL_NCOL_MIN", 6),
        "nlay_min": _int_env("VERTICAL_NUMERICAL_NLAY_MIN", 2),
    }


def vertical_default_inputs() -> dict[str, float | int]:
    return {
        "Lx": _float_env("VERTICAL_NUMERICAL_DEFAULT_LX", 200.0),
        "ncol": _int_env("VERTICAL_NUMERICAL_DEFAULT_NCOL", 200),
        "nlay": _int_env("VERTICAL_NUMERICAL_DEFAULT_NLAY", 20),
        "al": _float_env("VERTICAL_NUMERICAL_DEFAULT_AL", 5.0),
        "at": _float_env("VERTICAL_NUMERICAL_DEFAULT_AT", 0.2),
        "atv": _float_env("VERTICAL_NUMERICAL_DEFAULT_ATV", 0.1),
        "prsity": _float_env("VERTICAL_NUMERICAL_DEFAULT_PRSITY", 0.3),
        "gamma": _float_env("VERTICAL_NUMERICAL_DEFAULT_GAMMA", 3.5),
        "h1": _float_env("VERTICAL_NUMERICAL_DEFAULT_H1", 10.0),
        "h2": _float_env("VERTICAL_NUMERICAL_DEFAULT_H2", 9.0),
        "C0": _float_env("VERTICAL_NUMERICAL_DEFAULT_C0", 8.0),
        "perlen": _float_env("VERTICAL_NUMERICAL_DEFAULT_PERLEN", 100.0),
    }


def _as_float(value: Any, field: str) -> tuple[float | None, ValidationIssue | None]:
    if value is None:
        return None, ValidationIssue(field, value, f"{field} is required")
    try:
        return float(value), None
    except (TypeError, ValueError):
        return None, ValidationIssue(field, value, f"{field} must be numeric")


def convert_database_hk_to_m_per_day(value: Any) -> float:
    raw, issue = _as_float(value, "hydraulic_conductivity")
    if issue is not None:
        raise ValueError(issue.reason)
    hk = raw * DB_K_M_PER_S_TO_NUMERICAL_HK_M_PER_D
    config = vertical_validation_config()
    hk_min = float(config["hk_min"])
    hk_max = float(config["hk_max"])
    if hk < hk_min:
        raise ValueError(f"hk {hk:g} m/d is below min {hk_min:g} m/d")
    if hk > hk_max:
        raise ValueError(f"hk {hk:g} m/d exceeds max {hk_max:g} m/d")
    return hk


def _positive(inputs: dict[str, Any], field: str, issues: list[ValidationIssue]) -> None:
    value, issue = _as_float(inputs.get(field), field)
    if issue is not None:
        issues.append(issue)
    elif value <= 0:
        issues.append(ValidationIssue(field, inputs.get(field), f"{field} must be > 0"))


def _non_negative(inputs: dict[str, Any], field: str, issues: list[ValidationIssue]) -> None:
    value, issue = _as_float(inputs.get(field), field)
    if issue is not None:
        issues.append(issue)
    elif value < 0:
        issues.append(ValidationIssue(field, inputs.get(field), f"{field} must be >= 0"))


def validate_vertical_inputs(inputs: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    config = vertical_validation_config()

    for field in ("Lx", "Lz", "al", "at", "atv", "gamma", "perlen", "C0"):
        _positive(inputs, field, issues)
    for field in ("C_D", "C_A"):
        _non_negative(inputs, field, issues)

    prsity, issue = _as_float(inputs.get("prsity"), "prsity")
    if issue is not None:
        issues.append(issue)
    elif not 0 < prsity < 1:
        issues.append(ValidationIssue("prsity", inputs.get("prsity"), "prsity must be in (0, 1)"))

    hk, issue = _as_float(inputs.get("hk"), "hk")
    if issue is not None:
        issues.append(issue)
    else:
        hk_min = float(config["hk_min"])
        hk_max = float(config["hk_max"])
        if hk < hk_min:
            issues.append(ValidationIssue("hk", hk, f"hk {hk:g} m/d is below min {hk_min:g} m/d"))
        elif hk > hk_max:
            issues.append(ValidationIssue("hk", hk, f"hk {hk:g} m/d exceeds max {hk_max:g} m/d"))

    for field, minimum in (("ncol", int(config["ncol_min"])), ("nlay", int(config["nlay_min"]))):
        raw = inputs.get(field)
        if raw is None:
            issues.append(ValidationIssue(field, raw, f"{field} is required"))
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            issues.append(ValidationIssue(field, raw, f"{field} must be an integer"))
            continue
        if value < minimum:
            issues.append(ValidationIssue(field, raw, f"{field} must be >= {minimum}"))

    h1, h1_issue = _as_float(inputs.get("h1"), "h1")
    h2, h2_issue = _as_float(inputs.get("h2"), "h2")
    if h1_issue is not None:
        issues.append(h1_issue)
    if h2_issue is not None:
        issues.append(h2_issue)
    if h1_issue is None and h2_issue is None and h1 == h2:
        issues.append(ValidationIssue("h1/h2", f"{h1:g}/{h2:g}", "h1 and h2 must differ"))

    return issues


def vertical_inputs_from_site(site: dict[str, Any]) -> tuple[dict[str, Any], list[ValidationIssue]]:
    inputs: dict[str, Any] = dict(vertical_default_inputs())
    issues: list[ValidationIssue] = []

    lz, issue = _as_float(site.get("aquifer_thickness"), "Lz")
    if issue is not None:
        issues.append(issue)
    else:
        inputs["Lz"] = lz

    try:
        inputs["hk"] = convert_database_hk_to_m_per_day(site.get("hydraulic_conductivity"))
    except ValueError as exc:
        raw_hk = site.get("hydraulic_conductivity")
        try:
            value = float(raw_hk) * DB_K_M_PER_S_TO_NUMERICAL_HK_M_PER_D
        except (TypeError, ValueError):
            value = raw_hk
        inputs["hk"] = value
        issues.append(ValidationIssue("hk", value, str(exc)))

    cd, issue = _as_float(site.get("electron_donor"), "C_D")
    if issue is not None:
        issues.append(issue)
    else:
        inputs["C_D"] = cd

    ca, issue = _as_float(site.get("electron_acceptor_o2"), "C_A")
    if issue is not None:
        issues.append(issue)
    else:
        inputs["C_A"] = ca

    issues.extend(validate_vertical_inputs(inputs))
    deduped: list[ValidationIssue] = []
    seen = set()
    for item in issues:
        key = (item.field, str(item.value), item.reason)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return inputs, deduped


def filter_valid_vertical_sites(sites: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, list[ValidationIssue]]]:
    valid = []
    invalid: dict[int, list[ValidationIssue]] = {}
    for site in sites:
        _inputs, issues = vertical_inputs_from_site(site)
        if issues:
            invalid[int(site.get("id", -1))] = issues
        else:
            valid.append(site)
    return valid, invalid


def format_issues(issues: list[ValidationIssue]) -> str:
    return "; ".join(issue.reason for issue in issues)
