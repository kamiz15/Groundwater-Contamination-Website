from param_meta import attach_meta, table_titles
from symbol_registry import SYMBOL_REGISTRY, ui_label_markup


def _field(name, label):
    return attach_meta({"name": name, "label": label})


def test_site_fields_follow_variable_symbol_reference():
    assert _field("M", "Aquifer thickness [m]")["symbol"] == "<i>T</i><sub>A</sub>"
    assert _field("C_EA0", "Electron acceptor [mg/L]")["symbol"] == (
        "<i>C</i><sub>A</sub><sup>0</sup>"
    )
    assert _field("C_ED0", "Electron donor [mg/L]")["symbol"] == (
        "<i>C</i><sub>D</sub><sup>0</sup>"
    )
    assert _field("lam", "Decay coefficient [1/yr]")["symbol"] == "&lambda;<sub>e</sub>"
    assert _field("prsity", "Porosity [-]")["symbol"] == "&eta;"


def test_context_specific_symbols_are_not_confused():
    assert _field("R", "Recharge Rate [m/yr]")["symbol"] == "<i>R</i><sub>c</sub>"
    assert _field("gamma", "Source Decay [1/yr]")["symbol"] == "&Gamma;"


def test_scenario_tables_use_the_same_display_notation():
    assert table_titles(["R"], context="birla") == {"R": "Recharge Rate R_c [m/yr]"}
    assert table_titles(["grid_size"], context="numerical_vertical") == {
        "grid_size": "Grid Spacing \u0394x = \u0394z [m]"
    }


def test_site_database_labels_use_reference_symbols():
    assert SYMBOL_REGISTRY["M"]["ui"] == "Aquifer Thickness T_A [m]"
    assert SYMBOL_REGISTRY["S_w"]["ui"] == "Plume Width W_p [m]"
    assert SYMBOL_REGISTRY["L"]["ui"] == "Plume Length L_p [m]"
    assert SYMBOL_REGISTRY["C_D"]["ui"] == "Donor Concentration C_D [mg/L]"
    assert SYMBOL_REGISTRY["C_A"]["ui"] == "Acceptor Concentration C_A [mg/L]"
    assert SYMBOL_REGISTRY["R"]["ui"] == "Recharge Rate R_c [m/yr]"
    assert SYMBOL_REGISTRY["alpha_Tv"]["ui"] == (
        "Vertical Transverse Dispersivity \u03b1_Tv [m]"
    )
    assert SYMBOL_REGISTRY["C_A_NO3"]["ui"] == (
        "Acceptor Concentration C_A (NO\u2083) [mg/L]"
    )
    assert SYMBOL_REGISTRY["Cthres"]["ui"] == (
        "Threshold Concentration C_thres [mg/L]"
    )


def test_database_labels_render_mathematical_subscripts():
    assert ui_label_markup("Aquifer Thickness T_A [m]") == (
        "Aquifer Thickness <i>T</i><sub>A</sub> [m]"
    )
    assert ui_label_markup("Vertical Hydraulic Conductivity K_v [m/d]") == (
        "Vertical Hydraulic Conductivity <i>K</i><sub>v</sub> [m/d]"
    )
