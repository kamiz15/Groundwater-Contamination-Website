import numpy as np
from bokeh.plotting import figure

from panel_numerical_optional_views import LazyNumericalViews


def _payload():
    return {
        "concentration": np.array([
            [8.0, 7.0, 5.0, 3.0],
            [8.0, 6.0, 4.0, 2.0],
            [8.0, 7.0, 5.0, 3.0],
        ]),
        "x_grid": np.array([0.0, 1.0, 2.0, 3.0]),
        "cross_grid": np.array([0.0, 1.0, 2.0]),
        "cross_axis_label": "Horizontal Width [m]",
        "title": "Test Numerical Model",
    }


def test_optional_views_compute_only_after_button_click(capsys):
    calls = {"profile": 0, "vector": 0}

    def profile_plotter(*args, **kwargs):
        calls["profile"] += 1
        return figure()

    def vector_plotter(*args, **kwargs):
        calls["vector"] += 1
        return figure()

    views = LazyNumericalViews(
        _payload,
        profile_plotter=profile_plotter,
        vector_plotter=vector_plotter,
    )

    assert calls == {"profile": 0, "vector": 0}
    assert views.computation_counts == {"profile": 0, "vector": 0}

    views.profile_button.clicks += 1
    assert calls == {"profile": 1, "vector": 0}
    assert views.profile_pane in views.view_container.objects

    views.profile_button.clicks += 1
    views.profile_button.clicks += 1
    assert calls == {"profile": 1, "vector": 0}

    views.vector_button.clicks += 1
    assert calls == {"profile": 1, "vector": 1}
    assert views.vector_pane in views.view_container.objects

    logs = capsys.readouterr().out
    assert "[optional-view] profile computed on click" in logs
    assert "[optional-view] vector computed on click" in logs


def test_optional_views_request_run_before_computing_without_result():
    calls = {"profile": 0}

    def profile_plotter(*args, **kwargs):
        calls["profile"] += 1
        return figure()

    views = LazyNumericalViews(lambda: None, profile_plotter=profile_plotter)
    views.profile_button.clicks += 1

    assert calls["profile"] == 0
    assert "Run the numerical simulation" in views.status_pane.object


def test_optional_views_reset_discards_stale_plots():
    views = LazyNumericalViews(_payload)
    views.profile_button.clicks += 1
    views.vector_button.clicks += 1

    views.reset()

    assert views.profile_pane.object is None
    assert views.vector_pane.object is None
    assert views.view_container.objects == []


def test_optional_views_build_real_profile_and_vector_plots():
    views = LazyNumericalViews(_payload)

    views.profile_button.clicks += 1
    views.vector_button.clicks += 1

    assert views.profile_pane.object.title.text.endswith("Mean Concentration Profile")
    assert views.vector_pane.object.title.text.endswith("Decreasing-Concentration Vector View")
