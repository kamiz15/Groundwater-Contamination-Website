"""Unit tests for data_analysis.notation — column names to typeset labels."""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from data_analysis import notation


@pytest.mark.parametrize("column,expected", [
    ("x_m", r"$$x\ [\mathrm{m}]$$"),
    ("plume_length_m", r"$$L_{p}\ [\mathrm{m}]$$"),
    ("alpha_Tv", r"$$\alpha_{Tv}$$"),
    ("L_max", r"$$L_{max}$$"),
    ("aquifer_type", r"$$\mathrm{Aquifer\ type}$$"),
])
def test_latex_labels(column, expected):
    assert notation.latex_label(column) == expected


def test_known_symbol_and_unit():
    # General contaminant concentration follows the site-wide C_c notation.
    assert notation.latex_label("concentration_mgL") == r"$$C_{c}\ [\mathrm{mg\,L^{-1}}]$$"


@pytest.mark.parametrize("label,expected", [
    ("Aquifer Thickness T_A [m]", r"$$T_{A}\ [\mathrm{m}]$$"),
    ("Plume Length L_p [m]", r"$$L_{p}\ [\mathrm{m}]$$"),
    ("Donor Concentration C_D [mg/L]", r"$$C_{D}\ [\mathrm{mg\,L^{-1}}]$$"),
    ("Recharge Rate R_c [m/yr]", r"$$R_{c}\ [\mathrm{m\,yr^{-1}}]$$"),
    ("Stoichiometry Ratio \u03b3 [-]", "$$\u03b3\\ [-]$$"),
])
def test_database_display_labels_keep_their_mathematical_symbols(label, expected):
    assert notation.latex_label(label) == expected
    assert notation.plain_label(label) == label


def test_numeric_subscript():
    assert notation.latex_label("c0") == r"$$c_{0}$$"
    assert notation.plain_label("c0") == "c₀"
    assert notation.plain_label("h1") == "h₁"


def test_greek_is_not_sentence_capitalised():
    # Regression: "alpha_T" must not render as "Α T".
    assert notation.plain_label("alpha_T") == "αT"


def test_plain_labels_never_contain_underscores():
    # The whole point of the notation layer: no raw programmer underscores.
    for column in ["alpha_Tv", "L_max", "c0", "S_w", "K_h", "t_half",
                   "plume_length_m", "concentration_mgL", "aquifer_type"]:
        for scale in ["linear", "ln", "log10", "inverse"]:
            assert "_" not in notation.plain_label(column, scale), (column, scale)


def test_real_subscripts_used_where_unicode_allows():
    assert notation.plain_label("L_max") == "Lₘₐₓ"   # m, a, x all exist
    assert notation.plain_label("K_h") == "Kₕ"


def test_falls_back_when_subscript_unavailable():
    # No uppercase subscripts exist, so concatenate like symbol_registry does.
    assert notation.plain_label("alpha_Tv") == "αTv"
    assert notation.plain_label("S_w") == "Sw"
    # Longer qualifiers get a space rather than reading as one word.
    assert notation.plain_label("t_half") == "t half"


def test_unit_splitting():
    tokens, unit = notation.split_unit("velocity_m_yr")
    assert tokens == ["velocity"]
    assert unit == r"m\,yr^{-1}"


def test_bare_name_has_no_unit():
    tokens, unit = notation.split_unit("aquifer_type")
    assert tokens == ["aquifer", "type"]
    assert unit is None


def test_single_letter_column_not_mistaken_for_unit():
    # "m" alone is the whole name, so it must not be stripped as a unit.
    tokens, unit = notation.split_unit("m")
    assert tokens == ["m"]
    assert unit is None


def test_log_scale_divides_by_unit():
    # ln of a dimensional quantity is written as a ratio to its unit.
    label = notation.latex_label("plume_length_m", "ln")
    assert r"\ln" in label
    assert r"\,/\,\mathrm{m}" in label


def test_compound_unit_is_bracketed_under_log():
    label = notation.latex_label("concentration_mgL", "log10")
    assert r"\log_{10}" in label
    assert r"\left(\mathrm{mg\,L^{-1}}\right)" in label


def test_inverse_brackets_compound_unit():
    # Must not produce the malformed \mathrm{mg\,L^{-1}}^{-1}.
    label = notation.latex_label("concentration_mgL", "inverse")
    assert r"\left(\mathrm{mg\,L^{-1}}\right)^{-1}" in label


def test_inverse_simple_unit():
    assert notation.latex_label("x_m", "inverse") == r"$$1/x\ [\mathrm{m}^{-1}]$$"


def test_plain_labels_have_no_latex():
    for column in ["x_m", "plume_length_m", "concentration_mgL", "alpha_Tv"]:
        for scale in ["linear", "ln", "log10", "inverse"]:
            out = notation.plain_label(column, scale)
            assert "\\" not in out and "$$" not in out, (column, scale, out)


def test_plain_compound_unit_is_bracketed():
    assert notation.plain_label("concentration_mgL", "ln") == "ln(Cc/(mg/L))"


def test_unknown_scale_raises():
    with pytest.raises(ValueError, match="Unknown scale"):
        notation.latex_label("x_m", "sqrt")
    with pytest.raises(ValueError, match="Unknown scale"):
        notation.plain_label("x_m", "sqrt")
