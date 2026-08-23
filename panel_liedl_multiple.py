"""Liedl et al. (2005) multiple simulation - an editable table of scenarios.

Sites ticked in the sidebar seed the table; rows can also be typed in or
uploaded as CSV, and every modelled Lmax is plotted against the measured plume
length of its site.
"""
from panel_model_scenarios import scenario_app


def liedl_multiple_app():
    return scenario_app("liedl")
