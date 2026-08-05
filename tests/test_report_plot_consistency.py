import pandas as pd
import pytest

import panel_analytical_common
import panel_empirical_common
from param_meta import scenario_parameter_rows


@pytest.mark.parametrize(
    "common",
    [panel_analytical_common, panel_empirical_common],
)
def test_site_plot_and_pdf_plot_data_share_the_same_points(monkeypatch, common):
    # Both modules expose the same chart; panel_empirical_common re-exports the
    # analytical implementation, so that is where the loader has to be patched.
    monkeypatch.setattr(panel_analytical_common, "load_field_points", lambda _email: ([1, 2], [12.0, 24.0]))

    plot, plot_data = common.comparison_plot(
        "Example model",
        "Model plume length",
        [2],
        [18.0],
        2,
        "user@example.com",
        "Run Number",
        return_data=True,
    )

    assert plot_data["type"] == "comparison_scatter"
    assert plot_data["field_x"] == [1, 2]
    assert plot_data["field_y"] == [12.0, 24.0]
    assert plot_data["manual_x"] == [2]
    assert plot_data["manual_y"] == [18.0]
    assert plot.renderers[0].data_source.data["x"] == plot_data["field_x"]
    assert plot.renderers[0].data_source.data["y"] == plot_data["field_y"]
    assert plot.renderers[1].data_source.data["x"] == plot_data["manual_x"]
    assert plot.renderers[1].data_source.data["y"] == plot_data["manual_y"]


def test_multiple_report_rows_use_canonical_parameter_symbols():
    frame = pd.DataFrame([{"M": 2.0, "alpha_Tv": 0.01}])

    rows = scenario_parameter_rows(frame, [
        ("M", "S_T", "Source Thickness", "m"),
        ("alpha_Tv", "alpha_Tv", "Vertical Transverse Dispersivity", "m"),
    ])

    assert rows == [
        {"symbol": "S_T", "name": "Scenario 1 - Source Thickness", "value": 2.0, "unit": "m"},
        {"symbol": "alpha_Tv", "name": "Scenario 1 - Vertical Transverse Dispersivity", "value": 0.01, "unit": "m"},
    ]
