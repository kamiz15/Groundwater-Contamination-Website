"""Ham et al. (2004) multiple simulation - one run per site picked in the sidebar."""
from panel_model_scenarios import scenario_app


def ham_multiple_app():
    return scenario_app("ham")
