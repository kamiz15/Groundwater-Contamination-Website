from symbol_registry import SYMBOL_REGISTRY, header_to_site_column


def test_canonical_symbols_map_to_expected_database_columns():
    # Every model parameter now has a typed `sites` column (the catalog-driven
    # upload feature). Display-only symbols (observed plume length, nitrate)
    # also have columns but no consuming model.
    assert {
        symbol: metadata["db"]
        for symbol, metadata in SYMBOL_REGISTRY.items()
    } == {
        "M": "aquifer_thickness",
        "S_w": "plume_width",
        "L": "plume_length",
        "S_T": "source_thickness",
        "S_Ta": "source_buffer_above",
        "S_Tb": "source_buffer_below",
        "alpha_Tv": "alpha_tv",
        "alpha_Th": "alpha_th",
        "alpha_T": "alpha_t",
        "K": "hydraulic_conductivity",
        "K_v": "k_v",
        "Q": "ham_q",
        "C_D": "electron_donor",
        "C_A": "electron_acceptor_o2",
        "C_A_NO3": "electron_acceptor_no3",
        "gamma": "gamma",
        "epsilon": "epsilon",
        "Cthres": "cthres",
        "R": "birla_r",
    }


def test_header_matching_covers_new_model_parameters():
    # Headers for previously-unrecognized parameters now map to typed columns,
    # tolerating unit suffixes and alternate spellings.
    assert header_to_site_column("gamma") == "gamma"
    assert header_to_site_column("epsilon") == "epsilon"
    assert header_to_site_column("Cthres") == "cthres"
    assert header_to_site_column("alpha_Th") == "alpha_th"
    assert header_to_site_column("Plume width[m]") == "plume_width"
    assert header_to_site_column("Electron acceptors : o2[mg/l]") == "electron_acceptor_o2"
    # Genuinely unknown headers stay unmapped (routed to extra_data on upload).
    assert header_to_site_column("Porosity") is None
