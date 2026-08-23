"""Multiple simulation: site selection -> per-site model run -> comparison points.

Covers every analytical and empirical model, all of which share
panel_site_comparison.run_sites and the sidebar's Compare Sites checklist.
"""
import math

import panel as pn
import pytest

from analytical_models import liedl_lmax
from model_site_validation import filter_valid_sites_for_model
from panel_analytical_common import comparison_plot_data
from panel_site_comparison import MODEL_SPECS, run_sites, site_label
from symbol_registry import db_to_model

MODELS = sorted(MODEL_SPECS)


def _site(**over):
    site = {
        "id": 1, "display_id": 1, "site_unit": "Borden", "compound": "Benzene",
        "aquifer_thickness": 2.0, "plume_length": 120.0, "plume_width": 5.0,
        "hydraulic_conductivity": 1e-4, "electron_donor": 5.0,
        "electron_acceptor_o2": 8.0, "electron_acceptor_no3": None,
        "alpha_tv": 0.001, "alpha_th": 0.01, "alpha_t": 0.01, "gamma": 3.5,
        "epsilon": 0.0, "cthres": 0.5, "birla_r": 1.0, "ham_q": 5.0,
        "extra_data": {},
    }
    site.update(over)
    return site


def _fallback(model):
    return dict(MODEL_SPECS[model]["defaults"])


# --- the per-site run -------------------------------------------------------

@pytest.mark.parametrize("model", MODELS)
def test_every_model_runs_once_per_selected_site(model):
    sites = [_site(id=1, site_unit="A"), _site(id=2, site_unit="B")]
    labels, lengths, params = run_sites(model, sites, _fallback(model))

    assert labels == ["A", "B"]
    assert len(lengths) == len(params) == 2
    assert all(math.isfinite(v) and v > 0 for v in lengths)


@pytest.mark.parametrize("model", MODELS)
def test_every_report_row_maps_to_a_computed_parameter(model):
    spec = MODEL_SPECS[model]
    _labels, _lengths, params = run_sites(model, [_site()], _fallback(model))

    # A typo in a report spec would silently drop a row from the PDF.
    assert all(key in params[0] for key, _sym, _name, _unit in spec["report"])
    assert set(spec["args"]) <= set(spec["defaults"])


def test_site_columns_drive_the_run():
    site = _site(aquifer_thickness=4.0, alpha_tv=0.002)
    _labels, lengths, _params = run_sites("liedl", [site], _fallback("liedl"))
    assert math.isclose(lengths[0], liedl_lmax(4.0, 0.002, 3.5, 8.0, 5.0))


def test_null_columns_fall_back_to_the_url_values():
    site = _site(alpha_tv=None, gamma=None)
    fallback = {**_fallback("liedl"), "alpha_Tv": 0.004, "gamma": 2.0}
    _labels, lengths, _params = run_sites("liedl", [site], fallback)
    assert math.isclose(lengths[0], liedl_lmax(2.0, 0.004, 2.0, 8.0, 5.0))


def test_bioscreen_keeps_its_own_decay_and_retardation():
    # gamma/R mean different things for BIOSCREEN, so the site's stoichiometry
    # gamma and Birla recharge R must not leak into its parameters.
    mapped = db_to_model(_site(gamma=3.5, birla_r=9.0), "bioscreen")
    assert "gamma" not in mapped and "R" not in mapped


# --- labelling and plotting -------------------------------------------------

def test_sites_are_labelled_by_unit_not_number():
    assert site_label(_site(site_unit="Vejen")) == "Vejen"
    assert site_label(_site(site_unit=None, display_id=7)) == "Site 7"


def test_multiple_charts_plot_model_results_only(monkeypatch):
    """The whole site database is deliberately absent from these graphs.

    Patched, because without an account load_field_points falls back to the
    reference database - which is exactly the series that must not appear here,
    and exactly why this passed while the graphs were still drawing it.
    """
    import panel_analytical_common as common
    monkeypatch.setattr(common, "load_field_points",
                        lambda _email: ([1, 2, 3], [10.0, 20.0, 30.0]))

    data = comparison_plot_data(
        "Liedl et al. (2005)", "Liedl model plume length", [1, 2], [80.0, 90.0],
        0, "someone@example.com", "Site Number", show_database=False,
    )
    assert data["field_x"] == [] and data["field_y"] == []
    assert data["manual_y"] == [80.0, 90.0]
    assert data["x_label"] == "Site Number"
    assert "Database" not in data["caption"]


@pytest.mark.parametrize("model", MODELS)
def test_panel_plots_one_model_point_per_selected_site(model, monkeypatch):
    import panel_site_comparison as psc

    rows = [_site(id=1, display_id=1, site_unit="Borden", plume_length=120.0),
            _site(id=2, display_id=2, site_unit="Vejen", plume_length=None)]
    monkeypatch.setattr(psc, "get_user_sites_rows", lambda _email: rows)
    monkeypatch.setattr(psc, "selected_site_ids", lambda: {1, 2})   # nothing is ticked by default
    captured = {}
    real_plot = psc.comparison_plot
    monkeypatch.setattr(psc, "comparison_plot", lambda *a, **k: (captured.update(k, args=a), real_plot(*a, **k))[1])

    app = psc.site_comparison_app(model)

    assert captured["show_database"] is False         # no database dots
    assert captured["args"][2] == [1, 2]              # one x position per site
    assert len(captured["args"][3]) == 2              # one Lmax per site
    assert len(app.select(pn.pane.Bokeh)) == 1


def test_panel_plots_nothing_until_sites_are_picked(monkeypatch):
    """Landing on a multiple page starts empty, not with every site on the graph."""
    import panel_site_comparison as psc

    monkeypatch.setattr(psc, "get_user_sites_rows", lambda _email: [_site(id=1), _site(id=2)])
    monkeypatch.setattr(psc, "selected_site_ids", lambda: set())
    monkeypatch.setattr(psc, "comparison_plot", lambda *a, **k: pytest.fail("plotted with no sites picked"))

    app = psc.site_comparison_app("liedl")

    assert app.select(pn.pane.Bokeh)[0].object is None


# --- site filtering ---------------------------------------------------------

def test_sites_violating_a_models_restrictions_are_hidden():
    rows = [_site(id=1), _site(id=2, electron_acceptor_o2=0.0)]
    valid, invalid = filter_valid_sites_for_model(rows, "liedl")
    assert [s["id"] for s in valid] == [1]
    assert 2 in invalid


def test_compare_site_ids_ignores_sites_the_model_rejected():
    """A hand-edited query string must not smuggle in an unusable site."""
    import app as flask_app
    from route_guards import compare_site_ids

    usable = [{"id": 1}, {"id": 2}]
    with flask_app.app.test_request_context("/liedl/multiple?compare_sites=2&compare_sites=99"):
        assert compare_site_ids(usable) == [2]
    with flask_app.app.test_request_context("/liedl/multiple?compare_sites=99"):
        assert compare_site_ids(usable) == []          # nothing valid ticked -> none
    with flask_app.app.test_request_context("/liedl/multiple"):
        assert compare_site_ids(usable) == []          # nothing ticked -> none
    with flask_app.app.test_request_context("/liedl/multiple?compare_sites=abc"):
        assert compare_site_ids(usable) == []          # non-numeric -> none
