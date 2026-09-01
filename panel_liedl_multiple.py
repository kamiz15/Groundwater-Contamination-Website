"""Liedl et al. (2005) multiple simulation - an editable table of scenarios.

Rows are typed straight into the table or uploaded as CSV, and every modelled
Lmax is plotted against the measured plume length of the sites ticked in the
page sidebar. Both series come out of one press of Update Graph.

sidebar_sites is the Liedl-only redesign: the site picker lives on the page, not
on this card, and the layout follows the single simulation - run button and
graph on top, scenario table at the bottom.
"""
from panel_model_scenarios import scenario_app


def liedl_multiple_app():
    return scenario_app("liedl")
