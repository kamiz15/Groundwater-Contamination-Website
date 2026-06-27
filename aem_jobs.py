"""Helpers for AEM (Analytic Element Method) async jobs.

The async queue in :mod:`numerical_jobs` is generic by ``kind``; this module
holds the AEM-specific marshalling: building an :class:`ATConfiguration` from
posted parameters (optionally seeded from a bundled designer export) and the
small, pickle-able result object returned by the forward-simulation worker.

The live :class:`ATSimulation` holds ``Mathieu`` objects and a multiprocessing
pool and must NOT be pickled. ``AEMForwardResult`` carries only plain numpy
arrays and scalars so it round-trips cleanly through the job queue.
"""
from __future__ import annotations

import os
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


# Directory holding the sample designer exports bundled with the project.
DESIGNER_EXPORTS_DIR = Path(__file__).resolve().parent / "aem" / "designer_exports"

# A safe default sample so the page renders something even before a user designs
# their own source configuration.
DEFAULT_SAMPLE = "source_config_horizontal.json"
_DESIGN_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{32,64}$")
DESIGN_TTL_SECONDS = 24 * 60 * 60


def _design_root() -> Path:
    root = Path(os.getenv("NUMERICAL_JOB_ROOT", ".numerical_jobs")) / "aem_designs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_aem_design(email: str, config: dict[str, Any], token: str | None = None) -> str:
    """Persist an owner-bound design for short cross-process URL handoff."""
    if not email or not isinstance(config, dict):
        raise ValueError("An authenticated owner and design object are required.")
    token = token or secrets.token_urlsafe(32)
    if not _DESIGN_TOKEN_RE.fullmatch(token):
        raise ValueError("Invalid AEM design token.")
    path = _design_root() / f"{token}.json"
    if path.exists():
        existing = load_aem_design(token, email, allow_expired=True)
        if existing is None:
            raise PermissionError("The AEM design token belongs to another user.")
    temporary = path.with_suffix(".tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump({"email": email, "created_at": time.time(), "config": config}, handle)
    temporary.replace(path)
    return token


def load_aem_design(token: str, email: str, *, allow_expired: bool = False) -> dict[str, Any] | None:
    """Load a design only for its owner; malformed and expired records are hidden."""
    if not email or not _DESIGN_TOKEN_RE.fullmatch(token or ""):
        return None
    try:
        with open(_design_root() / f"{token}.json", "r", encoding="utf-8") as handle:
            record = json.load(handle)
        if record.get("email") != email or not isinstance(record.get("config"), dict):
            return None
        if not allow_expired and time.time() - float(record["created_at"]) > DESIGN_TTL_SECONDS:
            return None
        return record["config"]
    except (OSError, ValueError, TypeError):
        return None


@dataclass
class AEMForwardResult:
    """Pickle-able payload returned by the AEM forward-simulation worker.

    Attributes mirror the relevant fields of :class:`ATSimulation` after a run.
    ``plume_length`` aliases ``L_max`` so the generic job queue (which reads
    ``result.plume_length``) keeps working.
    """

    result: np.ndarray
    xaxis: np.ndarray
    yaxis: np.ndarray
    L_max: float | None
    ca: float
    gamma: float
    orientation: str = "horizontal"
    num_elements: int = 0
    interface_length: float | None = None
    validation_passed: bool | None = None
    validation_reason: str = ""
    domain_extent: dict[str, float] = field(default_factory=dict)

    @property
    def plume_length(self) -> float:
        """Generic-queue alias used by numerical_jobs.mark_done."""
        return float(self.L_max) if self.L_max is not None else 0.0


@dataclass
class AEMInverseResult:
    """Pickle-able payload returned by the AEM inverse-model worker.

    Carries the recovered parameter value plus the achieved L_max and (when a
    converged simulation is available) the plain concentration-field arrays so
    the page can render the matched plume. No live ATSimulation/Mathieu objects
    are stored, keeping the object picklable for the job queue.
    """

    estimate_param: str
    recovered_value: float
    achieved_L_max: float | None
    target_L_max: float
    orientation: str
    elem_kind: str
    lower_bound: float
    upper_bound: float
    fixed_params: dict[str, float] = field(default_factory=dict)
    result: np.ndarray | None = None
    xaxis: np.ndarray | None = None
    yaxis: np.ndarray | None = None
    ca: float = 8.0
    gamma: float = 3.5
    converged: bool = False

    @property
    def plume_length(self) -> float:
        """Generic-queue alias used by numerical_jobs.mark_done."""
        return float(self.achieved_L_max) if self.achieved_L_max is not None else 0.0


# Parameters the inverse model can recover.
INVERSE_PARAMS = ("alpha_t", "alpha_l", "r", "C0", "ca", "gamma")


def run_aem_inverse(params: dict[str, Any]) -> AEMInverseResult:
    """Recover one transport/source parameter from a target plume length L_max.

    Mirrors the per-case logic inside
    ``aem.at_inverse_model.process_input_file_with_logging`` (bound selection,
    fixed-parameter assembly) but calls the underlying solver
    ``estimate_parameter_scanned`` directly so a small, pickle-able result with
    the recovered value (and matched field) can be returned to the job queue.
    """
    from aem import at_inverse_model as inv

    estimate_param = str(params.get("estimate_param", "alpha_t"))
    if estimate_param not in INVERSE_PARAMS:
        raise ValueError(f"Unknown estimate_param: {estimate_param!r}")

    orientation = str(params.get("orientation", "horizontal"))
    elem_kind = str(params.get("elem_kind", "Circle"))

    r = float(params["r"])
    C0 = float(params["C0"])
    ca = float(params["ca"])
    gamma = float(params["gamma"])
    target = float(params["target_Lmax"])

    source_thickness_modifier = float(params.get("source_thickness_modifier", 1.0))
    alpha_t_in = params.get("alpha_t")
    alpha_l_in = params.get("alpha_l")
    alpha_t_in = None if alpha_t_in in (None, "") else float(alpha_t_in)
    alpha_l_in = None if alpha_l_in in (None, "") else float(alpha_l_in)

    tolerance = params.get("tolerance")
    L_tol = (float(inv.L_TOLERANCE_DEFAULT) if tolerance in (None, "")
             else float(tolerance))
    max_stagnation = params.get("max_stagnation")
    max_stagnation = (int(inv.MAX_STAGNATION_DEFAULT) if max_stagnation in (None, "")
                      else int(max_stagnation))

    r_eff = r if estimate_param == "r" else r * source_thickness_modifier

    # Resolve search bounds (explicit override else PARAM_SEARCH_DEFAULTS).
    pdefs = inv.PARAM_SEARCH_DEFAULTS.get(estimate_param, {})
    lb = params.get("lower_bound")
    ub = params.get("upper_bound")
    lb = None if lb in (None, "") else float(lb)
    ub = None if ub in (None, "") else float(ub)

    if lb is None or ub is None:
        if estimate_param in ("alpha_t", "alpha_l"):
            lb = float(pdefs.get("lower", 1e-3)) if lb is None else lb
            ub = float(pdefs.get("upper", 1.0)) if ub is None else ub
        elif estimate_param == "r":
            lb = float(pdefs.get("lower", 0.5)) if lb is None else lb
            ub = float(pdefs.get("upper", 8.0)) if ub is None else ub
        else:  # C0, ca, gamma -> factor-based bounds around the base value
            base_map = {"C0": C0, "ca": ca, "gamma": gamma}
            base = float(base_map[estimate_param])
            raw_lb = float(pdefs.get("factor_lower", 0.5)) * base
            raw_ub = float(pdefs.get("factor_upper", 2.0)) * base
            min_abs = float(pdefs.get("min_abs", raw_lb))
            max_abs = float(pdefs.get("max_abs", raw_ub))
            lb = raw_lb if lb is None else lb
            ub = raw_ub if ub is None else ub
            lb = max(min_abs, lb)
            ub = min(max_abs, ub)

    if not (np.isfinite(lb) and np.isfinite(ub) and lb < ub):
        raise ValueError(f"Invalid search bounds: lower={lb}, upper={ub}")

    # Fixed parameters, mirroring process_input_file_with_logging.
    fixed = {"r": r_eff, "C0": C0, "ca": ca, "gamma": gamma}
    if estimate_param == "alpha_t":
        fixed["alpha_l"] = alpha_l_in if alpha_l_in is not None else inv.FIXED_ALPHA_L
    elif estimate_param == "alpha_l":
        fixed["alpha_t"] = alpha_t_in if alpha_t_in is not None else inv.FIXED_ALPHA_T
    else:
        fixed["alpha_t"] = (alpha_t_in if alpha_t_in is not None
                            else inv.ALPHA_T_WHEN_ESTIMATING_OTHERS)
        fixed["alpha_l"] = (alpha_l_in if alpha_l_in is not None
                            else inv.ALPHA_L_WHEN_ESTIMATING_OTHERS)

    p_hat, L, sim = inv.estimate_parameter_scanned(
        estimate_param, lb, ub, fixed, target,
        orientation=orientation, elem_kind=elem_kind,
        L_tolerance=L_tol, param_defaults=pdefs, max_stagnation=max_stagnation,
    )

    converged = (L is not None) and np.isfinite(L) and abs(L - target) <= L_tol

    result_arr = xaxis = yaxis = None
    if sim is not None and getattr(sim, "result", None) is not None:
        result_arr = np.asarray(sim.result, dtype=float)
        xaxis = np.asarray(sim.xaxis, dtype=float)
        yaxis = np.asarray(sim.yaxis, dtype=float)

    return AEMInverseResult(
        estimate_param=estimate_param,
        recovered_value=float(p_hat),
        achieved_L_max=(float(L) if L is not None and np.isfinite(L) else None),
        target_L_max=target,
        orientation=orientation,
        elem_kind=elem_kind,
        lower_bound=float(lb),
        upper_bound=float(ub),
        fixed_params={k: float(v) for k, v in fixed.items()},
        result=result_arr,
        xaxis=xaxis,
        yaxis=yaxis,
        ca=float(fixed.get("ca", ca)),
        gamma=float(fixed.get("gamma", gamma)),
        converged=bool(converged),
    )


def available_samples() -> list[str]:
    """Return the bundled designer-export filenames (sorted)."""
    if not DESIGNER_EXPORTS_DIR.is_dir():
        return []
    return sorted(p.name for p in DESIGNER_EXPORTS_DIR.glob("*.json"))


def _resolve_sample(sample: str | None) -> Path:
    """Resolve a sample export name to a path inside DESIGNER_EXPORTS_DIR.

    Only basenames within the exports directory are permitted (no traversal).
    """
    name = os.path.basename(sample or DEFAULT_SAMPLE)
    path = DESIGNER_EXPORTS_DIR / name
    if not path.is_file():
        path = DESIGNER_EXPORTS_DIR / DEFAULT_SAMPLE
    return path


def build_config(params: dict[str, Any]):
    """Build an :class:`ATConfiguration` from job params.

    ``params`` may contain:
      - ``sample``: a bundled designer-export filename to seed elements/domain.
      - ``config_json``: a full designer config dict (round-trips through
        ATConfiguration.from_json's schema) — takes precedence over ``sample``.
      - scalar overrides: ``alpha_l``, ``alpha_t``, ``ca``, ``gamma``,
        ``dom_inc``.
    """
    # Imported lazily so importing this module (and app.py) never pulls in the
    # heavy AEM/matplotlib stack unless a job actually runs.
    from aem.at_config import ATConfiguration

    config_json = params.get("config_json")
    if config_json:
        config = ATConfiguration()
        _populate_config_from_dict(config, config_json)
    else:
        config = ATConfiguration.from_json(str(_resolve_sample(params.get("sample"))))

    for key in ("alpha_l", "alpha_t", "ca", "gamma", "dom_inc"):
        if params.get(key) is not None:
            setattr(config, key, float(params[key]))
    # beta is derived from alpha_l (matches ATConfiguration.from_json).
    config.beta = 1.0 / (2.0 * config.alpha_l)
    return config


def _populate_config_from_dict(config, data: dict[str, Any]) -> None:
    """Populate an ATConfiguration in-memory from a designer config dict.

    Mirrors ATConfiguration.from_json (which only reads from a file) so the
    Source Designer's JSON can be consumed without a temp file.
    """
    import math

    from aem.at_element import ATElement, ATElementType

    config.alpha_l = data.get("alpha_l", config.alpha_l)
    config.alpha_t = data.get("alpha_t", config.alpha_t)
    config.beta = 1.0 / (2.0 * config.alpha_l)
    config.ca = data.get("ca", config.ca)
    config.gamma = data.get("gamma", config.gamma)
    config.dom_xmin = data.get("dom_xmin", config.dom_xmin)
    config.dom_xmax = data.get("dom_xmax", config.dom_xmax)
    config.dom_ymin = data.get("dom_ymin", config.dom_ymin)
    config.dom_ymax = data.get("dom_ymax", config.dom_ymax)
    config.dom_inc = data.get("dom_inc", config.dom_inc)
    config.num_cp = data.get("num_cp", config.num_cp)
    config.num_terms = data.get("num_terms", config.num_terms)
    config.orientation = data.get("orientation", config.orientation)
    config.plot_aspect = data.get("plot_aspect", config.plot_aspect)

    config.elements = []
    for i, elem_data in enumerate(data.get("elements", [])):
        kind = str(elem_data["kind"]).lower()
        if kind == "circle":
            elem = ATElement(kind=ATElementType.Circle, x=float(elem_data["x"]),
                             y=float(elem_data["y"]), c=float(elem_data["c"]),
                             r=float(elem_data["r"]))
        elif kind == "line":
            theta_deg = elem_data.get("theta", 90)
            elem = ATElement(kind=ATElementType.Line, x=float(elem_data["x"]),
                             y=float(elem_data["y"]), c=float(elem_data["c"]),
                             r=float(elem_data["l"]) / 2.0,
                             theta=math.radians(float(theta_deg)))
        elif kind == "ellipse":
            theta_deg = elem_data.get("theta", 0)
            a = elem_data.get("a")
            b = elem_data.get("b")
            if a is None or b is None:
                raise ValueError("Ellipse requires 'a' and 'b' (semi-axes).")
            elem = ATElement(kind=ATElementType.Ellipse, x=float(elem_data["x"]),
                             y=float(elem_data["y"]), c=float(elem_data["c"]),
                             r=float(a), theta=math.radians(float(theta_deg)),
                             b=float(b))
        else:
            raise ValueError(f"Unknown element kind: {elem_data['kind']}")
        elem.label = elem_data.get("label", f"Element {i + 1}")
        elem.id = elem_data.get("id", f"source_{i}")
        config.elements.append(elem)


def run_aem_forward(params: dict[str, Any]) -> AEMForwardResult:
    """Run an AEM forward simulation and return a pickle-able result.

    Builds the config, runs ``ATSimulation.run()``, then copies out only the
    plain arrays/scalars needed for plotting and reporting.
    """
    from aem.at_simulation import ATSimulation

    config = build_config(params)
    sim = ATSimulation(config)
    # at_simulation.py is kept byte-identical to the reference, including
    # plot_result(), which on a non-physical, single-sign field raises an opaque
    # matplotlib "Contour levels must be increasing". The reference's own
    # validate_solution() (run just before plotting) already classifies this as
    # result_max <= ca ("no donor above background") — e.g. tiny designer sources on
    # a coarse grid in vertical orientation, where no grid node lands in the small
    # positive donor region. Honour that classification in the web layer: surface the
    # reason the reference computed instead of the raw plotting error.
    try:
        sim.run()
    except Exception as exc:
        if getattr(sim, "validation_passed", None) is False:
            raise ValueError(
                "Simulation did not produce a physically meaningful plume "
                f"({getattr(sim, 'validation_reason', '') or 'failed validation'}). "
                "The source geometry is likely too small or sparse to resolve on the "
                "current grid increment — try larger/denser sources, a finer grid, or "
                "horizontal orientation."
            ) from exc
        raise
    return AEMForwardResult(
        result=np.asarray(sim.result, dtype=float),
        xaxis=np.asarray(sim.xaxis, dtype=float),
        yaxis=np.asarray(sim.yaxis, dtype=float),
        L_max=(float(sim.L_max) if sim.L_max is not None else None),
        ca=float(config.ca),
        gamma=float(config.gamma),
        orientation=str(config.orientation),
        num_elements=int(getattr(sim, "num_elements_original", len(config.elements))),
        interface_length=(float(sim.interface_length)
                          if getattr(sim, "interface_length", None) is not None else None),
        validation_passed=getattr(sim, "validation_passed", None),
        validation_reason=str(getattr(sim, "validation_reason", "") or ""),
        domain_extent={
            "xmin": float(config.dom_xmin), "xmax": float(config.dom_xmax),
            "ymin": float(config.dom_ymin), "ymax": float(config.dom_ymax),
        },
    )
