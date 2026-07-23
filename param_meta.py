# param_meta.py
"""Shared parameter metadata: HTML notation symbol + help text per input name.

One source of truth for analytical_routes, empirical_routes and numerical_routes.
Descriptions are greppable placeholders — fill them in later.
"""

_SYMBOLS = {
    "M": "<i>m</i>",
    "H": "<i>h</i>",
    "Lz": "<i>M</i>",                 # numerical vertical aquifer thickness (matches the Liedl formula M)
    "Sw": "<i>w</i><sub>s</sub>",
    "source_thickness": "<i>W</i><sub>s</sub>",   # source WIDTH (used as Sw), capital W like the AEM designer
    "W": "<i>w</i>",
    "Q": "<i>q</i>",
    "v": "<i>v</i>",
    "R": "<i>r</i>",
    "gamma": "&gamma;",
    "g": "&gamma;",
    "epsilon": "&epsilon;",
    "lam": "&lambda;",
    "alpha_Tv": "&alpha;<sub>Tv</sub>",
    "atv": "&alpha;<sub>Tv</sub>",
    "tv": "&alpha;<sub>Tv</sub>",
    "alpha_Th": "&alpha;<sub>Th</sub>",
    "alpha_T": "&alpha;<sub>T</sub>",
    "at": "&alpha;<sub>Th</sub>",     # numerical horizontal transverse dispersivity
    "al": "&alpha;<sub>L</sub>",
    "ax": "&alpha;<sub>x</sub>",
    "ay": "&alpha;<sub>y</sub>",
    "az": "&alpha;<sub>z</sub>",
    "Ca": "<i>c</i><sub>A</sub>",
    "C_A": "<i>c</i><sub>A</sub>",
    "C_EA0": "<i>c</i><sub>A</sub>",
    "Cd": "<i>c</i><sub>D</sub>",
    "C_D": "<i>c</i><sub>D</sub>",
    "C_ED0": "<i>c</i><sub>D</sub>",
    "c0": "<i>c</i><sub>0</sub>",
    "Cthres": "<i>c</i><sub>thres</sub>",
    "prsity": "<i>n</i>",
    "num_terms": "<i>n</i>",
    "num_cp": "<i>n</i><sub>cp</sub>",
    "ng": "<i>n</i><sub>g</sub>",
    "hk": "<i>K</i>",                 # hydraulic conductivity is conventionally capital K
    "gradient": "<i>i</i>",
    "Df": "<i>d</i><sub>f</sub>",
    "time": "<i>t</i>",
    "dom_inc": "&Delta;",
    "grid_size": "&Delta;<i>x</i> = &Delta;<i>y</i>",   # grid spacing uses Δ
    "target_Lmax": "<i>L</i><sub>max</sub>",
}

# The vertical numerical model discretises x/z instead of x/y.
GRID_SIZE_VERTICAL_SYMBOL = "&Delta;<i>x</i> = &Delta;<i>z</i>"

# Real help text per input name goes here as it gets written.
_DESCRIPTIONS = {}


def attach_meta(field):
    """Attach symbol + description to a built input-field dict (in place)."""
    field["symbol"] = _SYMBOLS.get(field["name"], "")  # empty -> template shows plain label
    field["description"] = _DESCRIPTIONS.get(field["name"], "[TODO: describe %s]" % field["name"])
    return field
