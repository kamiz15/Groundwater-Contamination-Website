from types import SimpleNamespace
import json

import numpy as np
import panel as pn

import panel_numerical_horizontal_multiple as horizontal_multiple
import panel_numerical_vertical_multiple as vertical_multiple


class _StoppedCallback:
    def stop(self):
        pass


def test_vertical_multiple_renders_graphs_for_completed_jobs(monkeypatch):
    result = SimpleNamespace(
        plume_length=3.0,
        concentration=np.array(
            [
                [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                [2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                [3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
                [4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
            ]
        ),
        x_grid=np.linspace(0.0, 10.0, 6),
        z_grid=np.linspace(0.0, 4.0, 4),
        plot_png=b"png-bytes",
    )

    monkeypatch.setattr(vertical_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        vertical_multiple,
        "query_int",
        lambda name, default: 1 if name in {"output_only", "run"} else default,
    )
    monkeypatch.setattr(vertical_multiple, "submit_job", lambda _kind, _params: "job-1")
    monkeypatch.setattr(vertical_multiple, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(vertical_multiple, "fetch_result", lambda _job_id: result)
    monkeypatch.setattr(pn.state, "add_periodic_callback", lambda *_args, **_kwargs: _StoppedCallback())

    app = vertical_multiple.numerical_vertical_multiple_app()
    graphs_column = app.objects[1]

    # Per scenario: heading markdown + plume Bokeh pane. The growth animation now
    # plays once automatically (no manual Player widget).
    assert len(graphs_column.objects) == 2
    assert "Scenario 1" in graphs_column.objects[0].object
    assert graphs_column.objects[1].object.title is None


def test_vertical_multiple_output_mode_renders_completed_job_ids(monkeypatch):
    result = SimpleNamespace(
        plume_length=3.0,
        concentration=np.array(
            [
                [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                [2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                [3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
                [4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
            ]
        ),
        x_grid=np.linspace(0.0, 10.0, 6),
        z_grid=np.linspace(0.0, 4.0, 4),
        plot_png=b"png-bytes",
    )
    rows = [{"Lz": 4.0, "grid_size": 1.0, "al": 1.0, "atv": 0.1, "gamma": 3.5, "C_D": 5.0, "C_A": 8.0}]

    monkeypatch.setattr(vertical_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        vertical_multiple,
        "query_int",
        lambda name, default: 1 if name == "output_only" else 0,
    )
    monkeypatch.setattr(
        vertical_multiple,
        "query_str",
        lambda name, default="": json.dumps(["job-1"]) if name == "job_ids" else json.dumps(rows),
    )
    monkeypatch.setattr(vertical_multiple, "fetch_result", lambda _job_id: result)

    app = vertical_multiple.numerical_vertical_multiple_app()
    graphs_column = app.objects[1]

    assert len(graphs_column.objects) == 2
    assert "Scenario 1" in graphs_column.objects[0].object


def test_vertical_multiple_input_mode_keeps_results_out_of_input_panel(monkeypatch):
    monkeypatch.setattr(vertical_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        vertical_multiple,
        "query_int",
        lambda name, default: 1 if name == "input_only" else default,
    )

    app = vertical_multiple.numerical_vertical_multiple_app()

    assert len(app.objects) == 5
    assert "Vertical Numerical Model - Multiple" in app.objects[0].object
    assert app.objects[1].height == 95
    assert app.objects[2].height == 0
    assert app.objects[3].object == ""
    assert "run-numerical-multiple" in app.objects[4].object


def test_horizontal_multiple_renders_graphs_for_completed_jobs(monkeypatch):
    result = SimpleNamespace(
        plume_length=4.0,
        concentration=np.array(
            [
                [1.0, 2.0, 3.0, 4.0, 5.0, 6.0],
                [2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
                [3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
                [4.0, 5.0, 6.0, 7.0, 8.0, 9.0],
            ]
        ),
        x_grid=np.linspace(0.0, 10.0, 6),
        y_grid=np.linspace(0.0, 4.0, 4),
        plot_png=b"png-bytes",
    )

    monkeypatch.setattr(horizontal_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        horizontal_multiple,
        "query_int",
        lambda name, default: 1 if name in {"output_only", "run"} else default,
    )
    monkeypatch.setattr(horizontal_multiple, "submit_job", lambda _kind, _params: "job-1")
    monkeypatch.setattr(horizontal_multiple, "job_status", lambda _job_id: {"status": "done"})
    monkeypatch.setattr(horizontal_multiple, "fetch_result", lambda _job_id: result)
    monkeypatch.setattr(pn.state, "add_periodic_callback", lambda *_args, **_kwargs: _StoppedCallback())

    app = horizontal_multiple.numerical_horizontal_multiple_app()
    graphs_column = app.objects[1]

    # Per scenario: heading markdown + plume Bokeh pane. The growth animation now
    # plays once automatically (no manual Player widget).
    assert len(graphs_column.objects) == 2
    assert "Scenario 1" in graphs_column.objects[0].object
    assert graphs_column.objects[1].object.title.text == "Contaminant Plume \u2014 Horizontal Model (Plan View)"


def test_horizontal_multiple_input_mode_keeps_results_out_of_input_panel(monkeypatch):
    monkeypatch.setattr(horizontal_multiple, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        horizontal_multiple,
        "query_int",
        lambda name, default: 1 if name == "input_only" else default,
    )

    app = horizontal_multiple.numerical_horizontal_multiple_app()

    assert len(app.objects) == 5
    assert "Horizontal Numerical Model - Multiple" in app.objects[0].object
    assert app.objects[1].height == 95
    assert app.objects[2].height == 0
    assert app.objects[3].object == ""
    assert "run-numerical-multiple" in app.objects[4].object
