"""Koehler et al. (2024) multiple simulation - one row per scenario.

Same scenario table as every other closed-form model. Koehler is the one whose
spec carries an `extra` callable, so the run writes T_Lmax and the fitted-range
verdict back as two more columns.
"""
from panel_model_scenarios import scenario_app


def kohler_multiple_app():
    return scenario_app("kohler")
