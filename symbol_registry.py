"""
symbol_registry.py
Central alias registry for parameter name mapping across
database columns, UI labels, and model function arguments.

RULE: Conceptual Model Symbol == UI Label == Variable Name (or mapped alias)
"""

SYMBOL_REGISTRY = {
    # --- Geometric parameters ---
    "M": {
        "db": "aquifer_thickness",
        "ui": "Aquifer Thickness M [m]",
        "unit": "m",
        "models": ["liedl", "liedl3d", "ham", "maier"],
    },
    "S_w": {
        "db": "plume_width",
        "ui": "Source Width Sw [m]",
        "unit": "m",
        "models": ["chu", "cirpka", "numerical"],
    },
    "S_T": {
        "db": None,
        "ui": "Source Thickness ST [m]",
        "unit": "m",
        "models": ["numerical"],
    },
    "R_Ta": {
        "db": None,
        "ui": "Buffer Above Source R_T^a [m]",
        "unit": "m",
        "models": ["numerical"],
    },
    "R_Tb": {
        "db": None,
        "ui": "Buffer Below Source R_T^b [m]",
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
        "models": ["chu", "liedl3d", "cirpka"],
    },
    "K": {
        "db": "hydraulic_conductivity",
        "ui": "Hydraulic Conductivity K [m/s]",
        "unit": "m/s",
        "models": ["numerical"],
    },

    # --- Concentration parameters ---
    "C_D": {
        "db": "electron_donor",
        "ui": "Electron Donor CD [mg/L]",
        "unit": "mg/L",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "numerical"],
    },
    "C_A": {
        "db": "electron_acceptor_o2",
        "ui": "Electron Acceptor CA [mg/L]",
        "unit": "mg/L",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "numerical"],
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


def get_ui_label(symbol: str) -> str:
    """Return the UI-facing label for a canonical symbol."""
    entry = SYMBOL_REGISTRY.get(symbol)
    return entry["ui"] if entry else symbol


def get_unit(symbol: str) -> str:
    """Return the unit string for a canonical symbol."""
    entry = SYMBOL_REGISTRY.get(symbol)
    return entry["unit"] if entry else ""
