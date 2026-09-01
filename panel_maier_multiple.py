"""Maier & Grathwohl (2006) multiple simulation - one run per site picked in the sidebar."""
from panel_model_scenarios import scenario_app


def maier_multiple_app():
    return scenario_app("maier")
