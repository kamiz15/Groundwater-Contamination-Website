"""Cirpka et al. (2006) multiple simulation - one run per site picked in the sidebar."""
from panel_site_comparison import site_comparison_app


def cirpka_multiple_app():
    return site_comparison_app("cirpka")
