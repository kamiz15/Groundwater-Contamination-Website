"""Scenario-table multiple mode (panel_model_scenarios), wired to Liedl first."""
import math

import pandas as pd
import panel as pn
import pytest

from analytical_models import liedl_lmax
from panel_analytical_common import comparison_plot_data
from panel_model_scenarios import (
    MEASURED_COLUMN, SITE_COLUMN, measured_series, parse_trigger, read_scenario_csv,
    run_rows, scenario_app, scenario_columns, seed_rows,
)
from panel_site_comparison import MODEL_SPECS


def _site(**over):
    site = {
        "id": 1, "display_id": 1, "site_unit": "Borden", "compound": "Benzene",
        "aquifer_thickness": 4.0, "plume_length": 120.0, "plume_width": 5.0,
        "electron_donor": 5.0, "electron_acceptor_o2": 8.0,
        "alpha_tv": 0.002, "gamma": 3.5, "extra_data": {},
    }
    site.update(over)
    return site


def _frame(model, rows):
    return pd.DataFrame(rows, columns=scenario_columns(model))


def test_columns_cover_every_model_argument():
    for model, spec in MODEL_SPECS.items():
        assert set(spec["args"]) < set(scenario_columns(model))


def test_ticked_sites_seed_rows_with_their_own_values():
    rows = seed_rows("liedl", [_site()], MODEL_SPECS["liedl"]["defaults"])
    assert rows[0][SITE_COLUMN] == "Borden"
    assert rows[0]["M"] == 4.0 and rows[0]["alpha_Tv"] == 0.002
    assert rows[0][MEASURED_COLUMN] == 120.0


def test_no_sites_still_gives_one_runnable_row():
    rows = seed_rows("liedl", [], MODEL_SPECS["liedl"]["defaults"])
    assert len(rows) == 1
    _labels, lengths, _measured = run_rows("liedl", _frame("liedl", rows))
    assert math.isfinite(lengths[0])


def test_every_row_is_one_run():
    rows = seed_rows("liedl", [_site(id=1, site_unit="A"), _site(id=2, site_unit="B", aquifer_thickness=2.0)],
                     MODEL_SPECS["liedl"]["defaults"])
    labels, lengths, measured = run_rows("liedl", _frame("liedl", rows))
    assert labels == ["A", "B"]
    assert math.isclose(lengths[0], liedl_lmax(4.0, 0.002, 3.5, 8.0, 5.0))
    assert measured == [120.0, 120.0]


def test_a_blank_parameter_is_reported_not_guessed():
    rows = seed_rows("liedl", [], MODEL_SPECS["liedl"]["defaults"])
    rows[0]["alpha_Tv"] = None
    with pytest.raises(ValueError, match="Row 1"):
        run_rows("liedl", _frame("liedl", rows))


def test_rows_without_a_measurement_are_left_off_the_measured_series():
    assert measured_series([120.0, None, 30.0]) == ([1, 3], [120.0, 30.0])


def test_measured_points_reach_the_graph_on_their_own_x():
    data = comparison_plot_data(
        "Liedl et al. (2005)", "Liedl model plume length", [1, 2, 3], [80.0, 90.0, 100.0],
        0, "someone@example.com", "Scenario",
        field_points=([1, 3], [120.0, 30.0]), field_label="Measured plume length",
    )
    assert (data["field_x"], data["field_y"]) == ([1, 3], [120.0, 30.0])
    assert data["manual_x"] == [1, 2, 3]          # never re-parked past the last point
    assert data["x_label"] == "Scenario"
    assert data["field_label"] == "Measured plume length"


def test_uploaded_csv_fills_in_the_optional_columns():
    csv = b"M,alpha_Tv,gamma,C_A,C_D\n2,0.001,3.5,8,5\n3,0.001,3.5,8,5\n"
    frame = read_scenario_csv("liedl", csv)
    assert list(frame.columns) == scenario_columns("liedl")
    assert frame[SITE_COLUMN].tolist() == ["Scenario 1", "Scenario 2"]
    _labels, lengths, _measured = run_rows("liedl", frame)
    assert len(lengths) == 2


def test_uploaded_csv_missing_a_parameter_is_rejected():
    with pytest.raises(ValueError, match="alpha_Tv"):
        read_scenario_csv("liedl", b"M,gamma,C_A,C_D\n2,3.5,8,5\n")


# --- the single run button --------------------------------------------------

def test_site_ids_posted_by_the_page_are_read_back():
    assert parse_trigger('{"ids": [3, 7], "seq": 2}') == [3, 7]


@pytest.mark.parametrize("raw", ["", "not json", '{"seq": 1}', '{"ids": ["x"]}'])
def test_a_malformed_post_runs_no_sites_rather_than_crashing(raw):
    assert parse_trigger(raw) == []


def test_the_panel_carries_no_run_button_of_its_own():
    """One Run Scenarios button, and it lives on the page - not in the iframe."""
    app = scenario_app("liedl")
    names = [w.name for w in app.select(pn.widgets.Button)]

    assert not any("run" in name.lower() for name in names)
    assert names == ["+ Add row", "Clear rows", "Add scenario", "Cancel"]


def test_the_scenario_table_starts_empty_and_the_dialog_starts_closed():
    app = scenario_app("liedl")
    table = app.select(pn.widgets.Tabulator)[0]

    assert list(table.value.columns) == scenario_columns("liedl")
    assert len(table.value) == 0
    assert [c for c in app.select(pn.Column) if c.styles.get("z-index") == "20"][0].visible is False


def test_the_scenario_card_sits_below_the_graph():
    app = scenario_app("liedl")
    kinds = [type(obj).__name__ for obj in app]

    assert kinds.index("Bokeh") < kinds.index("Column")
