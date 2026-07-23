"""Turn raw CSV column names into properly typeset mathematical labels.

Uploaded columns arrive as programmer strings — ``plume_length_m``,
``alpha_Tv``, ``concentration_mgL`` — which read badly on a figure. This module
converts them to LaTeX for Bokeh axis labels and titles:

    plume_length_m    ->  $$\\mathrm{Plume\\ length}\\ [\\mathrm{m}]$$
    alpha_Tv          ->  $$\\alpha_{Tv}$$
    concentration_mgL ->  $$C\\ [\\mathrm{mg\\,L^{-1}}]$$

Bokeh only typesets LaTeX where MathJax is active, and only in axis labels and
titles — legends and hover tooltips are plain text. Use :func:`latex_label`
for the former and :func:`plain_label` for the latter.

Rendering LaTeX requires ``pn.extension("mathjax", ...)``; without it Bokeh
prints the raw TeX source, so keep that extension enabled.
"""
from __future__ import annotations

import re

# Units recognised as a trailing token, longest form first. Values are LaTeX
# fragments placed inside \mathrm{...}.
UNIT_MAP = {
    "mg_l": r"mg\,L^{-1}", "mgl": r"mg\,L^{-1}", "mg_per_l": r"mg\,L^{-1}",
    "ug_l": r"\mu g\,L^{-1}", "ugl": r"\mu g\,L^{-1}",
    "mol_l": r"mol\,L^{-1}", "moll": r"mol\,L^{-1}",
    "m_yr": r"m\,yr^{-1}", "myr": r"m\,yr^{-1}", "m_per_yr": r"m\,yr^{-1}",
    "m_d": r"m\,d^{-1}", "m_per_d": r"m\,d^{-1}",
    "m_s": r"m\,s^{-1}", "m_per_s": r"m\,s^{-1}",
    "m2": r"m^{2}", "m3": r"m^{3}",
    "m": r"m", "km": r"km", "cm": r"cm", "mm": r"mm",
    "yr": r"yr", "year": r"yr", "years": r"yr",
    "day": r"d", "days": r"d",
    "sec": r"s", "secs": r"s",
    "pct": r"\%", "percent": r"\%",
}

# Single-character unit tokens are ambiguous with variable names, so they are
# only stripped when something else remains in front of them.
_GREEK = {
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta",
    "iota", "kappa", "lambda", "mu", "nu", "xi", "rho", "sigma", "tau",
    "upsilon", "phi", "chi", "psi", "omega", "pi",
}

# Domain terms that have a conventional single-symbol form.
KNOWN_SYMBOLS = {
    "concentration": "C", "conc": "C",
    "head": "h", "hydraulic_head": "h",
    "time": "t", "temperature": "T",
    "porosity": r"\theta", "velocity": "v",
    "discharge": "q", "distance": "x", "depth": "z",
}


def _tokens(name: str) -> list[str]:
    cleaned = str(name).strip().replace("-", "_").replace(" ", "_")
    return [t for t in re.split(r"_+", cleaned) if t]


def split_unit(name: str) -> tuple[list[str], str | None]:
    """Split a column name into its name tokens and a LaTeX unit (if any)."""
    tokens = _tokens(name)
    # Try a two-token unit first (m_yr), then a single token (m).
    for n in (2, 1):
        if len(tokens) > n:
            candidate = "_".join(tokens[-n:]).lower()
            if candidate in UNIT_MAP:
                return tokens[:-n], UNIT_MAP[candidate]
    return tokens, None


def _escape_words(words: list[str]) -> str:
    """Render descriptive words as upright text with escaped spaces."""
    text = " ".join(words)
    text = text[:1].upper() + text[1:]
    return r"\mathrm{" + text.replace(" ", r"\ ") + "}"


def _symbol(token: str) -> str:
    """A single token as a maths symbol: Greek name -> command, else italic."""
    low = token.lower()
    if low in _GREEK:
        return "\\" + low
    return token


# A bare symbol carrying a numeric subscript, e.g. c0 -> c_{0}, h1 -> h_{1}.
_SYMBOL_DIGITS = re.compile(r"^([A-Za-z]{1,2})(\d+)$")


def base_latex(tokens: list[str]) -> str:
    """LaTeX for the name part of a column (no units)."""
    if not tokens:
        return ""
    first = tokens[0]
    low = first.lower()

    # A Greek letter or short symbol followed by one qualifier -> subscript,
    # e.g. alpha_Tv -> \alpha_{Tv}, L_max -> L_{max}.
    if len(tokens) == 2 and (low in _GREEK or len(first) <= 2):
        return f"{_symbol(first)}_{{{tokens[1]}}}"
    if len(tokens) == 1:
        if low in _GREEK:
            return _symbol(first)
        if low in KNOWN_SYMBOLS:
            return KNOWN_SYMBOLS[low]
        digits = _SYMBOL_DIGITS.match(first)
        if digits:
            return f"{digits.group(1)}_{{{digits.group(2)}}}"
        if len(first) <= 2:
            return first
        return _escape_words(tokens)

    # Multi-word descriptive name; collapse a known term if it stands alone.
    joined = "_".join(t.lower() for t in tokens)
    if joined in KNOWN_SYMBOLS:
        return KNOWN_SYMBOLS[joined]
    return _escape_words(tokens)


