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

_MODEL_CONTEXTS = {
    "panel_liedl_single": "liedl",
    "panel_liedl_multiple": "liedl",
    "panel_liedl3d_single": "liedl3d",
    "panel_liedl3d_multiple": "liedl3d",
    "panel_chu_single": "chu",
    "panel_chu_multiple": "chu",
    "panel_ham_single": "ham",
    "panel_ham_multiple": "ham",
    "panel_bioscreen_single": "bioscreen",
    "panel_bioscreen_multiple": "bioscreen",
    "panel_cirpka_single": "cirpka",
    "panel_cirpka_multiple": "cirpka",
    "panel_maier_single": "maier",
    "panel_maier_multiple": "maier",
    "panel_birla_single": "birla",
    "panel_birla_multiple": "birla",
    "panel_kohler_single": "kohler",
    "panel_kohler_multiple": "kohler",
}

_MODEL_DISPLAY_NAMES = {
    "liedl": {"M": "Source Thickness", "alpha_Tv": "Vertical Transverse Dispersivity", "C_EA0": "Acceptor Concentration at Source", "C_ED0": "Donor Concentration at Source"},
    "liedl3d": {"M": "Source Thickness", "W": "Source Width", "Cthres": "Threshold Donor Concentration", "C_EA0": "Acceptor Concentration at Source", "C_ED0": "Donor Concentration at Source"},
    "chu": {"W": "Source Width", "epsilon": "Biological Concentration Factor", "C_EA0": "Acceptor Concentration at Source", "C_ED0": "Donor Concentration at Source"},
    "ham": {"Q": "Source Flux", "alpha_T": "Horizontal Transverse Dispersivity", "C_EA0": "Acceptor Concentration at Source", "C_ED0": "Donor Concentration at Source"},
    "bioscreen": {"Cthres": "Threshold Contaminant Concentration", "time": "Simulation Time", "H": "Source Thickness", "c0": "Contamination Concentration", "W": "Source Width", "v": "Groundwater Seepage Velocity", "Df": "Diffusion Coefficient", "gamma": "Source Decay Coefficient", "lam": "First-order Decay Coefficient", "ng": "Number of Gauss Points"},
    "cirpka": {"Sw": "Source Width", "C_A": "Acceptor Concentration at Source", "C_D": "Donor Concentration at Source"},
    "maier": {"M": "Source Thickness", "g": "Stoichiometry Coefficient", "Ca": "Acceptor Concentration at Source", "Cd": "Donor Concentration at Source"},
    "birla": {"M": "Source Thickness", "g": "Stoichiometry Coefficient", "Ca": "Acceptor Concentration at Source", "Cd": "Donor Concentration at Source"},
    # gamma here is the SOURCE DECAY rate constant, not the stoichiometric
    # coefficient every other model on the site means by that name.
    "kohler": {"lam": "First-order Decay Coefficient", "v": "Groundwater Seepage Velocity", "gamma": "Source Decay Coefficient"},
}

