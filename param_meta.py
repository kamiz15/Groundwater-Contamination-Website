# param_meta.py
"""Shared parameter metadata: HTML notation symbol + help text per input name.

One source of truth for analytical_routes, empirical_routes and numerical_routes.
Descriptions are greppable placeholders — fill them in later.
"""

_SYMBOLS = {
    "M": "<i>T</i><sub>A</sub>",
    "H": "<i>h</i>",
    "Lz": "<i>T</i><sub>A</sub>",
    "Sw": "<i>w</i><sub>s</sub>",
    "source_thickness": "<i>W</i><sub>s</sub>",   # source WIDTH (used as Sw), capital W like the AEM designer
    "W": "<i>w</i>",
    "Q": "<i>q</i>",
    "v": "<i>v</i>",
    "R": "<i>R</i>",
    "gamma": "&gamma;",
    "g": "&gamma;",
    "epsilon": "&epsilon;",
    "lam": "&lambda;<sub>e</sub>",
    "alpha_Tv": "&alpha;<sub>Tv</sub>",
    "atv": "&alpha;<sub>Tv</sub>",
    "tv": "&alpha;<sub>Tv</sub>",
    "alpha_Th": "&alpha;<sub>Th</sub>",
    "alpha_T": "&alpha;<sub>T</sub>",
    "at": "&alpha;<sub>Th</sub>",     # numerical horizontal transverse dispersivity
    "al": "&alpha;<sub>L</sub>",
    "ax": "&alpha;<sub>L</sub>",
    "ay": "&alpha;<sub>Th</sub>",
    "az": "&alpha;<sub>Tv</sub>",
    "Ca": "<i>C</i><sub>c</sub>",
    "C_A": "<i>C</i><sub>A</sub>",
    "C_EA0": "<i>C</i><sub>A</sub><sup>0</sup>",
    "Cd": "<i>C</i><sub>r</sub>",
    "C_D": "<i>C</i><sub>D</sub>",
    "C_ED0": "<i>C</i><sub>D</sub><sup>0</sup>",
    "c0": "<i>C</i><sub>c</sub>",
    "Cthres": "<i>C</i><sub>thres</sub>",
    "prsity": "&eta;",
    "num_terms": "<i>n</i>",
    "num_cp": "<i>n</i><sub>cp</sub>",
    "ng": "<i>n</i><sub>g</sub>",
    "hk": "<i>K</i>",                 # hydraulic conductivity is conventionally capital K
    "gradient": "<i>i</i>",
    "Df": "<i>D</i><sub>f</sub>",
    "time": "<i>t</i>",
    "dom_inc": "&Delta;",
    "grid_size": "&Delta;<i>x</i> = &Delta;<i>y</i>",   # grid spacing uses Δ
    "target_Lmax": "<i>L</i><sub>max</sub>",
}

# A handful of internal parameter names are reused for different concepts.
# Resolve those by the visible field name while leaving the solver/query names
# untouched.
_CONTEXT_SYMBOLS = {
    ("R", "Recharge Rate"): "<i>R</i><sub>c</sub>",
    ("gamma", "Source Decay"): "&Gamma;",
}

_DISPLAY_NAMES = {
    "M": "Aquifer Thickness",
    "Lz": "Aquifer Thickness",
    "alpha_Tv": "Vertical Transverse Dispersivity",
    "atv": "Vertical Transverse Dispersivity",
    "tv": "Vertical Transverse Dispersivity",
    "alpha_Th": "Horizontal Transverse Dispersivity",
    "at": "Horizontal Transverse Dispersivity",
    "al": "Longitudinal Dispersivity",
    "ax": "Longitudinal Dispersivity",
    "ay": "Horizontal Transverse Dispersivity",
    "az": "Vertical Transverse Dispersivity",
    "gamma": "Stoichiometry Ratio",
    "g": "Stoichiometry Ratio",
    "C_EA0": "Acceptor Concentration at Source",
    "C_ED0": "Donor Concentration at Source",
    "C_A": "Acceptor Concentration",
    "C_D": "Donor Concentration",
    "Ca": "Contaminant Concentration",
    "Cd": "Partner Reactant Concentration",
    "c0": "General Contaminant Concentration",
    "Cthres": "Threshold Contaminant Concentration",
    "Df": "Diffusion Coefficient",
    "lam": "First-order Decay Coefficient",
}

_CONTEXT_NAMES = {
    ("gamma", "Source Decay"): "Source Decay Coefficient",
}

_TABLE_TITLES = {
    "M": "Aquifer Thickness T_A [m]",
    "Lz": "Aquifer Thickness T_A [m]",
    "W": "Source Width W [m]",
    "Sw": "Source Width S_w [m]",
    "Q": "Source Flux Q [m²/yr]",
    "source_thickness": "Source Width W_s [m]",
    "grid_size": "Grid Spacing Δx = Δy [m]",
    "alpha_Tv": "Vertical Transverse Dispersivity α_Tv [m]",
    "tv": "Vertical Transverse Dispersivity α_Tv [m]",
    "atv": "Vertical Transverse Dispersivity α_Tv [m]",
    "alpha_Th": "Horizontal Transverse Dispersivity α_Th [m]",
    "at": "Horizontal Transverse Dispersivity α_Th [m]",
    "alpha_T": "Transverse Dispersivity α_T [m]",
    "al": "Longitudinal Dispersivity α_L [m]",
    "gamma": "Stoichiometry Ratio γ [-]",
    "g": "Stoichiometry Ratio γ [-]",
    "C_EA0": "Acceptor Concentration at Source C_A^0 [mg/L]",
    "C_ED0": "Donor Concentration at Source C_D^0 [mg/L]",
    "C_A": "Acceptor Concentration C_A [mg/L]",
    "C_D": "Donor Concentration C_D [mg/L]",
    "Ca": "Contaminant Concentration C_c [mg/L]",
    "Cd": "Partner Reactant Concentration C_r [mg/L]",
    "Cthres": "Threshold Contaminant Concentration C_thres [mg/L]",
    "epsilon": "Biological Factor ε [mg/L]",
}

_CONTEXT_TABLE_TITLES = {
    "birla": {"R": "Recharge Rate R_c [m/yr]"},
    "numerical_vertical": {"grid_size": "Grid Spacing Δx = Δz [m]"},
}


def table_titles(columns, context=None):
    """Return display-only titles for a Panel scenario table."""
    overrides = _CONTEXT_TABLE_TITLES.get(context, {})
    return {
        column: overrides[column] if column in overrides else _TABLE_TITLES[column]
        for column in columns
        if column in overrides or column in _TABLE_TITLES
    }

# The vertical numerical model discretises x/z instead of x/y.
GRID_SIZE_VERTICAL_SYMBOL = "&Delta;<i>x</i> = &Delta;<i>z</i>"

# Real help text per input name goes here as it gets written.
_DESCRIPTIONS = {}


def attach_meta(field):
    """Attach symbol + description to a built input-field dict (in place)."""
    visible_name = (field.get("label") or "").split(" [", 1)[0]
    display_name = _CONTEXT_NAMES.get(
        (field["name"], visible_name),
        _DISPLAY_NAMES.get(field["name"], visible_name),
    )
    if " [" in field["label"]:
        field["label"] = display_name + " [" + field["label"].split(" [", 1)[1]
    else:
        field["label"] = display_name
    field["symbol"] = _CONTEXT_SYMBOLS.get(
        (field["name"], visible_name),
        _SYMBOLS.get(field["name"], ""),
    )  # empty -> template shows plain label
    field["description"] = _DESCRIPTIONS.get(field["name"], "[TODO: describe %s]" % field["name"])
    return field