def latex_label(name: str, scale: str = "linear") -> str:
    """A Bokeh-ready ``$$...$$`` label for ``name`` under ``scale``.

    Logarithms of a dimensional quantity are written as a ratio to the unit
    (``\\ln(L/\\mathrm{m})``) so the argument is properly dimensionless.
    """
    tokens, unit = split_unit(name)
    base = base_latex(tokens)
    if not base:
        return f"$${name}$$"

    # A compound unit (mg L^-1) needs bracketing before it can be divided by
    # or raised to a power, otherwise the TeX is ambiguous or malformed.
    compound = bool(unit) and ("\\," in unit or "^" in unit)

    if scale == "linear":
        body = f"{base}\\ [\\mathrm{{{unit}}}]" if unit else base
    elif scale in ("ln", "log10"):
        op = r"\ln" if scale == "ln" else r"\log_{10}"
        if unit:
            denom = f"\\left(\\mathrm{{{unit}}}\\right)" if compound else f"\\mathrm{{{unit}}}"
            inner = f"{base}\\,/\\,{denom}"
        else:
            inner = base
        body = f"{op}\\left({inner}\\right)"
    elif scale == "inverse":
        body = f"1/{base}"
        if unit:
            wrapped = f"\\left(\\mathrm{{{unit}}}\\right)" if compound else f"\\mathrm{{{unit}}}"
            body += f"\\ [{wrapped}^{{-1}}]"
    else:
        raise ValueError(f"Unknown scale '{scale}'.")
    return f"$${body}$$"


# --------------------------------------------------------------------------- #
# Plain text, for places Bokeh will not typeset maths (legends, tooltips)
# --------------------------------------------------------------------------- #

_GREEK_UNICODE = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "kappa": "κ", "lambda": "λ",
    "mu": "μ", "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ",
    "tau": "τ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
}
_UNIT_PLAIN = {
    r"mg\,L^{-1}": "mg/L", r"\mu g\,L^{-1}": "µg/L", r"mol\,L^{-1}": "mol/L",
    r"m\,yr^{-1}": "m/yr", r"m\,d^{-1}": "m/d", r"m\,s^{-1}": "m/s",
    r"m^{2}": "m²", r"m^{3}": "m³", r"\%": "%",
}

# Unicode has subscripts for digits and *some* lowercase letters only — there
# are no uppercase subscripts at all, and b/c/d/f/g/q/w/y/z are missing.
_SUBSCRIPT_CHARS = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ",
    "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ",
    "u": "ᵤ", "v": "ᵥ", "x": "ₓ", "+": "₊", "-": "₋",
}


def _to_subscript(text: str) -> str | None:
    """Unicode subscript for ``text``, or None if any character has no form.

    Partial conversion is deliberately refused: "Tv" would become "Tᵥ", which
    looks like a typo rather than a subscript.
    """
    out = []
    for ch in text:
        sub = _SUBSCRIPT_CHARS.get(ch)
        if sub is None:
            return None
        out.append(sub)
    return "".join(out)


def _join_subscript(symbol: str, qualifier: str) -> str:
    """``symbol`` with ``qualifier`` subscripted, without leaving an underscore.

    Three cases, in order of preference:
      * fully subscriptable      -> real subscript      (L_max  -> Lₘₐₓ)
      * short and not            -> concatenated        (alpha_Tv -> αTv),
        matching the convention already used in symbol_registry.py
      * long and not             -> space separated     (t_half -> "t half"),
        since concatenating would read as one word ("thalf")
    """
    sub = _to_subscript(qualifier)
    if sub:
        return f"{symbol}{sub}"
    if len(qualifier) <= 2:
        return f"{symbol}{qualifier}"
    return f"{symbol} {qualifier}"


def _plain_symbol(latex_symbol: str) -> str:
    """Convert a LaTeX symbol from KNOWN_SYMBOLS to its plain form."""
    if latex_symbol.startswith("\\"):
        return _GREEK_UNICODE.get(latex_symbol[1:], latex_symbol)
    return latex_symbol


def plain_label(name: str, scale: str = "linear") -> str:
    """Readable label without LaTeX, for legends, tooltips and table headers.

    Mirrors :func:`base_latex`'s structure so the two stay consistent: symbols
    keep their subscripts and are never sentence-capitalised, while descriptive
    names are.
    """
    tokens, unit = split_unit(name)
    if not tokens:
        return str(name)
    first = tokens[0]
    low = first.lower()

    if len(tokens) == 2 and (low in _GREEK or len(first) <= 2):
        base = _join_subscript(_GREEK_UNICODE.get(low, first), tokens[1])
    elif len(tokens) == 1:
        if low in _GREEK:
            base = _GREEK_UNICODE.get(low, first)
        elif low in KNOWN_SYMBOLS:
            base = _plain_symbol(KNOWN_SYMBOLS[low])
        else:
            digits = _SYMBOL_DIGITS.match(first)
            if digits:
                base = _join_subscript(digits.group(1), digits.group(2))
            elif len(first) <= 2:
                base = first
            else:
                base = first[:1].upper() + first[1:]
    else:
        joined = "_".join(t.lower() for t in tokens)
        if joined in KNOWN_SYMBOLS:
            base = _plain_symbol(KNOWN_SYMBOLS[joined])
        else:
            words = " ".join(tokens)
            base = words[:1].upper() + words[1:]
    unit_plain = _UNIT_PLAIN.get(unit, unit) if unit else None

    # Bracket a unit that already contains a slash so "C / (mg/L)" stays clear.
    unit_bracketed = None
    if unit_plain:
        unit_bracketed = f"({unit_plain})" if "/" in unit_plain else unit_plain

    if scale == "linear":
        return f"{base} [{unit_plain}]" if unit_plain else base
    if scale in ("ln", "log10"):
        op = "ln" if scale == "ln" else "log₁₀"
        inner = f"{base}/{unit_bracketed}" if unit_plain else base
        return f"{op}({inner})"
    if scale == "inverse":
        return f"1/{base} [1/{unit_bracketed}]" if unit_plain else f"1/{base}"
    raise ValueError(f"Unknown scale '{scale}'.")
