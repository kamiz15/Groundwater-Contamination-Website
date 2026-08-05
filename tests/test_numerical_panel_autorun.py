import panel as pn
import pytest

import panel_numerical_horizontal_multiple as horizontal_multiple
import panel_numerical_horizontal_single as horizontal_single
import panel_numerical_vertical_multiple as vertical_multiple
import panel_numerical_vertical_single as vertical_single


class _StoppedCallback:
    def stop(self):
        pass


def _freeze_button_names(monkeypatch, module):
    real_button = pn.widgets.Button

    def constant_name_button(*args, **kwargs):
        button = real_button(*args, **kwargs)
        button.param.name.constant = True
        return button

    monkeypatch.setattr(module.pn.widgets, "Button", constant_name_button)


@pytest.mark.parametrize(
    ("module", "app_factory", "job_kind"),
    [
        (horizontal_single, horizontal_single.numerical_horizontal_single_app, "horizontal_single"),
        (vertical_single, vertical_single.numerical_vertical_single_app, "vertical_single"),
    ],
)
def test_single_output_autorun_supports_constant_button_names(
    monkeypatch, module, app_factory, job_kind
):
    submitted = []
    _freeze_button_names(monkeypatch, module)
    monkeypatch.setattr(module, "query_float", lambda _name, default: default)
    monkeypatch.setattr(
        module,
        "query_int",
        lambda name, default: 1 if name in {"output_only", "run"} else default,
    )
    monkeypatch.setattr(
        module,
        "submit_job",
        lambda kind, params: submitted.append((kind, params)) or "job-1",
    )
    monkeypatch.setattr(
        module,
        "job_status",
        lambda _job_id: {"status": "queued", "queue_position": 1},
    )
    monkeypatch.setattr(
        pn.state,
        "add_periodic_callback",
        lambda *_args, **_kwargs: _StoppedCallback(),
    )

    app = app_factory()

    assert isinstance(app, pn.Column)
    assert submitted[0][0] == job_kind


@pytest.mark.parametrize(
    ("module", "app_factory", "job_kind"),
    [
        (horizontal_multiple, horizontal_multiple.numerical_horizontal_multiple_app, "horizontal_single"),
        (vertical_multiple, vertical_multiple.numerical_vertical_multiple_app, "vertical_single"),
    ],
)
def test_multiple_output_autorun_supports_constant_button_names(
    monkeypatch, module, app_factory, job_kind
):
    submitted = []
    _freeze_button_names(monkeypatch, module)
    monkeypatch.setattr(
        module,
        "query_int",
        lambda name, default: 1 if name in {"output_only", "run"} else default,
    )
    monkeypatch.setattr(module, "query_str", lambda _name, default="": default)
    # The run is driven by the sidebar's site pick, so autorun needs one.
    monkeypatch.setattr(module, "authenticated_email", lambda: "user@example.com")
    monkeypatch.setattr(module, "get_user_sites_rows", lambda _email: [{
        "id": 7, "display_id": 7, "site_unit": "Borden", "compound": "BTEX",
        "aquifer_thickness": 10.0, "source_thickness": 5.0, "electron_donor": 5.0,
        "electron_acceptor_o2": 2.0, "alpha_tv": 0.1, "alpha_th": 0.2, "gamma": 3.5,
    }])
    monkeypatch.setattr(module, "_selected_site_ids", lambda: [7])
    monkeypatch.setattr(
        module,
        "submit_job",
        lambda kind, params: submitted.append((kind, params)) or "job-1",
    )
    monkeypatch.setattr(
        module,
        "job_status",
        lambda _job_id: {"status": "queued", "queue_position": 1},
    )
    monkeypatch.setattr(
        pn.state,
        "add_periodic_callback",
        lambda *_args, **_kwargs: _StoppedCallback(),
    )

    app = app_factory()

    assert isinstance(app, pn.Column)
    assert submitted[0][0] == job_kind
