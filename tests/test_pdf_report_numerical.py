import io
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest
from reportlab.lib.units import mm

from pdf_report import CASTReport


def _tiny_plot_png():
    fig, ax = plt.subplots(figsize=(2, 1.2), dpi=80)
    ax.imshow([[0.0, 1.0], [2.0, 3.0]], cmap="Blues")
    ax.set_axis_off()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def test_numerical_pdf_report_accepts_new_parameter_output_shape():
    report = CASTReport("Numerical Horizontal Model - Single Simulation", "Numerical Horizontal")

    def fail_if_chart_is_generated(_plot_data):
        raise AssertionError("fallback chart should not be generated when a model image is supplied")

    report._make_chart = fail_if_chart_is_generated
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "Sw", "name": "Source Thickness", "value": 5, "unit": "m"},
            {"symbol": "dx", "name": "Grid Size", "value": 1.0, "unit": "m"},
            {"symbol": "LD", "name": "Domain Length (analytical)", "value": 143.664, "unit": "m"},
            {"symbol": "DW", "name": "Domain Width", "value": 50.0, "unit": "m"},
        ],
        outputs=[
            {"label": "Horizontal Numerical Lmax", "value": "117.987", "unit": "m"},
            {"label": "Domain Length LD", "value": "143.664", "unit": "m"},
            {"label": "Domain Width", "value": "50.0", "unit": "m"},
            {"label": "Peclet Number", "value": "1.234", "unit": "-"},
            {"label": "Courant Target", "value": "5", "unit": "-"},
        ],
        plot_data={"labels": ["Lmax"], "values": [117.987], "title": "Fallback chart"},
        plot_images=[{
            "title": "Horizontal Plume Concentration",
            "bytes": _tiny_plot_png(),
            "caption": "Synthetic plume figure.",
        }],
    )

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
    assert report._fmt_value("117.987") == "117.99"
    assert report._fmt_value(5) == "5.00"
    assert report._metric_value_markup("7.00", "m").startswith("<b>7.00</b>&#8201;")


def test_report_image_fit_preserves_aspect_ratio_when_height_is_capped():
    width, height = CASTReport._fit_image_dimensions(800, 600, 82)

    assert height == pytest.approx(82 * mm)
    assert width / height == pytest.approx(800 / 600)


def test_pdf_report_renders_comparison_scatter_on_second_page():
    report = CASTReport("Liedl et al. (2005) - Single Simulation", "Liedl Analytical")
    pdf_bytes = report.generate(
        parameters=[
            {"symbol": "M", "name": "Aquifer Thickness", "value": 2, "unit": "m"},
            {"symbol": "alpha_Tv", "name": "Transverse Dispersivity", "value": 0.001, "unit": "m"},
        ],
        outputs=[{"label": "Maximum Plume Length Lmax", "value": "1293.02", "unit": "m"}],
        plot_data={
            "type": "comparison_scatter",
            "title": "Liedl et al. (2005)",
            "x_label": "Site Number",
            "y_label": "Plume Length (m)",
            "field_label": "Database plume length",
            "field_x": [1, 2, 3, 4],
            "field_y": [120, 480, 900, 2000],
            "manual_label": "Liedl model plume length",
            "manual_x": [3],
            "manual_y": [1293.02],
        },
    )

    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000
    assert len(re.findall(rb"/Type\s*/Page\b", pdf_bytes)) >= 2


def test_pdf_report_formats_symbols_for_input_table():
    assert CASTReport._symbol_markup("alpha_Tv") == "&#945;<sub>Tv</sub>"
    assert CASTReport._symbol_markup(chr(945) + "Tv") == "&#945;<sub>Tv</sub>"
    assert CASTReport._symbol_markup(chr(206) + chr(177) + "Tv") == "&#945;<sub>Tv</sub>"
    assert CASTReport._symbol_markup("C_EA0") == "<i>C</i><sub>EA0</sub>"
