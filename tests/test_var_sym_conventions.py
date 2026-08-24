from param_meta import attach_meta, table_titles
from symbol_registry import SYMBOL_REGISTRY, ui_label_markup


def _field(name, label):
    return attach_meta({"name": name, "label": label})


def _model_field(context, name, label):
    return attach_meta({"name": name, "label": label}, context=context)


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


def test_model_pages_use_about_page_names_and_symbols():
    cases = [
        ("panel_liedl_single", "M", "Aquifer Thickness [m]", "Source Thickness [m]", "<i>T</i><sub>s</sub>"),
        ("panel_chu_single", "W", "Source Width [m]", "Source Width [m]", "<i>S</i><sub>W</sub>"),
        ("panel_ham_single", "alpha_T", "Transverse Dispersivity [m]", "Horizontal Transverse Dispersivity [m]", "&alpha;<sub>Th</sub>"),
        ("panel_cirpka_single", "C_A", "Electron Acceptor [mg/L]", "Acceptor Concentration at Source [mg/L]", "<i>C</i><sub>A</sub><sup>0</sup>"),
        ("panel_maier_single", "Ca", "Contaminant Concentration [mg/L]", "Acceptor Concentration at Source [mg/L]", "<i>C</i><sub>A</sub><sup>0</sup>"),
        ("panel_birla_single", "Cd", "Reactant Concentration [mg/L]", "Donor Concentration at Source [mg/L]", "<i>C</i><sub>D</sub><sup>0</sup>"),
        ("panel_bioscreen_single", "c0", "Source Concentration [mg/L]", "Contamination Concentration [mg/L]", "<i>C</i><sub>D</sub><sup>0</sup>"),
    ]

    for context, name, label, expected_label, expected_symbol in cases:
        field = _model_field(context, name, label)
        assert field["label"] == expected_label
        assert field["symbol"] == expected_symbol


def test_multiple_table_headers_follow_about_pages():
    assert table_titles(["M", "alpha_Tv", "C_ED0"], context="liedl") == {
        "M": "Source Thickness T_s [m]",
        "alpha_Tv": "Vertical Transverse Dispersivity α_Tv [m]",
        "C_ED0": "Donor Concentration at Source C_D^0 [mg/L]",
    }
    assert table_titles(["Q", "alpha_T"], context="ham") == {
        "Q": "Source Flux q [m²/yr]",
        "alpha_T": "Horizontal Transverse Dispersivity α_Th [m]",
    }
    assert table_titles(["M", "Ca", "Cd", "R"], context="birla") == {
        "M": "Source Thickness T_s [m]",
        "Ca": "Acceptor Concentration at Source C_A^0 [mg/L]",
        "Cd": "Donor Concentration at Source C_D^0 [mg/L]",
        "R": "Recharge Rate R_c [m/yr]",
    }
    assert table_titles(["g"], context="maier") == {
        "g": "Stoichiometry Coefficient γ [-]"
    }
    assert table_titles(["M", "C_ED0"], context="liedl", html=True) == {
        "M": "Source Thickness <i>T</i><sub>s</sub> [m]",
        "C_ED0": "Donor Concentration at Source <i>C</i><sub>D</sub><sup>0</sup> [mg/L]",
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
