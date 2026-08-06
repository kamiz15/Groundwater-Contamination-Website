"""Bounds and baseline-chip logic for the explore sliders under each plot."""

import panel as pn

from panel_analytical_common import _held_y_range, _slider_bounds, baseline_delta
from panel_theme import apply_theme


def _data(manual_y, field_y=()):
    return {"manual_y": list(manual_y), "field_y": list(field_y)}


def test_frame_holds_still_so_the_point_can_move():
    frame = {}
    first = _held_y_range(_data([2812.58]), frame)
    # Sliding the model down must not refit the axis around the new value.
    assert _held_y_range(_data([1400.0]), frame) == first
    assert _held_y_range(_data([3600.0]), frame) == first


def test_frame_widens_rather_than_hiding_the_point():
    frame = {}
    _low, high = _held_y_range(_data([100.0]), frame)
    new_low, new_high = _held_y_range(_data([500.0]), frame)
    assert new_high > high >= 130.0
    assert new_high >= 500.0
    assert new_low == 0.0


def test_manual_point_sits_past_the_last_site_when_no_site_is_loaded():
    from panel_analytical_common import comparison_plot_data
    import panel_analytical_common as common

    original = common.load_field_points
    common.load_field_points = lambda email: ([1, 2, 3], [40.0, 55.0, 61.0])
    try:
        data = comparison_plot_data("t", "model", [1], [50.0], 0, "", "Run Number")
        assert data["x_label"] == "Site Number"
        assert data["field_y"] == [40.0, 55.0, 61.0]   # database series always drawn
        assert data["manual_x"] == [4]                 # not colliding with site 1

    finally:
        common.load_field_points = original


def test_selected_site_plots_at_its_position_not_its_primary_key():
    # Site rows carry database ids in the thousands while the axis counts
    # positions, so passing the id through threw the marker off the chart.
    from panel_analytical_common import comparison_plot_data
    import panel_analytical_common as common

    rows = [
        [1577, "Borden", "BTEX", 3.0, 40.0],
        [1699, "Eglin AFB", "BTEX", 7.6, 55.0],
        [1701, "Third site", "BTEX", 4.0, 61.0],
    ]
    original_sites = common.get_user_sites
    original_points = common.load_field_points
    common.get_user_sites = lambda email: rows
    common.load_field_points = lambda email: ([1, 2, 3], [40.0, 55.0, 61.0])
    try:
        data = comparison_plot_data("t", "model", [1699], [42162.0], 1699, "", "Run Number")
        assert data["manual_x"] == [2]     # Eglin is the 2nd site, not tick 1699

        # An id that is not in the list leaves the caller's x untouched rather
        # than inventing a position.
        missing = comparison_plot_data("t", "model", [99], [42162.0], 99, "", "Run Number")
        assert missing["manual_x"] == [99]
    finally:
        common.get_user_sites = original_sites
        common.load_field_points = original_points


def test_model_dot_is_green_and_only_sites_carry_the_hover():
    # Dark green vs amber: opposite hue plus a wide lightness gap, so the pair
    # survives a projector and red-green colour blindness. The old two-blues
    # pairing separated on lightness alone.
    # The tooltip stays off the model renderer: on a manual run that point is
    # parked past the last site, so "Site N" there would name a site that is
    # not the one it sits next to.
    from bokeh.models import HoverTool
    from panel_analytical_common import comparison_plot
    import panel_analytical_common as common

    original = common.load_field_points
    common.load_field_points = lambda email: ([1, 2, 3], [40.0, 55.0, 61.0])
    try:
        p = comparison_plot("t", "model", [1], [50.0], 0, "", "Run Number")
        field, manual = p.renderers[0], p.renderers[1]
        assert manual.glyph.fill_color == "#1b5e20"
        assert field.glyph.fill_color == "#f59e0b"

        hovers = [t for t in p.tools if isinstance(t, HoverTool)]
        assert len(hovers) == 1
        assert hovers[0].renderers == [field]
        assert [label for label, _ in hovers[0].tooltips] == ["Site", "Plume length"]
    finally:
        common.load_field_points = original


