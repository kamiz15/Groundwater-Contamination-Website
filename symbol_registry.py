"""
symbol_registry.py
Central alias registry for parameter name mapping across
database columns, UI labels, and model function arguments.

RULE: Conceptual Model Symbol == UI Label == Variable Name (or mapped alias)

This module is the single source of truth for the site-database input columns.
Each canonical symbol declares the typed `sites` column that stores it (`db`),
the UI label, the unit, and the models that consume it. Derived from this:
  - SITE_COLUMN_DEFS        ordered (db_col, ui_label, unit) for the input table
  - header_to_site_column() maps an uploaded CSV header to a sites column
  - db_to_model()           maps a stored site row to one model's inputs

Adding a new model parameter is a one-line registry edit: declare the symbol
here (and add the matching column in data_queries.SCHEMA / ensure_schema), and
the upload reader, the input table, and per-model autofill all follow.
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
        "models": ["liedl", "liedl3d", "ham", "maier", "birla", "bioscreen", "numerical"],
    },
    "S_w": {
        "db": "plume_width",
        "ui": "Source Width Sw [m]",
        "unit": "m",
        "models": ["chu", "cirpka", "liedl3d", "bioscreen", "numerical"],
    },
    "L": {
        # Observed plume length. Stored and displayed; not a model input
        # (models compute Lmax), so models is empty.
        "db": "plume_length",
        "ui": "Plume Length [m]",
        "unit": "m",
        "models": [],
    },
    "S_T": {
        "db": "source_thickness",
        "ui": "Source Thickness ST [m]",
        "unit": "m",
        "models": ["numerical"],
    },
    "S_Ta": {
        "db": "source_buffer_above",
        "ui": "Buffer Above STa [m]",
        "unit": "m",
        "models": ["numerical"],
    },
    "S_Tb": {
        "db": "source_buffer_below",
        "ui": "Buffer Below STb [m]",
        "unit": "m",
        "models": ["numerical"],
    },

    # --- Transport parameters ---
    "alpha_Tv": {
        "db": "alpha_tv",
        "ui": "Transverse Dispersivity αTv [m]",
        "unit": "m",
        "models": ["liedl", "liedl3d", "maier", "birla", "numerical"],
    },
    "alpha_Th": {
        "db": "alpha_th",
        "ui": "Horizontal Transverse Dispersivity αTh [m]",
        "unit": "m",
        "models": ["chu", "liedl3d", "cirpka", "numerical"],
    },
    "alpha_T": {
        "db": "alpha_t",
        "ui": "Transverse Dispersivity αT [m]",
        "unit": "m",
        "models": ["ham"],
    },
    "K": {
        "db": "hydraulic_conductivity",
        "ui": "Hydraulic Conductivity K [m/s]",
        "unit": "m/s",
        "models": ["numerical"],
    },
    "K_v": {
        "db": "k_v",
        "ui": "Vertical Hydraulic Conductivity K_v [m/d]",
        "unit": "m/d",
        "models": ["numerical"],
    },
    "Q": {
        "db": "ham_q",
        "ui": "Specific Discharge Q [m/d]",
        "unit": "m/d",
        "models": ["ham"],
    },

    # --- Concentration parameters ---
    "C_D": {
        "db": "electron_donor",
        "ui": "Electron Donor CD [mg/L]",
        "unit": "mg/L",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "maier", "birla", "bioscreen", "numerical"],
    },
    "C_A": {
        "db": "electron_acceptor_o2",
        "ui": "Electron Acceptor CA [mg/L]",
        "unit": "mg/L",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "maier", "birla", "bioscreen", "numerical"],
    },
    "C_A_NO3": {
        # Nitrate acceptor. Stored and displayed; no model consumes it yet.
        "db": "electron_acceptor_no3",
        "ui": "Electron Acceptor NO₃ [mg/L]",
        "unit": "mg/L",
        "models": [],
    },

    # --- Stoichiometric / reaction ---
    "gamma": {
        "db": "gamma",
        "ui": "Stoichiometric Ratio γ [-]",
        "unit": "-",
        "models": ["liedl", "liedl3d", "chu", "ham", "cirpka", "maier", "birla", "numerical"],
    },
    "epsilon": {
        "db": "epsilon",
        "ui": "Threshold ε [mg/L]",
        "unit": "mg/L",
        "models": ["chu"],
    },
    "Cthres": {
        "db": "cthres",
        "ui": "Threshold Concentration Cthres [mg/L]",
        "unit": "mg/L",
        "models": ["liedl3d"],
    },
    "R": {
        "db": "birla_r",
        "ui": "Recharge Rate R [m/yr]",
        "unit": "m/yr",
        "models": ["birla"],
    },
}


# Identity / text columns. Not model inputs, but part of the site table and the
# upload header matching. Stored as VARCHAR (see data_queries).
TEXT_COLUMN_DEFS = {
    "site_unit": {
        # "Site No." is intentionally NOT an alias: it is a row index, not the
        # site name. Files that carry both "Site No." and "Site Unit" must put
        # the name (not the number) into site_unit.
        "ui": "Site unit",
        "aliases": {"site_unit", "site unit", "site name", "site"},
    },
    "compound": {
        "ui": "Compound",
        "aliases": {"compound", "contaminant"},
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
    "L": {"plume length", "plumelength"},
    "S_T": {"source thickness", "sourcethickness"},
    "S_Ta": {"buffer above", "bufferabove"},
    "S_Tb": {"buffer below", "bufferbelow"},
    "alpha_Tv": {"transverse dispersivity", "vertical transverse dispersivity", "alphatv", "tv", "atv"},
    "alpha_Th": {"horizontal transverse dispersivity", "alphath"},
    "alpha_T": {"alphat"},
    "K": {"hydraulic conductivity", "hydraulicconductivity", "k"},
    "K_v": {"vertical hydraulic conductivity", "kv"},
    "Q": {"specific discharge", "discharge", "darcy flux", "darcyflux"},
    "C_D": {"electron donor", "electrondonor", "cd"},
    "C_A": {"electron acceptor", "electronacceptor", "electron acceptor o2", "electron acceptors o2", "o2", "ca"},
    "C_A_NO3": {"no3", "nitrate", "electron acceptor no3", "electron acceptors no3", "electronacceptorno3"},
    "gamma": {"gamma", "stoichiometric ratio", "stoichiometricratio", "g"},
    "epsilon": {"epsilon", "threshold", "eps"},
    "Cthres": {"cthres", "threshold concentration", "cthreshold"},
    "R": {"recharge rate", "recharge", "rechargerate"},
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


# Ordered list of typed input columns for the site table: (db_col, ui_label, unit).
# Order follows registry declaration order (geometry -> transport -> conc -> reaction).
SITE_COLUMN_DEFS = [
    (meta["db"], meta["ui"], meta["unit"])
    for meta in SYMBOL_REGISTRY.values()
    if meta.get("db")
]

# All db columns that the upload reader may write to (text identity + typed params).
SITE_DB_COLUMNS = list(TEXT_COLUMN_DEFS.keys()) + [db for db, _ui, _unit in SITE_COLUMN_DEFS]


def _build_name_to_db_column():
    """{ normalized_header -> sites column } covering text + all typed columns."""
    lookup = {}
    for column, meta in TEXT_COLUMN_DEFS.items():
        for alias in {column, *meta["aliases"]}:
            norm = _normalize_name(alias)
            if norm and norm not in lookup:
                lookup[norm] = column
    for normalized, symbol in NAME_TO_SYMBOL.items():
        db_col = SYMBOL_REGISTRY.get(symbol, {}).get("db")
        if db_col and normalized not in lookup:
            lookup[normalized] = db_col
    # Also accept the raw db column name as a header.
    for column in SITE_DB_COLUMNS:
        norm = _normalize_name(column)
        if norm and norm not in lookup:
            lookup[norm] = column
    return lookup


NAME_TO_DB_COLUMN = _build_name_to_db_column()


def _build_strong_norms():
    """Normalized names that identify a column 'canonically' (its own name,
    symbol, or primary UI label) — as opposed to a softer descriptive alias.

    Used to resolve collisions: when two headers map to the same column, the
    canonical one wins over an alias (e.g. "Site Unit" beats a stray alias).
    """
    strong = set()
    for column, meta in TEXT_COLUMN_DEFS.items():
        strong.add(_normalize_name(column))
        strong.add(_normalize_name(meta["ui"]))
    for symbol, meta in SYMBOL_REGISTRY.items():
        strong.add(_normalize_name(symbol))
        if meta.get("db"):
            strong.add(_normalize_name(meta["db"]))
        ui = meta.get("ui") or ""
        strong.add(_normalize_name(ui.split(" [")[0]))
    strong.discard("")
    return strong


STRONG_COLUMN_NORMS = _build_strong_norms()


def header_match(header: str):
    """Return (column, is_strong) for an uploaded header.

    column is the canonical sites column the header maps to (or None). is_strong
    is True when the header matched a canonical name rather than a soft alias.
    Tries the full normalized header first, then the header with a trailing
    bracketed unit stripped (e.g. "Plume length[m]", "Hydraulic
    conductivity[10-3 [m/s]]").
    """
    if not header:
        return None, False
    for candidate in (header, header.split("[", 1)[0]):
        norm = _normalize_name(candidate)
        column = NAME_TO_DB_COLUMN.get(norm)
        if column:
            return column, norm in STRONG_COLUMN_NORMS
    return None, False


def header_to_site_column(header: str):
    """Map an uploaded CSV header to a canonical sites column, or None if unknown."""
    return header_match(header)[0]


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
