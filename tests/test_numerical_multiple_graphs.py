from types import SimpleNamespace

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

    assert len(graphs_column.objects) == 2
    assert "Scenario 1" in graphs_column.objects[0].object
    assert graphs_column.objects[1].object.title.text == "Contaminant Plume - Vertical Model"


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

    assert len(graphs_column.objects) == 2
    assert "Scenario 1" in graphs_column.objects[0].object
    assert graphs_column.objects[1].object.title.text == "Contaminant Plume \u2014 Horizontal Model (Plan View)"
