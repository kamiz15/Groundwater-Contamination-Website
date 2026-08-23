"""The multiple reports lay their inputs out like the site database table."""

from unittest.mock import patch

from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Table

from pdf_report import CASTReport


def _params(sites, columns):
    """Flat parameter list of the shape the multiple panels post."""
    return [
        {"symbol": name[0], "name": name, "value": i + 1.0, "unit": "m", "site": site}
        for i, site in enumerate(sites)
        for name in columns
    ]


def _text(cell):
    return cell.text if isinstance(cell, Paragraph) else str(cell)


def test_site_tagged_parameters_pivot_to_one_row_per_site():
    report = CASTReport("Liedl et al. (2005) - Multiple Simulation", "Liedl")
    tables = report.build_site_input_tables(
        _params(["Borden", "Vejen"], ["Source Thickness", "Recharge Rate"])
    )

    assert len(tables) == 1
    rows = tables[0]._cellvalues
    assert [_text(c) for c in rows[0]] == [
        "Site No.", "Site Unit", "Source Thickness [m]", "Recharge Rate [m]",
    ]
    # Row number is the site's x position on the graph, not its database id.
    assert [_text(r[0]) for r in rows[1:]] == ["1", "2"]
    assert [_text(r[1]) for r in rows[1:]] == ["Borden", "Vejen"]
    assert [_text(r[2]) for r in rows[1:]] == ["1.00", "2.00"]


def test_wide_models_split_instead_of_shrinking_columns():
    """BIOSCREEN reports 14 parameters; one row of them is unreadable."""
    columns = [f"Param {i}" for i in range(14)]
    report = CASTReport("BIOSCREEN-AT 3D - Multiple Simulation", "BIOSCREEN-AT 3D")
    tables = report.build_site_input_tables(_params(["Borden"], columns))

    assert len(tables) == 2
    # Every table repeats the site columns, and no parameter is dropped.
    seen = []
    for t in tables:
        header = [_text(c) for c in t._cellvalues[0]]
        assert header[:2] == ["Site No.", "Site Unit"]
        seen += header[2:]
    assert seen == [f"{c} [m]" for c in columns]


def test_single_run_reports_keep_the_parameter_value_layout():
    """Only the multiple pages tag parameters with a site, so nothing else moves."""
    report = CASTReport("Liedl et al. (2005) - Single Simulation", "Liedl")
    pdf = report.generate(
        parameters=[{"symbol": "S_T", "name": "Source Thickness", "value": 5.0, "unit": "m"}],
        outputs=[{"label": "Lmax", "value": "117.99", "unit": "m"}],
    )
    assert pdf.startswith(b"%PDF")


SECTIONS = {"Input Parameters", "Computed Results", "Results Visualisation"}


def _section_titles(report, **kwargs):
    """Section headers in the order they are laid out on the page.

    Read off the built story, not off the order the pieces were constructed in -
    generate() builds every section before deciding how to order them.
    """
    captured = []

    def spy(self, story, **kwargs):
        captured.extend(story)

    with patch.object(SimpleDocTemplate, "build", spy):
        report.generate(**kwargs)

    titles = []
    pending = list(captured)
    while pending:
        flow = pending.pop(0)
        if isinstance(flow, KeepTogether):
            pending = list(getattr(flow, "_content", [])) + pending
        elif isinstance(flow, Table) and getattr(flow, "_cellvalues", None):
            cell = flow._cellvalues[0][0]
            if isinstance(cell, Paragraph) and cell.text in SECTIONS:
                titles.append(cell.text)
    return titles


def test_a_multiple_report_leads_with_the_graph():
    """The site table can run for pages; the graph must not be stranded after it."""
    report = CASTReport("Liedl et al. (2005) - Multiple Simulation", "Liedl")
    titles = _section_titles(
        report,
        parameters=_params(["Borden"], ["Source Thickness"]),
        outputs=[],
        plot_data={"labels": ["Borden"], "values": [80.0], "title": "Lmax"},
    )

    assert titles.index("Results Visualisation") < titles.index("Input Parameters")


def test_a_multiple_report_drops_the_computed_results_box():
    report = CASTReport("Liedl et al. (2005) - Multiple Simulation", "Liedl")
    titles = _section_titles(
        report,
        parameters=_params(["Borden"], ["Source Thickness"]),
        outputs=[],
    )

    assert "Computed Results" not in titles


def test_single_reports_keep_their_section_order():
    report = CASTReport("Liedl et al. (2005) - Single Simulation", "Liedl")
    titles = _section_titles(
        report,
        parameters=[{"symbol": "S_T", "name": "Source Thickness", "value": 5.0, "unit": "m"}],
        outputs=[{"label": "Lmax", "value": "117.99", "unit": "m"}],
        plot_data={"labels": ["Lmax"], "values": [117.99], "title": "Lmax"},
    )

    assert titles == ["Input Parameters", "Computed Results", "Results Visualisation"]


def test_multiple_report_renders_end_to_end():
    report = CASTReport("Liedl et al. (2005) - Multiple Simulation", "Liedl")
    pdf = report.generate(
        parameters=_params(["Borden", "Vejen"], ["Source Thickness", "Recharge Rate"]),
        outputs=[{"label": "Sites simulated", "value": "2", "unit": ""}],
    )
    assert pdf.startswith(b"%PDF")
