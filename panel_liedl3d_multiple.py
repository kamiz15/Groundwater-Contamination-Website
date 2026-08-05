"""Liedl 3D (2011) multiple simulation - one run per site picked in the sidebar."""
from panel_site_comparison import site_comparison_app


def liedl3d_multiple_app():
    return site_comparison_app("liedl3d")