_MODEL_SYMBOLS = {
    "liedl": {"M": "<i>T</i><sub>s</sub>"},
    "liedl3d": {"M": "<i>T</i><sub>s</sub>", "W": "<i>S</i><sub>W</sub>", "Cthres": "<i>C</i><sub>thres</sub>"},
    "chu": {"W": "<i>S</i><sub>W</sub>"},
    "ham": {"Q": "<i>W</i><sub>e</sub>", "alpha_T": "&alpha;<sub>Th</sub>"},
    "bioscreen": {"Cthres": "<i>C</i><sub>thres</sub>", "time": "<i>t</i>", "H": "<i>T</i><sub>s</sub>", "c0": "<i>C</i><sub>D</sub><sup>0</sup>", "W": "<i>S</i><sub>W</sub>", "Df": "<i>D</i><sub>f</sub>", "gamma": "&Gamma;", "lam": "&lambda;<sub>e</sub>", "ng": "<i>n</i><sub>g</sub>"},
    "cirpka": {"Sw": "<i>S</i><sub>w</sub>", "C_A": "<i>C</i><sub>A</sub><sup>0</sup>", "C_D": "<i>C</i><sub>D</sub><sup>0</sup>"},
    "maier": {"M": "<i>T</i><sub>s</sub>", "Ca": "<i>C</i><sub>A</sub><sup>0</sup>", "Cd": "<i>C</i><sub>D</sub><sup>0</sup>"},
    "birla": {"M": "<i>T</i><sub>s</sub>", "Ca": "<i>C</i><sub>A</sub><sup>0</sup>", "Cd": "<i>C</i><sub>D</sub><sup>0</sup>"},
    "kohler": {"lam": "&lambda;<sub>e</sub>", "v": "<i>v</i>", "gamma": "&Gamma;"},
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
    "liedl": {"M": "Source Thickness T_s [m]", "alpha_Tv": "Vertical Transverse Dispersivity α_Tv [m]", "gamma": "Stoichiometric Ratio γ [-]", "C_EA0": "Acceptor Concentration at Source C_A^0 [mg/L]", "C_ED0": "Donor Concentration at Source C_D^0 [mg/L]"},
    "liedl3d": {"M": "Source Thickness T_s [m]", "W": "Source Width S_W [m]", "alpha_Th": "Horizontal Transverse Dispersivity α_Th [m]", "alpha_Tv": "Vertical Transverse Dispersivity α_Tv [m]", "gamma": "Stoichiometric Ratio γ [-]", "Cthres": "Threshold Donor Concentration C_thres [mg/L]", "C_EA0": "Acceptor Concentration at Source C_A^0 [mg/L]", "C_ED0": "Donor Concentration at Source C_D^0 [mg/L]"},
    "chu": {"W": "Source Width S_W [m]", "alpha_Th": "Horizontal Transverse Dispersivity α_Th [m]", "gamma": "Stoichiometric Ratio γ [-]", "C_EA0": "Acceptor Concentration at Source C_A^0 [mg/L]", "C_ED0": "Donor Concentration at Source C_D^0 [mg/L]", "epsilon": "Biological Concentration Factor ε [mg/L]"},
    "ham": {"Q": "Source Flux Wₑ [m²/yr]", "alpha_T": "Horizontal Transverse Dispersivity α_Th [m]", "gamma": "Stoichiometric Ratio γ [-]", "C_EA0": "Acceptor Concentration at Source C_A^0 [mg/L]", "C_ED0": "Donor Concentration at Source C_D^0 [mg/L]"},
    "cirpka": {"Sw": "Source Width S_w [m]", "alpha_Th": "Horizontal Transverse Dispersivity α_Th [m]", "gamma": "Stoichiometric Ratio γ [-]", "C_A": "Acceptor Concentration at Source C_A^0 [mg/L]", "C_D": "Donor Concentration at Source C_D^0 [mg/L]"},
    "maier": {"M": "Source Thickness T_s [m]", "tv": "Vertical Transverse Dispersivity α_Tv [m]", "g": "Stoichiometry Coefficient γ [-]", "Ca": "Acceptor Concentration at Source C_A^0 [mg/L]", "Cd": "Donor Concentration at Source C_D^0 [mg/L]"},
    "birla": {"M": "Source Thickness T_s [m]", "tv": "Vertical Transverse Dispersivity α_Tv [m]", "R": "Recharge Rate R_c [m/yr]", "g": "Stoichiometry Coefficient γ [-]", "Ca": "Acceptor Concentration at Source C_A^0 [mg/L]", "Cd": "Donor Concentration at Source C_D^0 [mg/L]"},
    "numerical_vertical": {"grid_size": "Grid Spacing Δx = Δz [m]"},
    # Without this the shared fallback would head the gamma column
    # "Stoichiometry Ratio γ [-]" - the wrong quantity in the wrong unit.
    "kohler": {"lam": "First-order Decay Coefficient λ_e [1/yr]", "v": "Groundwater Seepage Velocity v [m/yr]", "gamma": "Source Decay Coefficient Γ [1/yr]"},
}


