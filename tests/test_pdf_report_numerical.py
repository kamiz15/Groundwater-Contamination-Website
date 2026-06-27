import io

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

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
