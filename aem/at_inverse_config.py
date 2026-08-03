# Written by Willi Kappler, willi.kappler@uni-tuebingen.de
# Based on code from Anton Köhler

import json
import logging

from .at_config import ATConfiguration

logger = logging.getLogger(__name__)


# Default per-parameter search bounds for the inverse solver.
DEFAULT_PARAM_SEARCH = {
    # transverse dispersivity alpha_t [m]
    "alpha_t": {
        "lower": 0.001,
        "upper": 0.1,
        "initial_step_factor": 1.0 / 500.0,
        "step_growth": 3.0,
        "max_step_factor": 0.2,
        "L_tolerance": 10.0,
    },
    # longitudinal dispersivity alpha_l [m]
    "alpha_l": {
        "lower": 0.5,
        "upper": 10.5,
        "initial_step_factor": 1.0 / 200.0,
        "step_growth": 3.0,
        "max_step_factor": 0.2,
        "L_tolerance": 10.0,
    },
    # Radius r [m] - absolute global bounds (independent of source modifier)
    "r": {
        "lower": 0.1,
        "upper": 10.0,
        "initial_step_factor": 1.0 / 500.0,
        "step_growth": 3.0,
        "max_step_factor": 0.2,
        "L_tolerance": 10.0,
    },
    # Source conc C0 [mg/L]
    "C0": {
        "factor_lower": 0.5,
        "factor_upper": 150.0,
        "min_abs": 0.01,
        "max_abs": 120.0,
        "initial_step_factor": 1.0 / 500.0,
        "step_growth": 3.0,
        "max_step_factor": 0.2,
        "L_tolerance": 10.0,
    },
    # Background conc Ca [mg/L]
    "ca": {
        "factor_lower": 0.5,
        "factor_upper": 30.0,
        "min_abs": 0.1,
        "max_abs": 20.0,
        "initial_step_factor": 1.0 / 500.0,
        "step_growth": 3.0,
        "max_step_factor": 0.2,
        "L_tolerance": 10.0,
    },
    # Gamma [1/y]
    "gamma": {
        "factor_lower": 3.0,
        "factor_upper": 10.0,
        "min_abs": 0.0,
        "max_abs": 1.0,
        "initial_step_factor": 1.0 / 500.0,
        "step_growth": 3.0,
        "max_step_factor": 0.2,
        "L_tolerance": 10.0,
    },
}

# Scalar fields loaded straight from the JSON (one key per attribute).
_SCALAR_KEYS = (
    # run-level options
    "input_file", "output_file", "stats_file",
    "orientation", "elem_kind", "source_thickness_modifier", "estimate_param",
    "lower_bound", "upper_bound",
    # domain / numerical settings
    "num_cp", "num_terms",
    "dom_xmin", "dom_xmax", "dom_ymin", "dom_ymax", "dom_inc",
    # fixed dispersivities
    "fixed_alpha_t", "fixed_alpha_l",
    "alpha_t_when_estimating_others", "alpha_l_when_estimating_others",
    # solver controls
    "l_tolerance_default", "max_stagnation_default",
)


class InverseConfiguration:
    """Exclusive configuration for the inverse model.

    Holds every inverse-run parameter that is not supplied per case by the
    input file. Defaults match the canonical setup, so a missing or partial
    inverse_config.json still runs.
    """

    def __init__(self):
        # Run-level options
        self.input_file: str = "input_values_new.txt"
        self.output_file: str = "output_values.txt"
        self.stats_file: str = "stats_values.txt"
        self.orientation: str = "horizontal"      # "horizontal" or "vertical"
        self.elem_kind: str = "Line"              # "Circle" or "Line"
        self.source_thickness_modifier: float = 1.0
        self.estimate_param: str = "r"            # alpha_t, alpha_l, r, C0, ca, gamma

        # Optional global bound overrides (None -> use param_search_defaults)
        self.lower_bound = None
        self.upper_bound = None

        # Domain / numerical settings
        self.num_cp: int = 100
        self.num_terms: int = 7
        self.dom_xmin: float = 0.0
        self.dom_xmax: float = 300.0   # used as a floor; expanded per-case by target
        self.dom_ymin: float = -20.0
        self.dom_ymax: float = 20.0
        self.dom_inc: float = 0.5

        # Fixed dispersivities used while estimating another parameter.
        self.fixed_alpha_t: float = 0.1                    # m, used when estimating alpha_l
        self.fixed_alpha_l: float = 1.0                    # m, used when estimating alpha_t
        self.alpha_t_when_estimating_others: float = 0.1   # m, used for r/C0/ca/gamma
        self.alpha_l_when_estimating_others: float = 1.0   # m, used for r/C0/ca/gamma

        # Solver controls
        self.l_tolerance_default: float = 10.0   # |L_max - target| [m]
        self.max_stagnation_default: int = 5

        # Per-parameter dynamic-scan / bisection search configuration
        self.param_search_defaults: dict = {
            k: dict(v) for k, v in DEFAULT_PARAM_SEARCH.items()
        }

    @staticmethod
    def from_dict(data: dict) -> "InverseConfiguration":
        # Unknown keys are ignored; missing keys keep their defaults.
        cfg = InverseConfiguration()
        for key in _SCALAR_KEYS:
            if key in data:
                setattr(cfg, key, data[key])

        # Merge the search table per-parameter so a partial override keeps the
        # remaining defaults for that parameter.
        overrides = data.get("param_search_defaults")
        if overrides:
            merged = {k: dict(v) for k, v in DEFAULT_PARAM_SEARCH.items()}
            for pname, pvals in overrides.items():
                base = dict(merged.get(pname, {}))
                base.update(pvals)
                merged[pname] = base
            cfg.param_search_defaults = merged

        return cfg

    @staticmethod
    def from_json(filename: str) -> "InverseConfiguration":
        # Load the inverse configuration from a JSON file.
        logger.debug(f"Load inverse configuration from file: {filename}.")
        with open(filename, "r") as f:
            data = json.load(f)
        return InverseConfiguration.from_dict(data)

    def build_base_config(self) -> ATConfiguration:
        # ATConfiguration carrying only the domain / numerical settings; the
        # solver fills in the per-case physical parameters afterwards.
        cfg = ATConfiguration()
        cfg.num_cp = self.num_cp
        cfg.num_terms = self.num_terms
        cfg.dom_xmin = self.dom_xmin
        cfg.dom_xmax = self.dom_xmax
        cfg.dom_ymin = self.dom_ymin
        cfg.dom_ymax = self.dom_ymax
        cfg.dom_inc = self.dom_inc
        return cfg
