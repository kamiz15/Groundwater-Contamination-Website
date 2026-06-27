"""Per-model restrictions on site-database values.

Each CAST model places mathematical restrictions on the site parameters it
reads from the site database. Examples straight from the model equations:

- Liedl et al. (2005):    divides by C_EA0            -> electron_acceptor_o2 > 0
- Liedl 3D:               raises for M, C_A, C_D <= 0 -> all three must be > 0
- Chu et al.:             C_EA0 - epsilon > 0, W^2    -> electron_acceptor_o2 > 0, plume_width > 0
- Ham et al.:             divides by C_EA0            -> electron_acceptor_o2 > 0
- Cirpka et al. (2005):   raises for Sw, Ca <= 0      -> plume_width > 0, electron_acceptor_o2 > 0
- BIOSCREEN-AT:           source geometry/conc.       -> aquifer_thickness, plume_width, electron_donor > 0
- Maier & Grathwohl:      divides by Ca, M^2          -> electron_acceptor_o2 > 0, aquifer_thickness > 0
- Birla et al.:           same denominator structure  -> electron_acceptor_o2 > 0, aquifer_thickness > 0
- Numerical (horizontal): hk band, source width       -> hydraulic_conductivity in range, plume_width > 0

Sites that violate a model's restrictions are hidden from that model's site
drop-down so they cannot be loaded for it. They are NOT deleted: they remain
in the database and stay selectable for every model whose restrictions they
satisfy.

A missing (NULL) field is not a violation: the model pages fall back to their
manual defaults for inputs the site does not provide. The vertical numerical
model keeps its own stricter filter (numerical_input_validation), which does
require the fields to be present.
"""

from __future__ import annotations

from typing import Any

from numerical_input_validation import (
    ValidationIssue,
    convert_database_hk_to_m_per_day,
)


# model -> db fields that must be > 0 when the site provides them.
# The second tuple item is the model-symbol used in the issue message.
MODEL_POSITIVE_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "liedl": (
        ("aquifer_thickness", "M"),
        ("electron_acceptor_o2", "C_A"),
    ),
    "liedl3d": (
        ("aquifer_thickness", "M"),
        ("electron_acceptor_o2", "C_A"),
        ("electron_donor", "C_D"),
    ),
    "chu": (
        ("plume_width", "W"),
        ("electron_acceptor_o2", "C_A"),
    ),
    "ham": (
        ("electron_acceptor_o2", "C_A"),
    ),
    "cirpka": (
        ("plume_width", "Sw"),
        ("electron_acceptor_o2", "C_A"),
    ),
    "bioscreen": (
        ("aquifer_thickness", "H"),
        ("plume_width", "W"),
        ("electron_donor", "c0"),
    ),
    "maier": (
        ("aquifer_thickness", "M"),
        ("electron_acceptor_o2", "Ca"),
    ),
    "birla": (
        ("aquifer_thickness", "M"),
        ("electron_acceptor_o2", "Ca"),
    ),
    "numerical_horizontal": (
        ("plume_width", "source"),
    ),
}

# Models whose pages convert the site's hydraulic conductivity into a solver
# hk and therefore inherit the configured hk band.
_HK_BOUNDED_MODELS = {"numerical_horizontal"}


def site_issues_for_model(site: dict[str, Any], model_name: str) -> list[ValidationIssue]:
    """Return the restrictions this site violates for the given model."""
    issues: list[ValidationIssue] = []

    for db_field, symbol in MODEL_POSITIVE_FIELDS.get(model_name, ()):
        raw = site.get(db_field)
        if raw is None:
            continue  # missing -> page falls back to its manual default
        try:
            value = float(raw)
        except (TypeError, ValueError):
            issues.append(ValidationIssue(db_field, raw, f"{symbol} must be numeric"))
            continue
        if value <= 0:
            issues.append(ValidationIssue(db_field, raw, f"{symbol} must be > 0"))

    if model_name in _HK_BOUNDED_MODELS and site.get("hydraulic_conductivity") is not None:
        try:
            convert_database_hk_to_m_per_day(site.get("hydraulic_conductivity"))
        except ValueError as exc:
            issues.append(
                ValidationIssue("hydraulic_conductivity", site.get("hydraulic_conductivity"), str(exc))
            )

    return issues


def filter_valid_sites_for_model(
    sites: list[dict[str, Any]], model_name: str
) -> tuple[list[dict[str, Any]], dict[int, list[ValidationIssue]]]:
    """Split sites into (usable for this model, hidden with their issues)."""
    valid: list[dict[str, Any]] = []
    invalid: dict[int, list[ValidationIssue]] = {}
    for site in sites:
        issues = site_issues_for_model(site, model_name)
        if issues:
            invalid[int(site.get("id", -1))] = issues
        else:
            valid.append(site)
    return valid, invalid
