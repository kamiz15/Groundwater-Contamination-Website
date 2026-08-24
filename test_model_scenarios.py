"""Scenario-table multiple mode (panel_model_scenarios), wired to Liedl first."""
import math

import pandas as pd
import panel as pn
import pytest

from analytical_models import liedl_lmax
from panel_analytical_common import comparison_plot_data
from panel_model_scenarios import (
    MEASURED_COLUMN, SITE_COLUMN, _default_row, column_titles, measured_series,
    read_scenario_csv, run_rows, scenario_app, scenario_columns, site_measured_points,
    site_options, visible_options,
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


def _row(model, label="Manual", **over):
    row = _default_row(model, MODEL_SPECS[model]["defaults"], label=label)
    row.update(over)
    return row


def test_a_ticked_site_contributes_its_measurement_only():
    """Parameters are typed or uploaded - the reference database carries no
    alpha_Tv or gamma, so deriving a run from a site would fabricate them."""
    xs, ys = site_measured_points([_site(), _site(id=2, plume_length=None)], start=1)

    assert (xs, ys) == ([1], [120.0])


def test_one_row_is_runnable_on_its_own():
    rows = [_row("liedl")]
    _labels, lengths, _measured = run_rows("liedl", _frame("liedl", rows))

    assert math.isfinite(lengths[0])


def test_every_row_is_one_run():
    rows = [_row("liedl", label="A", M=4.0, alpha_Tv=0.002),
            _row("liedl", label="B", M=2.0, alpha_Tv=0.002)]

    labels, lengths, _measured = run_rows("liedl", _frame("liedl", rows))

    assert labels == ["A", "B"]
    assert math.isclose(lengths[0], liedl_lmax(4.0, 0.002, 3.5, 8.0, 5.0))


def test_a_blank_parameter_is_reported_not_guessed():
    rows = [_row("liedl", alpha_Tv=None)]

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


# --- column headings and the (absent) result box -------------------------------

@pytest.mark.parametrize("model", sorted(MODEL_SPECS))
def test_columns_are_headed_with_names_and_symbols(model):
    """Raw argument keys (M, alpha_Tv) are not what the single pages show."""
    titles = column_titles(model)

    for arg in MODEL_SPECS[model]["args"]:
        assert titles[arg] != arg, f"{model}.{arg} still shows its raw key"
        assert "[" in titles[arg], f"{model}.{arg} has no unit"


def test_the_headings_match_the_single_pages():
    titles = column_titles("liedl")

    assert titles["M"] == "Source Thickness T_s [m]"
    assert titles["alpha_Tv"] == "Vertical Transverse Dispersivity α_Tv [m]"
    assert titles["gamma"] == "Stoichiometric Ratio γ [-]"


def test_a_model_param_meta_does_not_cover_still_gets_a_heading():
    """BIOSCREEN is not in the table-title map; its own spec supplies the words."""
    titles = column_titles("bioscreen")

    assert titles["Cthres"] == "Threshold Contaminant Concentration C_thres [mg/L]"
    assert titles["v"] == "Groundwater Seepage Velocity v [m/yr]"


def test_the_stored_columns_stay_canonical():
    """Only the heading changes - an uploaded CSV still carries the real keys."""
    assert scenario_columns("liedl") == [SITE_COLUMN, "M", "alpha_Tv", "gamma",
                                         "C_A", "C_D", MEASURED_COLUMN]


def test_a_sites_only_run_still_exports_its_graph():
    """No model row is not nothing: the measured points on the graph are the
    report, or the Download PDF button has nothing to offer."""
    from unittest.mock import patch
    import panel_model_scenarios as psm

    sites = [_site(id=1, site_unit="Hill AFB", plume_length=502.92),
             _site(id=2, site_unit="No measurement", plume_length=None)]

    with patch.object(psm, "get_user_sites_rows", return_value=sites),          patch.object(psm, "filter_valid_sites_for_model", side_effect=lambda r, _m: (r, {})),          patch.object(psm, "selected_site_ids", return_value={1, 2}),          patch.object(psm, "authenticated_email", return_value="u@e.com"):
        app = psm.scenario_app("liedl")

    assert len(app.select(pn.widgets.Tabulator)[0].value) == 0        # nothing modelled
    posted = [str(p.object) for p in app.select(pn.pane.HTML) if "cast-report" in str(p.object)]
    assert posted, "a measured-only run posted no report"
    assert "Hill AFB" in posted[0]
    assert "No measurement" not in posted[0]     # a site without one is not a row


def test_the_panel_reports_its_height_to_the_page():
    """The graph is last: a frame that cannot grow cuts it off completely."""
    app = scenario_app("liedl")
    panes = [str(p.object) for p in app.select(pn.pane.HTML)]

    assert any("cast-frame-height" in html for html in panes)


def test_the_page_listens_for_the_height_it_posts():
    """Both halves of the contract, or the frame silently never resizes."""
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "static" / "script.js"
    body = script.read_text(encoding="utf-8", errors="replace")

    assert 'data.type !== "cast-frame-height"' in body
    assert "f.contentWindow === event.source" in body          # only our own frames


@pytest.mark.parametrize("caption", ["Download Sample File", "Upload", "Run Scenarios"])
def test_the_action_buttons_wear_the_site_blue(caption):
    """The outcome, not the mechanism: button_type="primary" takes the colour
    from panel_theme and keeps its radius, padding and shadow, which a private
    stylesheet would replace."""
    app = scenario_app("liedl")

    widget = next(w for w in app.select()
                  if getattr(w, "label", None) == caption or getattr(w, "name", None) == caption)

    branded = (widget.button_type == "primary"
               or any("#155da9" in sheet for sheet in widget.stylesheets))
    assert branded, f"{caption} is not branded"


def test_the_file_picker_wears_the_site_blue():
    app = scenario_app("liedl")
    picker = app.select(pn.widgets.FileInput)[0]

    assert any("file-selector-button" in sheet and "#155da9" in sheet
               for sheet in picker.stylesheets)


def test_the_panel_opens_with_no_result_box():
    app = scenario_app("liedl")
    status = app.select(pn.pane.HTML)[0]

    assert status.object == ""


# --- the site picker on the card ---------------------------------------------

def test_sites_sharing_a_unit_name_stay_apart_in_the_picker():
    options = site_options([_site(id=1, site_unit="Borden"),
                            _site(id=2, display_id=2, site_unit="Borden")])

    assert sorted(options.values()) == [1, 2]      # neither site is swallowed


def test_filtering_never_unpicks_a_site():
    options = {"Borden": 1, "Vejen": 2, "Hill AFB": 3}

    visible = visible_options(options, "vej", picked=[1])

    assert visible == {"Borden": 1, "Vejen": 2}    # the match, plus what is picked


def test_the_panel_owns_its_run_button():
    """The page has no sidebar any more, so Run Scenarios lives in here."""
    app = scenario_app("liedl")
    names = [w.name for w in app.select(pn.widgets.Button)]

    assert "Run Scenarios" in names


# --- the toolbar --------------------------------------------------------------

TOOLBAR = ["Download Sample File", "Upload", "Delete table data", "Add Data",
           "Copy", "CSV", "Excel", "PDF", "Print"]


def _labels(app):
    """Button captions in document order (FileDownload labels, Button names)."""
    out = []
    for widget in app.select():
        if isinstance(widget, pn.widgets.FileDownload):
            out.append(widget.label)
        elif isinstance(widget, pn.widgets.Button):
            out.append(widget.name)
    return out


def test_the_whole_old_cast_toolbar_is_present():
    labels = _labels(scenario_app("liedl"))

    for caption in TOOLBAR:
        assert caption in labels, f"{caption} is missing from the toolbar"


def test_the_toolbar_sits_above_the_site_picker():
    """It must hold its place whether or not a graph has been drawn."""
    app = scenario_app("liedl")
    flat = list(app.select())

    picker = flat.index(app.select(pn.widgets.MultiSelect)[0])
    for caption in TOOLBAR:
        position = next(i for i, w in enumerate(flat)
                        if getattr(w, "label", None) == caption or getattr(w, "name", None) == caption)
        assert position < picker, f"{caption} is below the site picker"


def test_no_toolbar_button_is_hidden_before_a_run():
    """Nothing waits for a run to appear - that is how they used to vanish."""
    app = scenario_app("liedl")

    for widget in app.select():
        caption = getattr(widget, "label", None) or getattr(widget, "name", None)
        if caption in TOOLBAR:
            assert widget.visible is not False, f"{caption} starts hidden"


@pytest.mark.parametrize("export", ["csv", "excel", "pdf"])
def test_the_exports_write_a_real_file_before_any_run(export):
    """Exporting must work on the rows as they stand, not only after a run."""
    from panel_model_scenarios import _csv_bytes, _excel_bytes, _pdf_bytes

    frame = _frame("liedl", [{SITE_COLUMN: "Borden", "M": 2.0, "alpha_Tv": 0.001,
                              "gamma": 3.5, "C_A": 8.0, "C_D": 5.0,
                              MEASURED_COLUMN: 120.0}])
    writer = {"csv": _csv_bytes, "excel": _excel_bytes,
              "pdf": lambda f: _pdf_bytes(f, "Liedl - Scenarios")}[export]

    data = writer(frame).getvalue()

    assert len(data) > 0
    if export == "pdf":
        assert data.startswith(b"%PDF")
    if export == "excel":
        assert data.startswith(b"PK")          # xlsx is a zip


@pytest.mark.parametrize("model", sorted(MODEL_SPECS))
def test_every_model_builds_this_panel(model):
    """All eight multiple pages run through here now, not just Liedl."""
    app = scenario_app(model)

    assert app.select(pn.widgets.Tabulator)[0].value.columns.tolist() == scenario_columns(model)
    assert "Run Scenarios" in [w.name for w in app.select(pn.widgets.Button)]


def test_the_picker_starts_empty_when_the_url_names_no_sites():
    app = scenario_app("liedl")
    picker = app.select(pn.widgets.MultiSelect)[0]

    assert picker.value == []


def test_the_scenario_table_starts_empty_and_the_dialog_starts_closed():
    app = scenario_app("liedl")
    table = app.select(pn.widgets.Tabulator)[0]

    assert list(table.value.columns) == scenario_columns("liedl")
    assert len(table.value) == 0
    assert [c for c in app.select(pn.Column) if c.styles.get("z-index") == "20"][0].visible is False


def test_the_graph_sits_below_the_scenario_card():
    """Inputs first: drawing a graph must never move the controls above it."""
    app = scenario_app("liedl")
    kinds = [type(obj).__name__ for obj in app]

    assert kinds.index("Column") < kinds.index("Bokeh")
