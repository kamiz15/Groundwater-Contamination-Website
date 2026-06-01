from symbol_registry import SYMBOL_REGISTRY


def test_canonical_symbols_map_to_expected_database_columns():
    assert {
        symbol: metadata["db"]
        for symbol, metadata in SYMBOL_REGISTRY.items()
    } == {
        "M": "aquifer_thickness",
        "S_w": "plume_width",
        "S_T": None,
        "S_Ta": None,
        "S_Tb": None,
        "alpha_Tv": None,
        "alpha_Th": None,
        "K": "hydraulic_conductivity",
        "K_v": None,
        "C_D": "electron_donor",
        "C_A": "electron_acceptor_o2",
        "gamma": None,
    }