_TABLE_SYMBOL_MARKUP = {
    "Δx = Δy": "&Delta;<i>x</i> = &Delta;<i>y</i>",
    "Δx = Δz": "&Delta;<i>x</i> = &Delta;<i>z</i>",
    "C_thres": "<i>C</i><sub>thres</sub>",
    "C_A^0": "<i>C</i><sub>A</sub><sup>0</sup>",
    "C_D^0": "<i>C</i><sub>D</sub><sup>0</sup>",
    "α_Tv": "&alpha;<sub>Tv</sub>",
    "α_Th": "&alpha;<sub>Th</sub>",
    "α_L": "&alpha;<sub>L</sub>",
    "T_s": "<i>T</i><sub>s</sub>",
    "S_T": "<i>T</i><sub>s</sub>",
    "S_W": "<i>S</i><sub>W</sub>",
    "S_w": "<i>S</i><sub>w</sub>",
    "R_c": "<i>R</i><sub>c</sub>",
    "T_A": "<i>T</i><sub>A</sub>",
    "W_s": "<i>W</i><sub>s</sub>",
    "C_A": "<i>C</i><sub>A</sub>",
    "C_D": "<i>C</i><sub>D</sub>",
    "α_T": "&alpha;<sub>T</sub>",
    "λ_e": "&lambda;<sub>e</sub>",
    "Γ": "&Gamma;",
    "γ": "&gamma;",
    "v": "<i>v</i>",
    "ε": "&epsilon;",
    "q": "<i>q</i>",
}

SCENARIO_TABLE_STYLESHEETS = [
    """
    .tabulator .tabulator-header .tabulator-col .tabulator-col-content {
      padding-left: 4px;
      padding-right: 4px;
    }
    .tabulator .tabulator-header .tabulator-col .tabulator-col-content .tabulator-col-title {
      white-space: normal;
      line-height: 1.15;
    }
    """
]


def _formatted_table_title(title):
    body, separator, unit = title.rpartition(" [")
    if not separator:
        body = title
    for symbol, markup in _TABLE_SYMBOL_MARKUP.items():
        if body.endswith(f" {symbol}"):
            body = f"{body[:-len(symbol)]}{markup}"
            break
    return f"{body}{separator}{unit}"


def table_titles(columns, context=None, html=False):
    """Return display-only titles for a Panel scenario table."""
    overrides = _CONTEXT_TABLE_TITLES.get(context, {})
    titles = {
        column: overrides[column] if column in overrides else _TABLE_TITLES[column]
        for column in columns
        if column in overrides or column in _TABLE_TITLES
    }
    if html:
        return {column: _formatted_table_title(title) for column, title in titles.items()}
    return titles


def scenario_parameter_rows(dataframe, specs):
    """Build PDF input rows for every scenario using canonical display symbols."""
    return [
        {
            "symbol": symbol,
            "name": f"Scenario {scenario_no} - {name}",
            "value": row.get(column),
            "unit": unit,
        }
        for scenario_no, (_, row) in enumerate(dataframe.iterrows(), start=1)
        for column, symbol, name, unit in specs
    ]

# The vertical numerical model discretises x/z instead of x/y.
GRID_SIZE_VERTICAL_SYMBOL = "&Delta;<i>x</i> = &Delta;<i>z</i>"

# Real help text per input name goes here as it gets written.
_DESCRIPTIONS = {}


def attach_meta(field, context=None):
    """Attach symbol + description to a built input-field dict (in place)."""
    model_context = _MODEL_CONTEXTS.get(context, context)
    visible_name = (field.get("label") or "").split(" [", 1)[0]
    display_name = _MODEL_DISPLAY_NAMES.get(model_context, {}).get(
        field["name"],
        _CONTEXT_NAMES.get(
            (field["name"], visible_name),
            _DISPLAY_NAMES.get(field["name"], visible_name),
        ),
    )
    if " [" in field["label"]:
        field["label"] = display_name + " [" + field["label"].split(" [", 1)[1]
    else:
        field["label"] = display_name
    field["symbol"] = _MODEL_SYMBOLS.get(model_context, {}).get(
        field["name"],
        _CONTEXT_SYMBOLS.get(
            (field["name"], visible_name),
            _SYMBOLS.get(field["name"], ""),
        ),
    )  # empty -> template shows plain label
    field["description"] = _DESCRIPTIONS.get(field["name"], "[TODO: describe %s]" % field["name"])
    return field
