"""The shipped reference database stands in for sites the user has not uploaded."""

import data_queries


def test_reference_rows_are_shaped_like_database_rows():
    rows = data_queries.reference_sites_rows()
    assert rows, "reference database parsed to no rows"
    first = rows[0]
    assert first["id"] == 1 and first["display_id"] == 1
    assert first["site_unit"] == "Hill AFB,UT,site 870"
    assert first["compound"] == "BTEX"
    assert first["aquifer_thickness"] == 7.62
    assert first["electron_acceptor_o2"] == 5.9
    # "Hydraulic conductivity[10-3 [m/s]]" declares its own scale: 0.0004 -> 4e-7 m/s.
    assert abs(first["hydraulic_conductivity"] - 4e-7) < 1e-12
    # Unmatched columns stay available for autofill, keyed by their CSV header.
    assert first["extra_data"]["Country"] == "USA"
    # Every stored column is present, so a model can read a reference row blindly.
    assert set(data_queries.SITE_FIELDS) <= set(first)


def test_reference_rows_are_independent_copies():
    first = data_queries.reference_sites_rows()[0]
    first["site_unit"] = "mutated"
    first["extra_data"]["Country"] = "mutated"
    fresh = data_queries.reference_sites_rows()[0]
    assert fresh["site_unit"] == "Hill AFB,UT,site 870"
    assert fresh["extra_data"]["Country"] == "USA"


def test_models_fall_back_to_the_reference_database(monkeypatch):
    monkeypatch.setattr(data_queries, "get_owned_sites_rows", lambda _email: [])
    rows = data_queries.get_user_sites_rows("nobody@example.com")
    assert len(rows) == len(data_queries.reference_sites_rows())
    # The legacy list-of-lists view used by the plot pages follows along.
    assert len(data_queries.get_user_sites("nobody@example.com")) == len(rows)


def test_uploaded_sites_win_over_the_reference_database(monkeypatch):
    mine = [{"id": 41, "site_unit": "Mine", "extra_data": {}}]
    monkeypatch.setattr(data_queries, "get_owned_sites_rows", lambda _email: mine)
    assert data_queries.get_user_sites_rows("me@example.com") == mine