def test_a_plot_with_no_sites_has_no_site_hover():
    from bokeh.models import HoverTool
    from panel_analytical_common import comparison_plot
    import panel_analytical_common as common

    original = common.load_field_points
    common.load_field_points = lambda email: ([], [])
    try:
        p = comparison_plot("t", "model", [1], [50.0], 0, "", "Run Number")
        assert not [t for t in p.tools if isinstance(t, HoverTool)]
    finally:
        common.load_field_points = original


def test_result_boxes_say_lmax_with_a_subscript():
    # Every model's result card, not just the analytical ones.
    import pathlib

    pages = [
        "bioscreen_panel.py", "panel_birla_single.py", "panel_chu.py",
        "panel_cirpka_single.py", "panel_ham_single.py", "panel_liedl3d_single.py",
        "panel_liedl_single.py", "panel_maier_single.py",
        "panel_numerical_horizontal_single.py", "panel_numerical_vertical_single.py",
        "panel_numerical_horizontal_multiple.py", "panel_numerical_vertical_multiple.py",
        "panel_numerical_multiple_common.py",
    ]
    root = pathlib.Path(__file__).resolve().parent.parent
    for page in pages:
        source = (root / page).read_text(encoding="utf-8")
        assert "Lₘₐₓ" in source, f"{page} lost the subscript label"
        # The ylabel/axis strings keep L_max; only the result-box labels changed.
        assert "Plume Length L_max\"" not in source, f"{page} still labels a card L_max"


def test_database_points_are_inside_the_frame():
    # Field points are what the model result is being compared against, so the
    # frame has to be sized on them too, not only on the manual value.
    low, high = _held_y_range(_data([40.0], field_y=[900.0, 120.0]), {})
    assert low == 0.0 and high >= 900.0


def test_every_component_gets_the_whole_theme():
    # stylesheets is one Parameter owned by Layoutable and shared by every
    # component, so per-class assignment silently overwrites itself and only the
    # last one survives. Guard the combined sheet against a regression to that.
    apply_theme()
    for widget in (
        pn.widgets.Button(name="x"),
        pn.widgets.FloatInput(name="x"),
        pn.widgets.FloatSlider(start=0, end=1, value=0.5),
        pn.pane.Markdown("x"),
    ):
        sheet = widget.stylesheets[0]
        for selector in (".bk-btn-primary", ".bk-input", ".noUi-connect", ".tabulator", "h2 {"):
            assert selector in sheet, f"{type(widget).__name__} lost {selector}"


class _W:
    """Stand-in for a Panel widget: the helper only reads value/start/end."""

    def __init__(self, value, start=None, end=None):
        self.value, self.start, self.end = value, start, end


def test_widget_bounds_win_over_the_table():
    # BIOSCREEN sets model-specific bounds on its own widgets.
    assert _slider_bounds("W", _W(20.0, start=0.1, end=1000.0)) == (0.1, 1000.0)


def test_table_fills_in_for_plain_inputs():
    assert _slider_bounds("W", _W(7.0)) == (0.1, 30.0)


def test_bounds_widen_to_admit_an_out_of_range_value():
    # A site loaded from the database can sit outside the table; the slider must
    # still open on the value that was actually run.
    assert _slider_bounds("M", _W(75.0)) == (0.1, 75.0)
    assert _slider_bounds("M", _W(0.01)) == (0.01, 20.0)


def test_unknown_parameter_never_collapses_to_a_zero_width_range():
    lo, hi = _slider_bounds("not_in_table", _W(4.0))
    assert lo < hi
    lo, hi = _slider_bounds("not_in_table", _W(0.0))   # epsilon-style zero default
    assert lo < hi


def test_chip_is_empty_until_a_slider_moves():
    assert baseline_delta(42.0, 42.0) == ""
    assert baseline_delta(42.0, None) == ""


def test_chip_names_the_direction_and_the_baseline():
    assert baseline_delta(46.2, 42.0) == "↑ 10% vs. baseline 42.00"
    assert baseline_delta(37.8, 42.0) == "↓ 10% vs. baseline 42.00"
