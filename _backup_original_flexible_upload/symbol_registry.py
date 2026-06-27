"""
symbol_registry.py
Central alias registry for parameter name mapping across
database columns, UI labels, and model function arguments.

RULE: Conceptual Model Symbol == UI Label == Variable Name (or mapped alias)
"""

from numerical_input_validation import (
    DB_K_M_PER_S_TO_NUMERICAL_HK_M_PER_D,
    SECONDS_PER_DAY,
    convert_database_hk_to_m_per_day,
)


SYMBOL_REGISTRY = {
    # --- Geometric parameters ---
    "M": {
        "db": "aquifer_thickness",
        "ui": "Aquifer Thickness M [m]",
        "unit": "m",
        "models": ["liedl", "liedl3d", "ham", "maier", "bioscreen", "numerical"],
    },
    "S_w": {
        "db": "plume_width",
        "ui": "Source Width Sw [m]",
        "unit": "m",
        "models": ["chu", "cirpka", "bioscreen", "numerical"],
    },
    "S_T": {
        "db": None,
        "ui": "Source Thickness ST [m]",
        "unit": "m",
        "models": ["numerical"],
    },
    "S_Ta": {
        "db": None,
        "ui": "Buffer Above STa [m]",
        "unit": "m",
        "models": ["numerical"],
    },
    "S_Tb": {
        "db": None,
        "ui": "Buffer Below STb [m]",
        "unit": "m",
        "models": ["numerical"],
    },

    # --- Transport parameters ---
    "alpha_Tv": {
        "db": None,
        "ui": "Transverse Dispersivity \u03b1Tv [m]",
        "unit": "m",
        "models": ["liedl", "liedl3d", "numerical"],
    },
    "alpha_Th": {
        "db": None,
        "ui": "Horizontal Transverse Dispersivity \u03b1Th [m]",
        "unit": "m",
        "models": ["chu", "liedl3d", "cirpka", "numerical"],
    },
    "K": {
        "db": "hydraulic_conductivity",
        "ui": "Hydraulic Conductivity K [m/s]",
        "unit": "m/s",
        "models": ["numerical"],
    },
    "K_v": {
        "db": None,
        "ui": "Vertical Hydraulic Conductivity K_v [m/d]",
        "unit": "m/d",
        "models": ["numerical"],
    },

    # --- Concentration parameters ---
    "C_D": {
        "db": "electron_donor",
        "ui": "Electron Donor CD [mg/L]",
        "unit": "mg/L",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "bioscreen", "numerical"],
    },
    "C_A": {
        "db": "electron_acceptor_o2",
        "ui": "Electron Acceptor CA [mg/L]",
        "unit": "mg/L",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "bioscreen", "numerical"],
    },

    # --- Stoichiometric / reaction ---
    "gamma": {
        "db": None,
        "ui": "Stoichiometric Ratio \u03b3 [-]",
        "unit": "-",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "numerical"],
    },
}


def _normalize_name(s: str) -> str:
    """Lowercase and keep only alphanumerics (mirrors site_routes._normalize_header)."""
    return "".join(ch.lower() for ch in (s or "") if ch.isalnum())


# Extra accepted names per symbol, beyond the auto-derived ones (canonical symbol
# + leading token of the UI label). Values are raw strings; they get normalized
# below when building the reverse lookup.
SYMBOL_ALIASES = {
    "M": {"aquifer thickness", "aquiferthickness", "thickness"},
    "S_w": {"source width", "sourcewidth", "plume width", "plumewidth"},
    "S_T": {"source thickness", "sourcethickness"},
    "alpha_Tv": {"transverse dispersivity", "vertical transverse dispersivity", "alphatv"},
    "alpha_Th": {"horizontal transverse dispersivity", "alphath"},
    "K": {"hydraulic conductivity", "hydraulicconductivity", "k"},
    "C_D": {"electron donor", "electrondonor", "cd"},
    "C_A": {"electron acceptor", "electronacceptor", "electron acceptor o2", "ca"},
    "gamma": {"gamma", "stoichiometric ratio", "stoichiometricratio"},
}


def _build_name_to_symbol():
    """
    Build a reverse lookup { normalized_name -> canonical_symbol }.

    For each symbol we accept:
      - normalize(symbol)            e.g. "S_w" -> "sw"
      - normalize(ui label up to ' [')  e.g. "Stoichiometric Ratio γ [-]" -> leading token
      - normalize(each SYMBOL_ALIASES entry)

    Auto-derived names never clobber an explicit alias mapping that already
    points at a symbol; first writer wins to keep behavior deterministic.
    """
    lookup = {}

    def _add(name, symbol):
        norm = _normalize_name(name)
        if norm and norm not in lookup:
            lookup[norm] = symbol

    for symbol, meta in SYMBOL_REGISTRY.items():
        _add(symbol, symbol)
        ui = meta.get("ui") or ""
        # Strip the trailing unit bracket, e.g. "Aquifer Thickness M [m]" -> "Aquifer Thickness M"
        label = ui.split(" [")[0]
        _add(label, symbol)
    for symbol, aliases in SYMBOL_ALIASES.items():
        for alias in aliases:
            _add(alias, symbol)
    return lookup


NAME_TO_SYMBOL = _build_name_to_symbol()


def db_to_model(db_row: dict, model_name: str) -> dict:
    """
    Map a database site row to model input parameters,
    returning only fields relevant to the given model.
    Returns dict of { canonical_symbol: value } for non-None values.

    Fixed DB columns are mapped first (their values always win). Any
    columns stored in db_row['extra_data'] (a dict of {original_header: value})
    are then matched by normalized name to a canonical symbol; matches whose
    symbol belongs to this model and that are not already set from a fixed
    column are added as floats when convertible.

    Note: extra_data hydraulic conductivity (K) is assumed to be in m/s, the
    same convention as the fixed `hydraulic_conductivity` column, so the
    downstream db_hydraulic_conductivity_to_numerical_hk (m/s -> m/d)
    conversion continues to apply unchanged.
    """
    result = {}
    for symbol, meta in SYMBOL_REGISTRY.items():
        if model_name not in meta["models"]:
            continue
        db_col = meta.get("db")
        if db_col is None:
            continue
        value = db_row.get(db_col)
        if value is not None:
            result[symbol] = value

    extra = db_row.get("extra_data") or {}
    if isinstance(extra, dict):
        for header, value in extra.items():
            symbol = NAME_TO_SYMBOL.get(_normalize_name(header))
            if symbol is None:
                continue
            meta = SYMBOL_REGISTRY.get(symbol)
            if not meta or model_name not in meta["models"]:
                continue
            if symbol in result:
                # Fixed-column value wins; do not overwrite.
                continue
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            try:
                result[symbol] = float(value)
            except (TypeError, ValueError):
                continue
    return result


def db_hydraulic_conductivity_to_numerical_hk(value) -> float:
    """
    Convert a database hydraulic-conductivity value in m/s to numerical hk in m/d.

    The bounds intentionally flag suspicious site-linked inputs after conversion.
    They are configurable because the domain expert must confirm the accepted range.
    """
    return convert_database_hk_to_m_per_day(value)


def get_ui_label(symbol: str) -> str:
    """Return the UI-facing label for a canonical symbol."""
    entry = SYMBOL_REGISTRY.get(symbol)
    return entry["ui"] if entry else symbol


def get_unit(symbol: str) -> str:
    """Return the unit string for a canonical symbol."""
    entry = SYMBOL_REGISTRY.get(symbol)
    return entry["unit"] if entry else ""
