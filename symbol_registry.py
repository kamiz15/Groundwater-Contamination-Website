"""
symbol_registry.py
Central alias registry for parameter name mapping across
database columns, UI labels, and model function arguments.

RULE: Conceptual Model Symbol == UI Label == Variable Name (or mapped alias)
"""

from settings import NUMERICAL_HK_MAX_M_PER_DAY, NUMERICAL_HK_MIN_M_PER_DAY


SECONDS_PER_DAY = 86400.0
# Assumption pending domain-expert confirmation: DB K is stored in m/s and numerical hk uses m/d.
DB_K_M_PER_S_TO_NUMERICAL_HK_M_PER_D = SECONDS_PER_DAY


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


def db_to_model(db_row: dict, model_name: str) -> dict:
    """
    Map a database site row to model input parameters,
    returning only fields relevant to the given model.
    Returns dict of { canonical_symbol: value } for non-None values.
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
    return result


def db_hydraulic_conductivity_to_numerical_hk(value) -> float:
    """
    Convert a database hydraulic-conductivity value in m/s to numerical hk in m/d.

    The bounds intentionally flag suspicious site-linked inputs after conversion.
    They are configurable because the domain expert must confirm the accepted range.
    """
    try:
        numerical_hk = float(value) * DB_K_M_PER_S_TO_NUMERICAL_HK_M_PER_D
    except (TypeError, ValueError) as exc:
        raise ValueError("Database hydraulic conductivity K must be numeric.") from exc
    if not NUMERICAL_HK_MIN_M_PER_DAY <= numerical_hk <= NUMERICAL_HK_MAX_M_PER_DAY:
        raise ValueError(
            "Converted hydraulic conductivity hk "
            f"({numerical_hk:g} m/d) is outside the configured bounds "
            f"[{NUMERICAL_HK_MIN_M_PER_DAY:g}, {NUMERICAL_HK_MAX_M_PER_DAY:g}] m/d."
        )
    return numerical_hk


def get_ui_label(symbol: str) -> str:
    """Return the UI-facing label for a canonical symbol."""
    entry = SYMBOL_REGISTRY.get(symbol)
    return entry["ui"] if entry else symbol


def get_unit(symbol: str) -> str:
    """Return the unit string for a canonical symbol."""
    entry = SYMBOL_REGISTRY.get(symbol)
    return entry["unit"] if entry else ""
