"""Ham et al. (2004) multiple simulation - one run per site picked in the sidebar."""
from panel_site_comparison import site_comparison_app


def ham_multiple_app():
    return site_comparison_app("ham")
