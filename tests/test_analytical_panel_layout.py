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


MULTIPLE_APPS = [
    bioscreen_multiple_app,
    liedl_multiple_app,
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
def test_multiple_panels_show_only_the_graph(app_factory):
    """Multiple pages drive their runs from the sidebar's site checklist, so the
    panel holds the comparison graph and no scenario table."""
    app = app_factory()

    assert app.select(pn.widgets.Tabulator) == []
    assert len(app.select(pn.pane.Bokeh)) == 1


@pytest.mark.parametrize("app_factory", ALL_APPS)
def test_embedded_apps_do_not_repeat_the_outer_model_title(app_factory):
    app = app_factory()
    markdown = app.select(pn.pane.Markdown)

    assert not any(str(pane.object).lstrip().startswith("## ") for pane in markdown)
