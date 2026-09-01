import panel as pn
import pytest

from bioscreen_panel import bioscreen_multiple_app, bioscreen_single_app
from panel_birla_multiple import birla_multiple_app
from panel_birla_single import birla_single_app
from panel_chu import chu_multiple_app, chu_single_app
from panel_cirpka_multiple import cirpka_multiple_app
from panel_cirpka_single import cirpka_single_app
from panel_ham_multiple import ham_multiple_app
from panel_ham_single import ham_single_app
from panel_liedl3d_multiple import liedl3d_multiple_app
from panel_liedl3d_single import liedl3d_single_app
from panel_liedl_multiple import liedl_multiple_app
from panel_liedl_single import liedl_single_app
from panel_maier_multiple import maier_multiple_app
from panel_maier_single import maier_single_app


# Every multiple page runs the scenario-table mode (panel_model_scenarios) on
# the single-simulation shell: the site picker is in the PAGE sidebar, and the
# Add-row dialog belongs to the page too, so neither is in the panel. What is in
# here is the run button, the graph, the export buttons and the table.
MULTIPLE_APPS = [
    liedl_multiple_app,
    bioscreen_multiple_app,
    liedl3d_multiple_app,
    chu_multiple_app,
    ham_multiple_app,
    cirpka_multiple_app,
    maier_multiple_app,
    birla_multiple_app,
]

ALL_APPS = [
    liedl_single_app,
    liedl_multiple_app,
    liedl3d_single_app,
    liedl3d_multiple_app,
    chu_single_app,
    chu_multiple_app,
    ham_single_app,
    ham_multiple_app,
    bioscreen_single_app,
    bioscreen_multiple_app,
    cirpka_single_app,
    cirpka_multiple_app,
    maier_single_app,
    maier_multiple_app,
    birla_single_app,
    birla_multiple_app,
]


@pytest.mark.parametrize("app_factory", MULTIPLE_APPS)
def test_multiple_panels_carry_the_graph_and_an_editable_scenario_table(app_factory):
    """One shape across every model: the graph and the table it was built from,
    with the picker and the Add-row dialog left to the page."""
    app = app_factory()

    table = app.select(pn.widgets.Tabulator)
    assert len(table) == 1 and not table[0].disabled
    assert table[0].selectable == "checkbox"                   # Delete row needs it
    assert len(app.select(pn.widgets.MultiSelect)) == 1     # its own site picker
    # No plot before a run: a box holds its place, and the graph replaces it.
    # Found by what is in it rather than where it sits - the redesigned layout
    # nests the slot beside the picker instead of at the top level.
    slot = next(c for c in app.select(pn.Column)
                if isinstance(next(iter(c), None), pn.pane.HTML)
                and "Update Graph" in str(next(iter(c)).object))
    assert len(slot) == 1 and isinstance(slot[0], pn.pane.HTML)
    names = [w.name for w in app.select(pn.widgets.Button)]
    # + and - carry "Add row" / "Delete row" in their tooltip on the redesign.
    captions = set(names) | {w.description for w in app.select(pn.widgets.Button)}
    assert {"Update Graph", "Delete table"} <= set(names)
    assert {"Add row", "Delete row"} <= captions


@pytest.mark.parametrize("app_factory", ALL_APPS)
def test_embedded_apps_do_not_repeat_the_outer_model_title(app_factory):
    app = app_factory()
    markdown = app.select(pn.pane.Markdown)

    assert not any(str(pane.object).lstrip().startswith("## ") for pane in markdown)
