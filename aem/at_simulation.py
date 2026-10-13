# Written by Alvin Yadav
# Based on code from Willi Kappler and Anton Köhler

"""
AEM Transport Simulation: main simulation class and supporting functions.

This module implements the Analytic Element Method (AEM) transport model for
simulating steady-state contaminant plumes in groundwater. The core workflow is:

  1. Load a configuration of source elements (circles, lines, ellipses)
  2. For vertical orientation, add mirror images to enforce the
     water-table boundary condition
  3. Solve a least-squares system for Mathieu function expansion coefficients
     that satisfy the prescribed concentration on each element's boundary
  4. Evaluate the concentration field on a grid across the domain
  5. Post-process: find L_max (plume length), validate, plot, save results

The module uses multiprocessing to parallelize the grid evaluation and
vectorized Mathieu function calls to reduce numpy overhead across all
expansion orders simultaneously.
"""

# Python std library:
import math
import timeit
from datetime import timedelta
import logging
import json
import os
import sys
import platform

# External library:
import numpy as np
import matplotlib

# The backend must be chosen before pyplot is imported, i.e. before any config
# file can be read. Default to the non-interactive Agg backend so headless and
# batch runs keep working (run_tests.py renders from worker threads, where the
# GUI backends are unsafe).
#
# AEM_INTERACTIVE=1 opts out of forcing Agg and lets matplotlib auto-detect an
# interactive backend instead — macosx on macOS, TkAgg or QtAgg on Windows and
# Linux. No backend is hardcoded here, so this stays portable. main.py sets the
# variable automatically when the config has "show_plots": true; set it by hand
# for any other entry point.
_WANT_INTERACTIVE: bool = os.environ.get(
    "AEM_INTERACTIVE", "").strip().lower() in ("1", "true", "yes", "on")
if not _WANT_INTERACTIVE:
    matplotlib.use('Agg')

import matplotlib.pyplot as plt
import matplotlib.pyplot as plt_temp
import matplotlib as mpl
from matplotlib.ticker import MaxNLocator
from matplotlib.lines import Line2D
from multiprocessing import Pool, cpu_count
import multiprocessing

# Whether plt.show() can actually draw anything. Resolved from the backend
# matplotlib really ended up with rather than from what was requested:
# auto-detection falls back to Agg when no display is available (headless
# Linux, a machine without tkinter), and that fallback is silent.
INTERACTIVE_BACKEND: bool = matplotlib.get_backend().lower() != "agg"

# SciencePlots publication style. Guarded so the module still imports on a
# machine without scienceplots or without a LaTeX installation ('science'
# sets text.usetex, which needs latex on PATH).
try:
    import scienceplots  # noqa: F401  (registers the styles with matplotlib)
    plt.style.use('science')
except Exception as style_err:      # pragma: no cover — environment dependent
    print(f"WARNING: could not apply the 'science' plot style ({style_err}). "
          f"Falling back to the matplotlib default. "
          f"Install with: pip install scienceplots")

# Local imports:
from .at_config import ATConfiguration
from .at_element import ATElement, ATElementType
from .at_grid_export import grid_csv_bytes, grid_npz_bytes, write_grid_csv, write_grid_npz

logger = logging.getLogger(__name__)

# Output root for forward-model runs, relative to the working directory.
# Each run gets a subdirectory named <index>_<label> (see generate_run_label)
# holding input.pdf, plot.pdf, error.pdf and stats.txt.
RUNS_DIR = "sim_runs"

# Shared state for multiprocessing workers
# These module-level globals are populated in each worker process via
# _init_pool(). They allow _compute_point_shared() to access simulation
# state without pickling it on every task — which would be prohibitively
# expensive for 50k+ grid points.
_shared_elements = None
_shared_coeff = None
_shared_log_coeff = None
_shared_sign_coeff = None
_shared_num_terms = None
_shared_alpha_l = None
_shared_alpha_t = None
_shared_beta = None
_shared_ca = None
_shared_gamma = None

# The largest value that math.exp() and np.exp() can be given. Above it the
# answer does not fit in a float64: math.exp() raises OverflowError and
# np.exp() returns inf. exp(709.78) is about 1.8e308.
EXP_ARG_MAX = 709.0

# The value of |beta*x| where the field reconstruction stops using the plain
# product F * exp(beta*x) and switches to log space.
#
# This sits below EXP_ARG_MAX on purpose. F shrinks like exp(-beta*x) while
# exp(beta*x) grows, so the two run out of float64 range at roughly the same
# distance, but F gets there slightly first: it enters the denormal range,
# where it loses precision quietly without raising anything. Below this
# threshold the plain product gives exactly the same numbers the code produced
# before log space was added, so short domains are unaffected and pay nothing.
LOGSPACE_SWITCH = 600.0

def _init_pool(elements, coeff, num_terms, alpha_l, alpha_t, beta, ca, gamma,
               log_coeff=None, sign_coeff=None):
    """
    Pool initializer that copies simulation state into each worker process.

    Called once per worker at pool startup (not once per task). The state
    then stays resident in the worker for the lifetime of the pool, so
    individual task dispatches only need to pass the (x, y) coordinates.
    """
    global _shared_elements, _shared_coeff, _shared_num_terms
    global _shared_alpha_l, _shared_alpha_t, _shared_beta, _shared_ca, _shared_gamma
    global _shared_log_coeff, _shared_sign_coeff
    _shared_elements = elements
    _shared_coeff = coeff
    _shared_num_terms = num_terms
    _shared_alpha_l = alpha_l
    _shared_alpha_t = alpha_t
    _shared_beta = beta
    _shared_ca = ca
    _shared_gamma = gamma
    _shared_log_coeff = log_coeff
    _shared_sign_coeff = sign_coeff


def _compute_point_shared(args):
    """
    Worker-side entry point for the multiprocessing pool.

    Unpacks the (x, y) coordinates and delegates to _compute_point using
    the shared state that was set by _init_pool at worker startup.
    """
    x, y = args
    return _compute_point((
        x, y, _shared_elements, _shared_coeff,
        _shared_num_terms, _shared_alpha_l, _shared_alpha_t,
        _shared_beta, _shared_ca, _shared_gamma,
        _shared_log_coeff, _shared_sign_coeff
    ))


def _log_field_terms(x, y, elements, coeff, num_terms, alpha_l, alpha_t,
                     log_coeff=None, sign_coeff=None):
    """
    Return the log magnitude and the sign of every term that makes up F at
    (x, y), gathered from all elements into two flat arrays.

    Every term is coeff * angular * radial. The angular parts (ce and se) stay
    within a small range of values, so they are used as they are. Everything
    that gets extremely large or extremely small comes from the radial parts
    (Ke and Ko), so those are taken from log_Ke and log_Ko, which return the
    log magnitude instead of the value itself.

    When log_coeff / sign_coeff are supplied, they are used instead of
    computing log|coeff| from the coefficient vector.  This avoids the
    loss of information that happens when Dc * coeffs_hat underflows to
    zero in the stored coeff array.

    A term that is exactly zero comes back as log = -inf with sign = 0. The
    caller drops those.
    """
    total_terms = 2 * num_terms - 1
    orders_all = np.arange(num_terms)
    orders_odd = np.arange(1, num_terms) if num_terms > 1 else np.array([], dtype=int)
    use_log_coeff = log_coeff is not None

    logs = []
    signs = []
    with np.errstate(divide='ignore', invalid='ignore'):
        for idx, elem in enumerate(elements):
            eta, psi = elem.uv(x - elem.x, y - elem.y, alpha_l, alpha_t)
            block = coeff[idx * total_terms: (idx + 1) * total_terms]

            ce_vals = np.atleast_1d(elem.m.ce(orders_all, psi).real)
            log_ke, sgn_ke = elem.m.log_Ke(orders_all, eta)

            if use_log_coeff:
                lc = log_coeff[idx * total_terms: (idx + 1) * total_terms]
                sc = sign_coeff[idx * total_terms: (idx + 1) * total_terms]
                log_amp = lc[0::2] + np.log(np.abs(ce_vals))
                sgn_amp = sc[0::2] * np.sign(ce_vals)
            else:
                amp = block[0::2] * ce_vals
                log_amp = np.log(np.abs(amp))
                sgn_amp = np.sign(amp)

            logs.append(log_amp + np.atleast_1d(log_ke))
            signs.append(sgn_amp * np.atleast_1d(sgn_ke))

            if num_terms > 1:
                se_vals = np.atleast_1d(elem.m.se(orders_odd, psi).real)
                log_ko, sgn_ko = elem.m.log_Ko(orders_odd, eta)

                if use_log_coeff:
                    log_amp = lc[1::2] + np.log(np.abs(se_vals))
                    sgn_amp = sc[1::2] * np.sign(se_vals)
                else:
                    amp = block[1::2] * se_vals
                    log_amp = np.log(np.abs(amp))
                    sgn_amp = np.sign(amp)

                logs.append(log_amp + np.atleast_1d(log_ko))
                signs.append(sgn_amp * np.atleast_1d(sgn_ko))

    return np.concatenate(logs), np.concatenate(signs)


def _logspace_total(x, y, elements, coeff, num_terms, alpha_l, alpha_t, beta,
                    log_coeff=None, sign_coeff=None):
    """
    Work out total = F * exp(beta*x) without ever building F or exp(beta*x).

    Returns (total, cancellation_ratio).

    Computing the two factors separately only works while |beta*x| stays below
    about 709. Past that point F has shrunk to 0 and exp(beta*x) has grown to
    inf, and 0 * inf is nan. The product itself is still a perfectly ordinary
    number out there. It is only the two halves that cannot be written down on
    their own, because log|Ke| is close to -beta*x and the two nearly cancel.

    So the terms are summed as log magnitudes, beta*x is added in that same
    log form, and the exponential is taken once at the very end. Every
    intermediate value then stays inside float64 range no matter how far out x
    is, which is what removes the old limit on how large a domain can be.

    The sum is a logsumexp that also keeps track of signs. The largest term is
    taken out first, so every exponential actually evaluated has an argument of
    zero or less and cannot overflow.

    cancellation_ratio is max|term| divided by |sum|. It says how much of the
    answer was lost to terms of opposite sign cancelling each other out.
    Values of roughly 10 to 100 are normal and cost less than two decimal
    digits. A value near 1e10 means nearly all the precision has gone and the
    answer should not be trusted.
    """
    log_terms, sign_terms = _log_field_terms(
        x, y, elements, coeff, num_terms, alpha_l, alpha_t,
        log_coeff=log_coeff, sign_coeff=sign_coeff)

    keep = np.isfinite(log_terms) & (sign_terms != 0.0)
    if not np.any(keep):
        return 0.0, 1.0

    lt = log_terms[keep]
    st = sign_terms[keep]
    log_max = float(lt.max())
    s = float(np.sum(st * np.exp(lt - log_max)))
    if s == 0.0:
        return 0.0, np.inf

    log_total = log_max + math.log(abs(s)) + beta * x
    cancellation = 1.0 / abs(s)     # == max|term| / |sum|

    # log_total is the log of the answer. The line below turns it back into an
    # ordinary number with math.exp(), which raises OverflowError once its
    # argument passes EXP_ARG_MAX. This check guards only that final
    # conversion. It is not choosing between the plain product and log space,
    # which the caller already decided before calling this function.
    #
    # It should never trigger for a sensible solution, because folding beta*x
    # into the sum is exactly what keeps log_total bounded. If it does
    # trigger, the concentration really is enormous, which means the solve
    # went wrong. Capping the value instead of letting inf or nan escape stops
    # one bad point from spreading nan over the whole grid and breaking the
    # contour step that L_max depends on.
    if log_total > EXP_ARG_MAX:
        log_total = EXP_ARG_MAX
    return math.copysign(math.exp(log_total), s), cancellation


def _compute_point(args):
    """
    Evaluate the concentration field at a single (x, y) point.

    Sums contributions from every element's Mathieu function expansion,
    applies the exp(beta*x) advection term, and maps the transformed
    field to concentration using the donor/acceptor reaction stoichiometry:
      - Above the reaction threshold (F > ca): donor regime, C = (F - ca) / gamma
      - Below the threshold (F <= ca): acceptor regime, C = F - ca

    Points that fall inside a source element are clamped to the element's
    prescribed concentration (elem.c), overriding the Mathieu expansion.
    This handles both circles and ellipses via point-in-region tests.

    The Mathieu function calls are vectorized over the expansion order
    (ce(0:n, psi), Ke(0:n, eta), etc.) since the library's overhead per
    call dominates the underlying numerics for small n.
    """
    x, y, elements, coeff, num_terms, alpha_l, alpha_t, beta, ca, gamma = args[:10]
    log_coeff = args[10] if len(args) > 10 else None
    sign_coeff = args[11] if len(args) > 11 else None
    total_terms = 2 * num_terms - 1

    # Precompute order arrays once — reused across all elements
    orders_all = np.arange(num_terms)
    orders_odd = np.arange(1, num_terms) if num_terms > 1 else np.array([], dtype=int)

    # Use the plain product while it is safely in range and only fall back to
    # log space past that. Ordinary domains then give exactly the same numbers
    # as before log space was added, and pay nothing for it.
    # That matters because this function accounts for 67 to 88 percent of the runtime,
    # so the extra logarithm per term is worth skipping when it gains nothing.
    arg = beta * x
    total = None
    if abs(arg) <= LOGSPACE_SWITCH:
        F = 0.0
        for idx, elem in enumerate(elements):
            dx = x - elem.x
            dy = y - elem.y
            eta, psi = elem.uv(dx, dy, alpha_l, alpha_t)

            block = coeff[idx * total_terms: (idx + 1) * total_terms]

            # Batch all Mathieu orders into a single call each
            ce_vals = elem.m.ce(orders_all, psi).real
            Ke_vals = elem.m.Ke(orders_all, eta).real

            Fi = block[0] * ce_vals[0] * Ke_vals[0]

            if num_terms > 1:
                se_vals = elem.m.se(orders_odd, psi).real
                Ko_vals = elem.m.Ko(orders_odd, eta).real
                for j in range(1, num_terms):
                    Fi += block[2*j - 1] * se_vals[j-1] * Ko_vals[j-1]
                    Fi += block[2*j    ] * ce_vals[j]   * Ke_vals[j]

            F += Fi

        total = F * math.exp(arg)
        if not math.isfinite(total):
            # Came out as nan or inf, so redo this point in log space.
            total = None

    if total is None:
        total, _ = _logspace_total(x, y, elements, coeff, num_terms,
                                   alpha_l, alpha_t, beta,
                                   log_coeff=log_coeff, sign_coeff=sign_coeff)

    if total > ca:
        conc = (total - ca) / gamma
    else:
        conc = total - ca

    # Clamp interior points to the prescribed element concentration
    for elem in elements:
        dx = x - elem.x
        dy = y - elem.y
        if elem.kind == ATElementType.Circle:
            if dx*dx + dy*dy <= elem.r**2:
                conc = elem.c
                break
        if elem.kind == ATElementType.Ellipse:
            a = float(elem.r)
            b = float(elem.b if elem.b is not None else elem.r)
            ctheta, stheta = math.cos(elem.theta), math.sin(elem.theta)
            xp =  ctheta * dx + stheta * dy
            yp = -stheta * dx + ctheta * dy
            if (xp*xp) / (a*a) + (yp*yp) / (b*b) <= 1.0:
                conc = elem.c
                break

    return conc


def create_mirrored_element(elem):
    """
    Return a mirror image of an element reflected across the water table (y=0).

    Used in vertical orientation to enforce the water-table boundary condition.
    The image has y → -y, c → -c, and theta → -theta (for lines and ellipses).
    For circles, theta is set to pi/2 as a canonical value.
    """
    if elem.kind == ATElementType.Line:
        return ATElement(kind=elem.kind, x=elem.x, y=-elem.y,
                         c=-elem.c, r=elem.r, theta=-elem.theta)
    elif elem.kind == ATElementType.Ellipse:
        return ATElement(kind=elem.kind, x=elem.x, y=-elem.y,
                         c=-elem.c, r=elem.r, theta=-elem.theta, b=elem.b)
    else:
        return ATElement(kind=elem.kind, x=elem.x, y=-elem.y,
                         c=-elem.c, r=elem.r, theta=math.pi / 2)


# Timing helper
class _PhaseTimer:
    """
    Accumulates elapsed time for named simulation phases.

    Supports nested timing via a stack of (name, start_time) entries.
    Calling start(name) pushes a new timing entry; stop() pops the most
    recent entry and adds its elapsed time to phases[name]. If the same
    name is started multiple times, the times accumulate — useful for
    phases like conc_array that may run more than once (e.g., when the
    domain is dynamically extended).
    """
    def __init__(self):
        self.phases = {}
        self._stack = []

    def start(self, name):
        self._stack.append((name, timeit.default_timer()))

    def stop(self):
        if self._stack:
            name, t0 = self._stack.pop()
            elapsed = timeit.default_timer() - t0
            self.phases[name] = self.phases.get(name, 0.0) + elapsed
            return elapsed
        return 0.0

    def report(self):
        total = sum(self.phases.values())
        lines = ["\n=== PHASE TIMING REPORT ==="]
        for name, elapsed in self.phases.items():
            pct = (elapsed / total * 100) if total > 0 else 0
            lines.append(f"  {name:<35} {elapsed:8.2f}s  ({pct:5.1f}%)")
        lines.append(f"  {'TOTAL':<35} {total:8.2f}s")
        return "\n".join(lines)


class ATSimulation:
    """
    Orchestrator for an AEM transport simulation.

    Holds the configuration, solved coefficient vector, computed concentration
    grid, and post-processing outputs (L_max, interface length, plots).
    A single run is driven by the run() method which executes the full
    pipeline from setup through saving plots.

    Attributes
    ----------
    config : ATConfiguration
        All physical parameters, element definitions, and domain extents.
    coeff : np.ndarray
        Flat coefficient vector from solve_system. Length = num_elements *
        (2 * num_terms - 1). Indexed as coeff[i*total_terms:(i+1)*total_terms]
        for element i.
    xaxis, yaxis : np.ndarray
        1D coordinate arrays for the evaluation grid.
    result : np.ndarray
        2D concentration grid with shape (len(yaxis), len(xaxis)).
    L_max : int or None
        Furthest x-extent of the 0-concentration contour, in meters.
    interface_length : float or None
        Total polyline length of the 0-contour, in meters.
    z_min_reached : float or None
        Deepest y-coordinate (most negative) touched by the 0-contour, in
        meters. Used by check_vertical_adequacy to detect capping against
        the bottom (dom_ymin) boundary.
    export_paths : list of str
        Paths of the concentration-grid file(s) written by run() — a CSV, an
        NPZ, both, or empty depending on config.concentration_output. See
        at_grid_export for the formats.
    timer : _PhaseTimer
        Accumulates elapsed time per pipeline phase.
    """

    def __init__(self, config: ATConfiguration):
        self.config: ATConfiguration = config
        self.coeff: np.ndarray = np.zeros((10, 10))
        self.xaxis: np.ndarray = np.arange(0, 10, 1)
        self.yaxis: np.ndarray = np.arange(0, 10, 1)
        self.result: np.ndarray = np.zeros((10, 10))
        self.num_elements_original = 0
        self.L_max = None
        self.interface_length = None
        self.z_min_reached = None
        # Filled by run() with the grid file(s) written; stays empty when
        # config.concentration_output is "none".
        self.export_paths = []
        self.validation_passed = None
        self.validation_reason = ""
        # Set by solve_system; also serves as the "has the system been solved"
        # marker, since self.coeff starts as a placeholder rather than None.
        self.solve_info = None
        self.probe_results = []
        self.timer = _PhaseTimer()

    def run(self):
        """
        Execute the full simulation pipeline end-to-end.

        Pipeline stages:
          1. Element setup — for vertical orientation, adds mirror images
             for water-table boundary conditions.
             Computes each element's Mathieu parameter q and outline points.
          2. solve_system — least-squares fit of expansion coefficients to
             match prescribed concentrations on all element boundaries.
          3. conc_array — parallel evaluation of the concentration field on
             the domain grid.
          4. Dynamic domain extension — if the plume reaches the x-boundary
             (dom_xmax) or the bottom z-boundary (dom_ymin), extends that
             boundary and recomputes. Repeats up to MAX_EXTENSIONS times.
             dom_ymax is never extended: in vertical orientation it is pinned
             at the water table (y=0). Avoids wasting a full fine-grid pass on
             an undersized domain.
          5. Post-processing — L_max calculation, x/vertical domain and
             concentration range checks.
          6. Output — input plot, statistics file, error plot, result plot,
             all saved under sim_runs/<run_index>_<label>/.
        """
        if len(self.config.elements) < 1:
            raise ValueError("Simulation requires at least one element.")

        self.num_elements_original = len(self.config.elements)
        self.timer.start("element_setup")
        if self.config.orientation == "vertical":
            # Build the full element list: each source gets a mirror image.
            updated_elements = []
            for elem in self.config.elements:
                if elem.y > -(elem.r*np.sin(elem.theta)+0.01):
                    raise ValueError(f"Element '{elem.id}' must have y < -(r+0.01) for vertical orientation.")
                updated_elements.append(elem)
                mirrored = create_mirrored_element(elem)
                mirrored.id = f"image_{elem.id}"
                updated_elements.append(mirrored)
            self.config.elements = updated_elements
            self.config.dom_ymax = 0

        alpha_t = self.config.alpha_t
        alpha_l = self.config.alpha_l
        beta = self.config.beta
        gamma = self.config.gamma
        ca = self.config.ca
        n = self.config.num_terms
        M = self.config.num_cp

        for elem in self.config.elements:
            elem.calc_d_q(alpha_t, alpha_l, beta, n)
            elem.set_outline(M)
        self.timer.stop()

        self.timer.start("solve_system")
        self.solve_system(alpha_l, alpha_t, beta, gamma, ca, n, M)
        self.timer.stop()

        self.timer.start("conc_array")
        self.conc_array(self.config.dom_xmin, self.config.dom_ymin,
                        self.config.dom_xmax, self.config.dom_ymax,
                        self.config.dom_inc)
        self.timer.stop()

        # Extend the domain iteratively until the plume fits, or until
        # MAX_EXTENSIONS is reached. Each round grows dom_xmax (horizontal
        # capping at the tip) and/or dom_ymin (vertical capping from below)
        # and triggers a fresh grid computation. The x step is graduated: a tip
        # sitting on the boundary grows by ~50%, one merely near it by ~10%, so
        # an ambiguous case is probed cheaply instead of jumping straight to a
        # much larger grid. dom_ymax is never grown:
        # in vertical orientation it is pinned at the water table (y=0) by the
        # mirror-image construction, so extending it would pull image elements
        # into the domain.
        # Disabling this (config "dynamic_domain": false) keeps the domain
        # exactly as specified in the config, which is what you want when
        # comparing runs on a fixed grid — at the cost of L_max being capped
        # whenever the plume runs off an edge. The check_domain_adequacy() and
        # check_vertical_adequacy() warnings below still flag that case.
        MAX_EXTENSIONS = 20 if getattr(self.config, "dynamic_domain", True) else 0
        self.timer.start("calculate_lmax")
        self.calculate_lmax()

        for ext_round in range(MAX_EXTENSIONS):
            if self.L_max is None:
                break
            domain_width = self.config.dom_xmax - self.config.dom_xmin
            domain_height = self.config.dom_ymax - self.config.dom_ymin
            max_x_dist = self.L_max - self.config.dom_xmin

            # Horizontal capping: the interface tip approaches dom_xmax.
            x_capped = max_x_dist >= 0.90 * domain_width
            # Vertical capping: the interface reaches down toward dom_ymin.
            z_capped = (self.z_min_reached is not None and
                        (self.z_min_reached - self.config.dom_ymin)
                        <= 0.10 * domain_height)

            if not x_capped and not z_capped:
                break  # plume fits in both directions

            if x_capped:
                # How hard the tip presses against the edge sets the step. A tip
                # on dom_xmax is certainly running off, so jump ahead; one merely
                # near it may already be the true L_max, so probe with a small
                # step and re-measure. If that probe comes back capped it takes
                # the generous branch next round, so nothing is lost.
                if max_x_dist >= 0.995 * domain_width:
                    grow = 0.5 * max(self.L_max, domain_width)
                else:
                    grow = 0.10 * domain_width
                # Guarantee progress even when L_max sits well inside dom_xmax.
                new_xmax = max(self.L_max + grow,
                               self.config.dom_xmax + 0.05 * domain_width)
                print(f"Dynamic domain extension #{ext_round+1}: "
                      f"dom_xmax {self.config.dom_xmax:.0f} -> {new_xmax:.0f} m  "
                      f"(L_max={self.L_max})")
                self.config.dom_xmax = new_xmax
            if z_capped:
                new_ymin = self.config.dom_ymin - 0.5 * domain_height
                print(f"Dynamic domain extension #{ext_round+1}: "
                      f"dom_ymin {self.config.dom_ymin:.0f} -> {new_ymin:.0f} m  "
                      f"(z_min_reached={self.z_min_reached:.1f})")
                self.config.dom_ymin = new_ymin
            self.timer.stop()

            self.timer.start(f"conc_array_ext{ext_round+1}")
            self.conc_array(self.config.dom_xmin, self.config.dom_ymin,
                            self.config.dom_xmax, self.config.dom_ymax,
                            self.config.dom_inc)
            self.timer.stop()

            self.timer.start("calculate_lmax")
            self.calculate_lmax()

        self.check_domain_adequacy()
        self.check_vertical_adequacy()
        self.check_concentration_range()
        self.validate_solution()
        self.probe_concentration()
        self.timer.stop()

        results_dir = os.path.join(RUNS_DIR)
        os.makedirs(results_dir, exist_ok=True)
        self.run_index = self.get_next_run_index(results_dir)
        self.run_dir = os.path.join(
            results_dir, f"{self.run_index:04d}_{self.generate_run_label()}")
        os.makedirs(self.run_dir, exist_ok=True)

        # Export the concentration grid. This runs after the dynamic
        # domain-extension loop above, so self.xaxis/yaxis/result are final
        fmt = getattr(self.config, "concentration_output", "none")
        if fmt != "none":
            self.timer.start("export_grid")
            stem = self.config.export_path or os.path.join(self.run_dir, "grid")
            if fmt in ("csv", "both"):
                self.export_paths.append(write_grid_csv(
                    stem + ".csv", self.xaxis, self.yaxis, self.result,
                    step=self.config.export_step))
            if fmt in ("npz", "both"):
                self.export_paths.append(write_grid_npz(
                    stem + ".npz", self.xaxis, self.yaxis, self.result,
                    step=self.config.export_step,
                    float32=self.config.export_npz_float32))
            print(f"Grid exported: {', '.join(self.export_paths)}")
            self.timer.stop()

        self.timer.start("plot_input")
        self.plot_input()
        self.timer.stop()

        self.timer.start("print_statistics")
        cpu_time = timedelta(seconds=int(sum(self.timer.phases.values())))
        self.print_statistics(cpu_time)
        self.timer.stop()

        self.timer.start("plot_result")
        self.plot_result()
        self.timer.stop()

        # Print timing report
        print(self.timer.report())

    # Coupling / decoupling helpers

    @staticmethod
    def _ke_log_magnitude(q: float, eta: float) -> float:
        """
        Estimate log10 |Ke_0(eta)| for a given Mathieu parameter q.

        Uses the leading-order asymptotic behavior of the radial Mathieu
        function:   Ke_0(eta) ~ exp(-sqrt(q) * exp(eta))
        and returns its base-10 logarithm.

        Used as a cheap proxy for how strongly element j's basis functions
        contribute at element i's location. When log|Ke| < ~-14, the
        contribution is at or below double-precision machine epsilon and
        the elements can be treated as decoupled for solving purposes.

        For q=0: returns 0 (near-source region where Ke is O(1)).
        """
        if q <= 0.0 or eta <= 0.0:
            return 0.0
        return -math.sqrt(q) * math.exp(eta) / math.log(10.0)

    def _are_elements_coupled(self, e_i, e_j, alpha_l, alpha_t,
                              log10_floor=-300.0):
        """
        Test whether two elements are close enough that cross-terms between
        them are numerically significant.

        Computes |Ke| in both directions (e_i's basis evaluated at e_j's
        center, and vice versa) and returns True if either magnitude exceeds
        10^log10_floor. The q-dependent criterion matters because Ke's
        decay rate is sqrt(q)-dependent: for small q, Ke stays significant
        out to larger eta than for large q.

        The floor sits just above float64's underflow cliff (2.2e-308). The
        coupled solve is exact down to |Ke| ~ 1e-304 and only breaks once the
        cross-term underflows to zero in the matrix, so every representable
        interaction is worth keeping coupled.
        """
        if e_i is e_j:
            return True
        dx_ij = e_i.x - e_j.x
        dy_ij = e_i.y - e_j.y
        eta_ij, _ = e_j.uv(dx_ij, dy_ij, alpha_l, alpha_t)
        log_ke_j = self._ke_log_magnitude(e_j.q, eta_ij)
        dx_ji = e_j.x - e_i.x
        dy_ji = e_j.y - e_i.y
        eta_ji, _ = e_i.uv(dx_ji, dy_ji, alpha_l, alpha_t)
        log_ke_i = self._ke_log_magnitude(e_i.q, eta_ji)
        coupled = max(log_ke_i, log_ke_j) > log10_floor
        logger.info(f"  Coupling: ({e_i.x},{e_i.y})<->({e_j.x},{e_j.y}): "
                     f"log|Ke|={max(log_ke_i, log_ke_j):.1f} -> "
                     f"{'COUPLED' if coupled else 'DECOUPLED'}")
        return coupled

    def _find_coupling_groups(self, elements, alpha_l, alpha_t):
        """
        Partition elements into groups that can be solved together.

        Union-find over _are_elements_coupled gives connected components, but
        that relation is transitive while the float64 limit is pairwise: a
        chain of elements each coupled to its neighbour can span far enough
        that the two ends underflow to zero in the matrix. Each component is
        therefore split again, left to right, so that every element stays
        coupled to the first element of its own group.

        Returns a list of groups, each a list of element indices.
        """
        ne = len(elements)
        parent = list(range(ne))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
        for i in range(ne):
            for j in range(i + 1, ne):
                if self._are_elements_coupled(elements[i], elements[j],
                                              alpha_l, alpha_t):
                    union(i, j)
        components = {}
        for i in range(ne):
            components.setdefault(find(i), []).append(i)

        groups = []
        for comp in components.values():
            if len(comp) < 2:
                groups.append(comp)
                continue
            chunk = []
            for idx in sorted(comp, key=lambda k: elements[k].x):
                if chunk and not self._are_elements_coupled(
                        elements[chunk[0]], elements[idx], alpha_l, alpha_t):
                    groups.append(chunk)
                    chunk = []
                chunk.append(idx)
            groups.append(chunk)
        return groups

    # Matrix building (vectorized Mathieu)

    def build_row(self, elem, eta, psi, n):
        """
        Build one element's contribution to a coefficient-matrix row.

        Returns a list of length (2n - 1) containing the Mathieu basis
        function products at the given (eta, psi):
          [ce_0*Ke_0, se_1*Ko_1, ce_1*Ke_1, se_2*Ko_2, ce_2*Ke_2, ...]

        The full matrix row for a given control point is built by
        concatenating these per-element blocks.
        """
        orders_all = np.arange(n)
        ce_vals = elem.m.ce(orders_all, psi).real
        Ke_vals = elem.m.Ke(orders_all, eta).real

        row = [ce_vals[0] * Ke_vals[0]]
        if n > 1:
            orders_odd = np.arange(1, n)
            se_vals = elem.m.se(orders_odd, psi).real
            Ko_vals = elem.m.Ko(orders_odd, eta).real
            for j in range(1, n):
                row.append(se_vals[j-1] * Ko_vals[j-1])
                row.append(ce_vals[j]   * Ke_vals[j])
        return row

    def _build_group_system(self, group_indices, elements,
                            alpha_l, alpha_t, beta, ca, gamma, n):
        """
        Assemble the least-squares matrix A and RHS vector b for a group
        of elements, together with the diagonal equilibration factors
        (Dr, Dc) that _equilibrate applies to them.

        For each element pair (i, j) in the group, evaluates element j's
        Mathieu basis functions at all of element i's control points in a
        single batched call.

        Self-element blocks along the diagonal use eta=0 for line elements.

        Returns (A, b, Dr, Dc, b_eq_direct, log_Dc, Dc_out).

        b_eq_direct is the equilibrated RHS computed directly as T, bypassing
        both the intermediate product Dr*b (which underflows for far-away
        elements) and the common exp(-beta*x0) factor (which underflows once
        a group sits past ~2800 m).  Dropping that factor scales the solved
        coefficients by exp(+beta*x0), so there are two column scales:

          Dc     - group-relative, exp(-beta*(col_x - x0)); builds A_eq
          Dc_out - exp(-beta*col_x); converts solved coefficients to real
                   space, with x0 cancelling exactly

        log_Dc is the unclipped log(Dc_out) per coefficient slot, for use in
        log-space evaluation when Dc_out itself underflows.
        """
        group_elements = [elements[k] for k in group_indices]
        ng = len(group_elements)
        total_terms = 2 * n - 1
        orders_all = np.arange(n)
        orders_odd = np.arange(1, n) if n > 1 else np.array([], dtype=int)

        # Precompute outline coordinates and control-point counts
        num_cp_per = [len(e.outline) for e in group_elements]
        total_rows = sum(num_cp_per)
        total_cols = ng * total_terms

        A = np.zeros((total_rows, total_cols))
        b = np.zeros(total_rows)

        elem_x = np.array([e.x for e in group_elements], dtype=float)
        # x0 is the group's own centre.  It only has to keep the *within-group*
        # factors exp(+/-beta*(x - x0)) representable, so it is never clamped
        # against an absolute bound: a group far downstream simply gets a large
        # x0.  The common exp(-beta*x0) factor is divided out of the RHS below
        # and folded back into the returned column scales, so it never has to
        # be formed.
        x0 = float(np.mean(elem_x)) if ng else 0.0

        row_x = (np.concatenate([np.array([p[0] for p in e.outline], dtype=float)
                                 for e in group_elements])
                 if ng else np.zeros(0))
        col_x = np.repeat(elem_x, total_terms)

        # A group whose own x-span exceeds the float64 exponent range cannot be
        # equilibrated by any single x0; such elements are never coupled, so
        # this only fires when decoupling is disabled.
        if ng:
            half_span = beta * (float(np.max(elem_x)) - float(np.min(elem_x))) / 2.0
            if half_span > EXP_ARG_MAX - 2.0:
                raise ValueError(
                    f"Element group spans {float(np.max(elem_x)) - float(np.min(elem_x)):.0f} m, "
                    f"which exceeds the range a single solve can equilibrate "
                    f"(limit {2.0 * (EXP_ARG_MAX - 2.0) / beta:.0f} m at beta={beta:g}). "
                    f"Enable allow_decoupling so distant elements are solved separately.")

        Dr = np.exp(np.clip(beta * (row_x - x0), -EXP_ARG_MAX, EXP_ARG_MAX))
        # Column scale used to build A_eq: group-relative, always O(1).
        Dc = np.exp(np.clip(-beta * (col_x - x0), -EXP_ARG_MAX, EXP_ARG_MAX))
        # Column scale used to convert solved coefficients back to real space.
        # Because b_eq_direct below drops the common exp(-beta*x0) factor, the
        # solution comes out scaled by exp(+beta*x0); absorbing that here makes
        # x0 cancel exactly, leaving exp(-beta*col_x).
        Dc_out = np.exp(np.clip(-beta * col_x, -EXP_ARG_MAX, EXP_ARG_MAX))
        log_Dc = -beta * col_x             # unclipped, for log-space eval

        # b_eq_direct: the equilibrated RHS, with the common exp(-beta*x0)
        # factor divided out so it stays O(T) instead of underflowing.
        # Mathematically Dr[i]*b[i] = T * exp(-beta*x0) for every CP of
        # the same element, regardless of x_cp.
        b_eq_direct = np.zeros(total_rows)

        row_offset = 0
        for i_local, e_i in enumerate(group_elements):
            ncp_i = num_cp_per[i_local]
            outline_x = np.array([p[0] for p in e_i.outline])
            outline_y = np.array([p[1] for p in e_i.outline])

            T_i = self._f_target_prefactor(e_i, ca, gamma)
            b_eq_direct[row_offset:row_offset + ncp_i] = T_i

            # Fill b vector: prescribed F-space boundary values
            for cp_idx in range(ncp_i):
                b[row_offset + cp_idx] = self.f_target(
                    outline_x[cp_idx], e_i, ca, gamma, beta)

            # Fill A columns: each element j contributes one block
            for j_local, e_j in enumerate(group_elements):
                dx = outline_x - e_j.x
                dy = outline_y - e_j.y

                # Compute (eta, psi) for all control points
                etas = np.empty(ncp_i)
                psis = np.empty(ncp_i)
                for cp_idx in range(ncp_i):
                    etas[cp_idx], psis[cp_idx] = e_j.uv(
                        dx[cp_idx], dy[cp_idx], alpha_l, alpha_t)

                # A line's own control points sit on the slit, at eta = 0.
                # Take psi from the element's own parametrisation rather than
                # from uv(): on the slit the acosh branch decides which face a
                # point lies on from a quantity that is zero in exact
                # arithmetic, so the face is otherwise set by rounding noise,
                # which flips the sign of every odd (se*Ko) basis function.
                if e_j.kind == ATElementType.Line and i_local == j_local:
                    etas[:] = 0.0
                    if e_j.outline_psi is not None:
                        psis[:] = e_j.outline_psi

                # Batch Mathieu: all orders × all control points in one call
                ce_vals = e_j.m.ce(orders_all, psis).real  # (n, ncp_i)
                Ke_vals = e_j.m.Ke(orders_all, etas).real  # (n, ncp_i)

                col_start = j_local * total_terms
                A[row_offset:row_offset+ncp_i, col_start] = \
                    ce_vals[0] * Ke_vals[0]

                if n > 1:
                    se_vals = e_j.m.se(orders_odd, psis).real  # (n-1, ncp_i)
                    Ko_vals = e_j.m.Ko(orders_odd, etas).real  # (n-1, ncp_i)
                    for j in range(1, n):
                        A[row_offset:row_offset+ncp_i, col_start + 2*j-1] = \
                            se_vals[j-1] * Ko_vals[j-1]
                        A[row_offset:row_offset+ncp_i, col_start + 2*j] = \
                            ce_vals[j] * Ke_vals[j]

            row_offset += ncp_i

        return A, b, Dr, Dc, b_eq_direct, log_Dc, Dc_out

    @staticmethod
    def _equilibrate(A, b, Dr, Dc, b_eq_direct=None):
        """
        Scale the system as A -> Dr A Dc and b -> Dr b before solving it.

        Solve the scaled system for x_hat, then return x = Dc * x_hat.

        Each boundary point asks for b_i = (C*gamma + ca) * exp(-beta*x_i).
        Sources at different x therefore ask for values that differ by many orders
        of magnitude, 12 orders for two sources 110 m apart at alpha_l = 2.
        lstsq minimises the total squared error over all rows at once, so the rows
        belonging to the downstream source count for almost nothing and the concentration
        it asked for is ignored. After scaling, every source states its requested
        concentration at a similar size, so all of them count.

        The condition number never sees this, because the size difference is
        in b and not in A.

        If the system were square with an exact solution this would change
        nothing: scaled and unscaled answers agree to about 1e-16. It changes
        the result only because there are many more equations than unknowns
        (200 equations for 26 unknowns), and then the row factors decide which
        equations the solver tries hardest to satisfy.
        """
        b_eq = b_eq_direct if b_eq_direct is not None else b * Dr
        return A * Dr[:, None] * Dc[None, :], b_eq

    def _solve_scaled_lstsq(self, A, b, rcond=1e-10):
        """
        Solve A @ x = b in the least-squares sense with row and column scaling.

        Row scaling: each row divided by its max-abs value — prevents rows
        with very different magnitudes (near-source vs far-field control
        points) from dominating the least-squares residual.

        Column scaling: each column divided by its max-abs value — corrects
        for columns that are uniformly small, which would otherwise inflate
        the condition number without reflecting genuine numerical instability.
        The column scales are folded back into the returned coefficients.

        Returns (coeffs, condition_number) where coeffs are in the original
        (unscaled) space and condition_number is that of the doubly-scaled
        matrix.
        """
        # Row scaling
        row_scales = np.max(np.abs(A), axis=1)
        row_scales = np.where(row_scales < 1e-300, 1.0, row_scales)
        A_rs = A / row_scales[:, None]
        b_rs = b / row_scales

        # Column scaling
        col_scales = np.max(np.abs(A_rs), axis=0)
        col_scales = np.where(col_scales < 1e-300, 1.0, col_scales)
        A_scaled = A_rs / col_scales[None, :]

        coeffs_scaled, residuals, rank, sv = np.linalg.lstsq(A_scaled, b_rs, rcond=rcond)
        # Undo column scaling to recover coefficients in original space
        coeffs = coeffs_scaled / col_scales
        cond = np.inf
        if sv is not None and len(sv) > 0:
            cond = sv[0] / sv[-1] if sv[-1] > 0 else np.inf
        return coeffs, cond

    # Solve strategies

    def _solve_decoupled_iterative(self, elements, groups, n, total_terms,
                                   alpha_l, alpha_t, beta, ca, gamma):
        """
        Gauss-Seidel iteration over independent element groups with
        log-space cross-group corrections.

        Each group is solved as a self-contained least-squares system, but
        the RHS is corrected by subtracting the known field contributions
        from all other groups. Cross-group contributions are computed in
        log space (via _logspace_total) so they survive even when the Ke
        values underflow to zero in double precision.

        The correction works in the "total" space (F*exp(beta*x)) where
        values are O(1), then converts back to the equilibrated b_eq
        space for the solve.
        """
        num_elements = len(elements)
        group_data = []
        for group in groups:
            A, b_original, Dr, Dc, b_eq_direct, log_Dc_g, Dc_out_g = \
                self._build_group_system(
                    group, elements, alpha_l, alpha_t, beta, ca, gamma, n)
            control_points = []
            T_per_cp = []
            for g_idx in group:
                T_i = self._f_target_prefactor(elements[g_idx], ca, gamma)
                for (x_cp, y_cp) in elements[g_idx].outline:
                    control_points.append((x_cp, y_cp))
                    T_per_cp.append(T_i)
            group_data.append({
                'indices': group, 'A': A, 'Dr': Dr, 'Dc': Dc,
                'Dc_out': Dc_out_g,
                'b_eq_direct': b_eq_direct, 'log_Dc': log_Dc_g,
                'control_points': control_points,
                'T_per_cp': np.array(T_per_cp),
            })

        coeff = np.zeros(num_elements * total_terms)
        log_coeff = np.full(num_elements * total_terms, -np.inf)
        sign_coeff = np.zeros(num_elements * total_terms)
        max_iter = 8
        tol = 1e-6

        # Collect other-group element indices for each group
        other_indices = []
        for gi in range(len(groups)):
            others = []
            for gj in range(len(groups)):
                if gi != gj:
                    others.extend(groups[gj])
            other_indices.append(others)

        for iteration in range(max_iter):
            log_coeff_old = log_coeff.copy()
            for gi, gd in enumerate(group_data):
                # b_eq_direct = T * exp(-beta*x0) for each CP.
                # The target in "total" space is T (= f_target_prefactor).
                # Subtract other groups' contribution (computed in log space)
                # to get the corrected target, then convert back to b_eq.
                b_eq = gd['b_eq_direct'].copy()

                if iteration > 0 and len(other_indices[gi]) > 0:
                    other_elems = [elements[j] for j in other_indices[gi]]
                    other_coeff = np.concatenate(
                        [coeff[j*total_terms:(j+1)*total_terms]
                         for j in other_indices[gi]])
                    other_lc = np.concatenate(
                        [log_coeff[j*total_terms:(j+1)*total_terms]
                         for j in other_indices[gi]])
                    other_sc = np.concatenate(
                        [sign_coeff[j*total_terms:(j+1)*total_terms]
                         for j in other_indices[gi]])

                    for cp_idx, (x_cp, y_cp) in enumerate(gd['control_points']):
                        total_other, _ = _logspace_total(
                            x_cp, y_cp, other_elems, other_coeff, n,
                            alpha_l, alpha_t, beta,
                            log_coeff=other_lc, sign_coeff=other_sc)
                        # b_eq_direct is T, so the corrected target is
                        # T - total_other = b_eq_direct * (1 - total_other/T)
                        T_i = gd['T_per_cp'][cp_idx]
                        if abs(T_i) > 1e-300:
                            b_eq[cp_idx] *= (1.0 - total_other / T_i)

                A_eq = gd['A'] * gd['Dr'][:, None] * gd['Dc'][None, :]
                coeffs_hat, _ = self._solve_scaled_lstsq(A_eq, b_eq)
                coeffs_local = gd['Dc_out'] * coeffs_hat
                for local_idx, global_idx in enumerate(gd['indices']):
                    gs = global_idx * total_terms
                    ls = local_idx * total_terms
                    coeff[gs:gs+total_terms] = coeffs_local[ls:ls+total_terms]
                    hat_block = coeffs_hat[ls:ls+total_terms]
                    with np.errstate(divide='ignore'):
                        log_coeff[gs:gs+total_terms] = (
                            np.log(np.abs(hat_block)) + gd['log_Dc'][ls:ls+total_terms])
                    sign_coeff[gs:gs+total_terms] = np.sign(hat_block)

            both_finite = np.isfinite(log_coeff) & np.isfinite(log_coeff_old)
            if np.any(both_finite):
                delta = np.max(np.abs(log_coeff[both_finite]
                                      - log_coeff_old[both_finite]))
            else:
                delta = float('inf')
            logger.info(f"  Iteration {iteration+1}: max_log_delta={delta:.2e}")
            if iteration > 0 and delta < 0.01:
                self.solve_info["iterations"] = iteration + 1
                self.solve_info["max_log_delta"] = float(delta)
                self.solve_info["converged"] = True
                return coeff, log_coeff, sign_coeff

        self.solve_info["iterations"] = max_iter
        self.solve_info["max_log_delta"] = float(delta)
        self.solve_info["converged"] = False
        return coeff, log_coeff, sign_coeff

    def solve_system(self, alpha_l, alpha_t, beta, gamma, ca, n, M):
        """
        Top-level solver: choose the coupled or decoupled solve from the Ke
        coupling graph.

        Strategy:
          1. Link two elements when |Ke| between their centres exceeds 1e-300
             in either direction (_find_coupling_groups).
          2. If allow_decoupling is true and the graph splits into more than
             one group, solve the groups separately (_solve_decoupled_iterative).
             Each group's field at the other groups' control points is computed
             in log space and subtracted from their right-hand sides, iterating
             until the log coefficients settle. The condition number is not used.
          3. Otherwise, solve all elements as one equilibrated system.

        Decoupling keeps distant sources correct; it is not a speed-up. Along x
        the cross-term Ke decays roughly like exp(-beta*dx), so beyond about
        709/beta (2836 m at alpha_l = 2) it underflows to exactly zero in the
        coupled matrix, while the upstream plume still reaches the downstream
        source with O(1) strength. A coupled solve then misses an interaction
        that the log-space field evaluation includes, and past about twice that
        span the coupled system cannot be equilibrated at all.

        "Decoupled" groups therefore still interact; they are solved separately
        because their interaction cannot be held in a float64 matrix. The
        1e-300 floor sits just above float64 underflow, so pairs the coupled
        solve can still represent stay coupled.

        Set config "allow_decoupling": false to force the coupled solve. Distant
        groups are then solved inaccurately, and a group spanning beyond the
        equilibration limit raises ValueError.

        Coefficients go to self.coeff, self.log_coeff and self.sign_coeff, and a
        record of the decision to self.solve_info (written to the stats file by
        print_statistics).
        """
        elements = self.config.elements
        num_elements = len(elements)
        total_terms = 2 * n - 1
        allow_decoupling = getattr(self.config, "allow_decoupling", True)

        # Populated as the decision below is made; consumed by print_statistics
        # and available to batch drivers that want to aggregate solver outcomes.
        self.solve_info = {
            "cond": None,
            "decoupling_allowed": allow_decoupling,
            "n_coupling_groups": None,
            "groups": None,
            "iterations": None,
            "max_log_delta": None,
            "converged": None,
            "decision": None,
            "reason": None,
        }

        all_indices = list(range(num_elements))

        coupling_groups = self._find_coupling_groups(elements, alpha_l, alpha_t)
        self.solve_info["n_coupling_groups"] = len(coupling_groups)

        if allow_decoupling and len(coupling_groups) > 1:
            groups = coupling_groups

            self.solve_info["decision"] = "decoupled"
            self.solve_info["groups"] = [sorted(g) for g in groups]
            self.solve_info["reason"] = (
                f"Ke coupling graph (floor 1e-300) splits into {len(groups)} "
                f"groups; solved separately with log-space cross-group "
                f"corrections.")

            print("Decoupled solve")

            self.coeff, self.log_coeff, self.sign_coeff = \
                self._solve_decoupled_iterative(
                    elements, groups, n, total_terms,
                    alpha_l, alpha_t, beta, ca, gamma)
            return

        # Single coupling group or decoupling disabled: coupled solve.
        A, b, Dr, Dc, b_eq_direct, log_Dc, Dc_out = self._build_group_system(
            all_indices, elements, alpha_l, alpha_t, beta, ca, gamma, n)
        A_eq, b_eq = self._equilibrate(A, b, Dr, Dc, b_eq_direct)

        coeffs_hat, cond = self._solve_scaled_lstsq(A_eq, b_eq)
        coeffs = Dc_out * coeffs_hat

        self.coeff = np.zeros(num_elements * total_terms)
        self.log_coeff = np.full(num_elements * total_terms, -np.inf)
        self.sign_coeff = np.zeros(num_elements * total_terms)
        for li, gi in enumerate(all_indices):
            s = li * total_terms
            gs = gi * total_terms
            self.coeff[gs:gs+total_terms] = coeffs[s:s+total_terms]
            hat_block = coeffs_hat[s:s+total_terms]
            with np.errstate(divide='ignore'):
                self.log_coeff[gs:gs+total_terms] = (
                    np.log(np.abs(hat_block)) + log_Dc[s:s+total_terms])
            self.sign_coeff[gs:gs+total_terms] = np.sign(hat_block)

        self.solve_info["cond"] = cond
        self.solve_info["decision"] = "coupled"
        self.solve_info["reason"] = (
            f"Single coupling group (or decoupling disabled). "
            f"Condition number {cond:.3e}.")
        print("Coupled solve")

    # Boundary condition target

    @staticmethod
    def _f_target_prefactor(elem, ca, gamma):
        """Return T such that f_target(x) = T * exp(-beta*x)."""
        Ci = elem.c
        is_image = elem.id.lower().startswith("image")
        if Ci > 0 and not is_image:
            return Ci * gamma + ca
        if Ci < 0 and not is_image:
            return Ci + ca
        if Ci < 0 and is_image:
            return -(abs(Ci) * gamma + ca)
        if Ci > 0 and is_image:
            return -(Ci + ca)
        if Ci == 0 and not is_image:
            return ca
        return 0.0

    def f_target(self, x, elem, ca, gamma, beta):
        """
        Return the prescribed F-space value on an element's boundary at
        position x.

        The F-space is the transformed variable that the least-squares
        matrix equation solves for: F = (actual concentration reaction
        term) * exp(-beta*x). The exp(-beta*x) factor unwraps the
        advection term so the Mathieu expansion itself doesn't need to
        represent it.

        Different cases based on element type and sign:
          - Donor source (Ci > 0, not image):  (Ci*gamma + ca) * exp(-beta*x)
          - Acceptor source (Ci < 0, not image): (Ci + ca) * exp(-beta*x)
          - Image-donor (Ci < 0, image): -(image-donor counterpart)
          - Image-acceptor (Ci > 0, image): -(image-acceptor counterpart)

        The image-element cases have flipped signs to enforce the
        water-table mirror boundary condition at y=0.
        """
        Ci = elem.c
        is_image = elem.id.lower().startswith("image")
        if Ci > 0 and not is_image:
            return (Ci * gamma + ca) * np.exp(-beta * x)
        if Ci < 0 and not is_image:
            return (Ci + ca) * np.exp(-beta * x)
        if Ci < 0 and is_image:
            return -((abs(Ci) * gamma + ca) * np.exp(-beta * x))
        if Ci > 0 and is_image:
            return -((Ci + ca) * np.exp(-beta * x))
        if Ci == 0 and not is_image:
            return ca * np.exp(-beta * x)

    # Point evaluation (vectorized Mathieu)

    def calc_c(self, x, y):
        """
        Evaluate the concentration field at a single (x, y) point using
        the solved coefficient vector.

        This is the single-process counterpart to _compute_point used by
        the parallel grid evaluation. Used for on-demand evaluation at
        arbitrary points (e.g., for boundary validation or individual
        spot checks) after conc_array has populated self.result.

        The reaction-term mapping mirrors _compute_point:
          - F * exp(beta*x) > ca:  donor regime, C = (F*exp(beta*x) - ca) / gamma
          - F * exp(beta*x) <= ca: acceptor regime, C = F*exp(beta*x) - ca

        The switch between the plain product and log space matches
        _compute_point. These two functions have drifted apart from each other
        before, so keep any change to one in step with the other.
        """
        n = self.config.num_terms
        alpha_l = self.config.alpha_l
        alpha_t = self.config.alpha_t
        beta = self.config.beta
        total_coeffs = self.coeff
        total_terms = 2 * n - 1

        orders_all = np.arange(n)
        orders_odd = np.arange(1, n) if n > 1 else np.array([], dtype=int)

        arg = beta * x
        total = None
        if abs(arg) <= LOGSPACE_SWITCH:
            F = 0.0
            for idx, elem in enumerate(self.config.elements):
                dx = x - elem.x
                dy = y - elem.y
                eta, psi = elem.uv(dx, dy, alpha_l, alpha_t)
                coeffs = total_coeffs[idx * total_terms:(idx + 1) * total_terms]

                ce_vals = elem.m.ce(orders_all, psi).real
                Ke_vals = elem.m.Ke(orders_all, eta).real
                Fi = coeffs[0] * ce_vals[0] * Ke_vals[0]

                if n > 1:
                    se_vals = elem.m.se(orders_odd, psi).real
                    Ko_vals = elem.m.Ko(orders_odd, eta).real
                    for j in range(1, n):
                        Fi += coeffs[2*j-1] * se_vals[j-1] * Ko_vals[j-1]
                        Fi += coeffs[2*j]   * ce_vals[j]   * Ke_vals[j]
                F += Fi

            total = F * math.exp(arg)
            if not math.isfinite(total):
                total = None

        if total is None:
            total, _ = _logspace_total(
                x, y, self.config.elements, self.coeff,
                n, alpha_l, alpha_t, beta,
                log_coeff=getattr(self, 'log_coeff', None),
                sign_coeff=getattr(self, 'sign_coeff', None))

        if total > self.config.ca:
            return (total - self.config.ca) / self.config.gamma
        else:
            return total - self.config.ca

    def cancellation_ratio(self, x, y):
        """
        Return max|term| divided by |sum| for the field at (x, y).

        This is a precision check for the log-space path. The normal pipeline
        does not use it. Folding exp(beta*x) into the sum fixes values that are
        too large or too small to store, but it does nothing about terms of
        opposite sign cancelling each other, so this is the number to look at
        when a result far from the source looks wrong.

        Expect roughly 10 to 100 even far out, which costs under two decimal
        digits. If it climbs towards 1e10 then cancellation has eaten the
        answer, and logsumexp cannot help with that. It needs a different fix.
        """
        _, ratio = _logspace_total(
            x, y, self.config.elements, self.coeff, self.config.num_terms,
            self.config.alpha_l, self.config.alpha_t, self.config.beta,
            log_coeff=getattr(self, 'log_coeff', None),
            sign_coeff=getattr(self, 'sign_coeff', None))
        return ratio

    def probe_concentration(self, points=None):
        """
        Evaluate the concentration at specific points in the domain.

        A debugging aid, not part of the normal consumer output: it answers
        "what does the model actually predict at this exact location?" without
        having to read it off a contour plot or index into the result grid.

        :param points: iterable of (x, y). Defaults to config "probe_points".
        :return: list of (x, y, concentration) tuples.

        Sign convention follows calc_c: a positive value is a donor-regime
        concentration, a negative value is acceptor-regime. Points outside the
        computed domain are still evaluated — the analytic solution is defined
        everywhere — but are flagged, since they are usually a typo.
        """
        if points is None:
            points = getattr(self.config, "probe_points", []) or []
        if len(points) == 0:
            return []

        if self.solve_info is None:
            raise RuntimeError(
                "probe_concentration() requires a solved system; "
                "call run() or solve_system() first.")

        results = []
        print("\n=== CONCENTRATION PROBES ===")
        for pt in points:
            x, y = float(pt[0]), float(pt[1])
            c = float(self.calc_c(x, y))
            outside = not (self.config.dom_xmin <= x <= self.config.dom_xmax
                           and self.config.dom_ymin <= y <= self.config.dom_ymax)
            regime = "donor" if c > 0 else "acceptor"
            flag = "   [OUTSIDE DOMAIN]" if outside else ""
            print(f"  c({x:g}, {y:g}) = {c:.6g} mg/l  ({regime}){flag}")
            results.append((x, y, c))

        self.probe_results = results
        return results

    # Grid evaluation (parallel, platform-aware)

    def conc_array(self, xmin, ymin, xmax, ymax, inc):
        """
        Populate self.result with the concentration field evaluated on a
        regular grid spanning the requested extents.

        Coordinates are placed at [xmin, xmin+inc, ..., xmax] and similarly
        for y. The evaluation is parallelized across CPU cores, with each
        worker calling _compute_point_shared for its chunk of grid points.

        On Linux/macOS the default fork multiprocessing context is used
        (fast worker startup, shared memory with the parent). On Windows
        spawn is required; this is ~1 second slower but unavoidable.
        The chunksize is tuned so each worker handles ~25% of its share of
        points per dispatch, balancing parallelism against IPC overhead.
        """
        self.xaxis = np.arange(xmin, xmax + inc, inc)
        self.yaxis = np.arange(ymin, ymax + inc, inc)
        # Clamp to declared bounds — np.arange can overshoot by one step due to
        # floating-point rounding. Critical for vertical orientation where ymax=0
        # must be the exact upper limit so image elements (y > 0) never appear.
        self.xaxis = self.xaxis[self.xaxis <= xmax + 1e-9]
        self.yaxis = self.yaxis[self.yaxis <= ymax + 1e-9]

        xs, ys = np.meshgrid(self.xaxis, self.yaxis)
        coords = list(zip(xs.ravel(), ys.ravel()))

        pool_args = (
            self.config.elements, self.coeff, self.config.num_terms,
            self.config.alpha_l, self.config.alpha_t,
            self.config.beta, self.config.ca, self.config.gamma,
            getattr(self, 'log_coeff', None),
            getattr(self, 'sign_coeff', None),
        )

        nproc = cpu_count()
        chunksize = max(1, len(coords) // (nproc * 4))

        if platform.system() == 'Windows':
            ctx = multiprocessing.get_context('spawn')
        else:
            ctx = multiprocessing  # default fork context

        with ctx.Pool(processes=nproc, initializer=_init_pool,
                      initargs=pool_args) as pool:
            flat = pool.map(_compute_point_shared, coords, chunksize=chunksize)

        self.result = np.array(flat).reshape(xs.shape)
        self.result_tuple = (self.xaxis, self.yaxis, self.result)

    def grid_csv_bytes(self, step: int = 1) -> bytes:
        """
        Return the solved concentration grid as long-form CSV, in memory.

        The on-disk counterpart of the export written by run(), for a caller
        (e.g. a web download) that wants the bytes without leaving a file
        behind. Requires conc_array to have run. See at_grid_export for the
        format and the ``step`` argument.
        """
        return grid_csv_bytes(self.xaxis, self.yaxis, self.result, step=step)

    def grid_npz_bytes(self, step: int = 1, float32: bool = False) -> bytes:
        """
        Return the solved concentration grid as a compressed .npz, in memory.

        The compact, workbench-native counterpart of grid_csv_bytes — for a
        download or handoff that wants the native grid without leaving a file
        behind. Requires conc_array to have run. See at_grid_export for the
        layout and the ``float32`` option.
        """
        return grid_npz_bytes(self.xaxis, self.yaxis, self.result,
                              step=step, float32=float32)

    # Post-processing

    def generate_run_label(self):
        """
        Build the descriptive part of a run directory's name.

        Format: <N>el_<num_terms>terms_<acc|noacc>_inc<dom_inc>
        The run parameters live in the directory name so that `ls sim_runs/`
        alone tells you what each run was; the files inside are named by
        role only (input.pdf, plot.pdf, error.pdf, stats.txt).
        """
        n_elements = self.num_elements_original
        has_acceptor = any(elem.c < 0 for elem in self.config.elements)
        acceptor_str = "acc" if has_acceptor else "noacc"
        return (f"{n_elements}el_{self.config.num_terms}terms_"
                f"{acceptor_str}_inc{self.config.dom_inc}")

    def get_next_run_index(self, results_dir):
        """
        Return the next unused numeric run index for naming the output
        subdirectory.

        Scans <results_dir> for subdirectories whose name starts with a
        zero-padded integer (0001_..., 0002_...) and returns the highest + 1.
        Bare numeric names are also accepted so that directories produced
        before the descriptive-suffix scheme still count. Returns 1 if the
        directory doesn't exist or has no indexed subdirectories.
        """
        if not os.path.exists(results_dir):
            return 1
        max_index = 0
        for entry in os.listdir(results_dir):
            if os.path.isdir(os.path.join(results_dir, entry)):
                try:
                    max_index = max(max_index, int(entry.split("_")[0]))
                except ValueError:
                    continue
        return max_index + 1

    def calculate_lmax(self):
        """
        Extract the zero-concentration contour from self.result and compute:
          - self.L_max: the furthest x-coordinate reached by any zero-contour
            path (rounded to an integer meter).
          - self.interface_length: the total polyline length of the chosen
            contour path (the one with the largest max-x).
          - self.z_min_reached: the deepest y-coordinate touched by any
            zero-contour path (in meters), used to detect vertical capping
            against the bottom (dom_ymin) boundary.

        The zero-contour separates the donor-dominated region (C > 0) from
        the acceptor-dominated region (C < 0) and defines the plume
        envelope. L_max is the key diagnostic for plume extent.

        Uses matplotlib's contour extraction (on an off-screen figure that
        is immediately discarded) since it handles irregular grids and
        disconnected paths robustly.
        """
        fig_temp = plt_temp.figure()
        contour_temp = plt_temp.contour(self.result, levels=[0])
        paths = contour_temp.get_paths()
        chosen = None
        self.interface_length = None
        self.L_max = None
        self.z_min_reached = None

        if paths:
            max_x_overall = -np.inf
            min_row_overall = np.inf
            for p in paths:
                v = p.vertices
                if v is None or len(v) == 0:
                    continue
                max_x_path = np.max(v[:, 0])
                if max_x_path > max_x_overall:
                    max_x_overall = max_x_path
                    chosen = v
                # Track how close any part of the interface gets to the bottom
                # boundary. contour() returns row indices in v[:, 1]; row 0 maps
                # to dom_ymin, so the global minimum row over all paths marks the
                # deepest point the plume envelope reaches.
                min_row_overall = min(min_row_overall, float(np.min(v[:, 1])))

            if chosen is not None and len(chosen) > 1:
                # contour() gives back column indices in v[:, 0], and column 0
                # sits at dom_xmin, so dom_xmin has to be added on to turn an
                # index into an x coordinate. z_min_reached below does the same
                # thing for y. Without it, L_max would be a distance from the
                # left edge rather than an x position, which is not what the
                # rest of the code expects. run() and check_domain_adequacy
                # both compute L_max - dom_xmin, so the missing offset would
                # end up being counted twice.
                self.L_max = int(self.config.dom_xmin
                                 + max_x_overall * self.config.dom_inc)
                diffs = np.diff(chosen, axis=0)
                self.interface_length = float(
                    np.sum(np.hypot(diffs[:, 0], diffs[:, 1])) * self.config.dom_inc)

            if np.isfinite(min_row_overall):
                self.z_min_reached = (
                    self.config.dom_ymin + min_row_overall * self.config.dom_inc)

        plt_temp.close(fig_temp)

        if self.L_max is not None:
            print(f'Lmax = {self.L_max}')
            if self.interface_length is not None:
                print(f'Interface length = {self.interface_length:.3f} m')
        else:
            print("L_max: -")

    def check_domain_adequacy(self):
        """
        Warn if the computed plume reaches the edge of the domain.

        If L_max is within 5% of dom_xmax, the plume may actually extend
        further than the domain — the reported L_max is a lower bound, not
        the true value. Dynamic domain extension in run() will normally
        prevent this, but the check remains as a safety net.
        """
        if self.L_max is None:
            return
        domain_width = self.config.dom_xmax - self.config.dom_xmin
        max_x_distance = self.L_max - self.config.dom_xmin
        if max_x_distance >= 0.95 * domain_width:
            print(f"WARNING: L_max ({self.L_max:.1f} m) capped by x-domain boundary! "
                  f"({max_x_distance / domain_width * 100:.1f}% of width)")

    def check_vertical_adequacy(self):
        """
        Warn if the plume interface reaches the bottom (dom_ymin) boundary.

        The vertical analogue of check_domain_adequacy. If the zero-contour
        comes within 5% of the domain height of dom_ymin, the plume is capped
        from below and L_max may be under-reported: the part of the envelope
        that would reach furthest in x can be clipped off by a too-shallow
        domain, so the measured max-x is a lower bound. Dynamic domain
        extension in run() normally prevents this by growing dom_ymin
        downward; the check remains as a safety net (dynamic_domain off, or
        MAX_EXTENSIONS exhausted).

        dom_ymax is deliberately not checked: in vertical orientation it is
        pinned at the water table (y=0), where the interface legitimately
        terminates, so touching it is a physical feature, not a capping
        artifact.
        """
        if self.z_min_reached is None:
            return
        domain_height = self.config.dom_ymax - self.config.dom_ymin
        dist_from_bottom = self.z_min_reached - self.config.dom_ymin
        if dist_from_bottom <= 0.05 * domain_height:
            print(f"WARNING: plume interface reaches the bottom z-boundary "
                  f"(z_min_reached={self.z_min_reached:.1f} m, "
                  f"dom_ymin={self.config.dom_ymin:.1f} m)! "
                  f"L_max may be capped vertically.")

    def check_concentration_range(self):
        """
        Warn if computed grid concentrations fall outside the physical
        range defined by the element concentrations.

        Values should lie between the minimum of (-8, min element c) and
        the maximum of (all element c). Values outside this range by more
        than 1% indicate numerical problems — typically exp(beta*x)
        overflow in far-field regions or solver divergence.

        The -8 floor corresponds to a reasonable background acceptor
        concentration; adjust if your configs use different values.
        """
        if len(self.config.elements) == 0:
            return
        element_concs = [elem.c for elem in self.config.elements]
        min_expected = min(-8.0, min(element_concs))
        max_expected = max(element_concs)
        tolerance = 0.01 * max(abs(min_expected), abs(max_expected))
        outside = np.sum((self.result > max_expected + tolerance) |
                         (self.result < min_expected - tolerance))
        pct = outside / self.result.size * 100
        if pct > 1.0:
            print(f"WARNING: {outside} points ({pct:.2f}%) outside expected range "
                  f"[{min_expected:.3f}, {max_expected:.3f}] mg/l")
            print(f"Actual range: [{np.min(self.result):.3f}, {np.max(self.result):.3f}] mg/l")
        else:
            print(f"All concentration values within expected range "
                  f"[{min_expected:.3f}, {max_expected:.3f}] mg/l")

    def validate_solution(self):
        """
        Determine whether the simulation produced a physically meaningful result.

        The criterion operates only on the already-computed concentration array
        and is deliberately coarse and grid-independent:

          PASS if both:
            (a) result_max > ca  — donor concentration exists above background.
                When the solve fails, the field collapses and result_max < ca
                even with strong sources present.
            (b) result_min < -ca * 0.5  — acceptor depletion is present,
                confirming the reaction stoichiometry is active.

        For composite element clusters, individual boundary checks do not seem to
        be reliable because the field at any element boundary reflects
        contributions from all neighbours by design. This grid-level check
        is the appropriate surrogate.

        Sets self.validation_passed (bool) and self.validation_reason (str),
        and prints a parseable line starting with VALIDATION PASS / FAIL
        for capture by run_tests.py.
        """
        ca = self.config.ca
        result_max = float(np.max(self.result))
        result_min = float(np.min(self.result))

        reasons = []
        if result_max <= ca:
            reasons.append(
                f"result_max={result_max:.3f} <= ca={ca:.3f}: "
                f"no donor above background"
            )
        if result_min >= -ca * 0.5:
            reasons.append(
                f"result_min={result_min:.3f} >= -{ca*0.5:.3f}: "
                f"no acceptor depletion"
            )

        self.validation_passed = len(reasons) == 0
        if self.validation_passed:
            self.validation_reason = (
                f"result_max={result_max:.3f} > ca={ca:.3f}, "
                f"result_min={result_min:.3f} < -{ca*0.5:.3f}"
            )
            print(f"VALIDATION PASS  ({self.validation_reason})")
        else:
            self.validation_reason = "; ".join(reasons)
            print(f"VALIDATION FAIL  ({self.validation_reason})")

    # Statistics

    def _build_interpolator(self):
        """
        Build a RegularGridInterpolator over the stored concentration field.

        Used by print_statistics to look up concentration values at
        arbitrary (x, y) points without recomputing the full Mathieu
        expansion. Linear interpolation is used; points outside the grid
        return NaN.
        """
        from scipy.interpolate import RegularGridInterpolator
        return RegularGridInterpolator(
            (self.yaxis, self.xaxis), self.result,
            method='linear', bounds_error=False, fill_value=np.nan
        )

    def print_statistics(self, cpu_time):
        """
        Compute and save per-element boundary concentration statistics,
        then produce an error plot.

        Samples exactly 4 points on each source element's boundary using
        calc_c (the full Mathieu expansion — exact, not grid-interpolated).
        Image auxiliary elements are skipped; their boundary concentrations
        differ from their stored c values by design.

        The 4 sample positions are:
          Circle / Ellipse: cardinal angles 0, π/2, π, 3π/2
          Line: fractions -3/4, -1/4, +1/4, +3/4 of the half-length
        """
        from math import cos, sin, pi

        stats = {}
        all_elem_errors = {}

        print("\n=== ELEMENT BOUNDARY STATISTICS ===")
        for idx, elem in enumerate(self.config.elements):
            eid = elem.id.lower() if elem.id else ""
            if eid.startswith("image_"):
                print(f'Element {idx + 1}: ({eid}) — skipped (auxiliary element)')
                continue

            if elem.kind == ATElementType.Circle:
                phi = np.array([0.0, pi/2, pi, 3*pi/2])
                x_test = elem.x + (elem.r + 1e-2) * np.cos(phi)
                y_test = elem.y + (elem.r + 1e-2) * np.sin(phi)

            elif elem.kind == ATElementType.Ellipse:
                phi = np.array([0.0, pi/2, pi, 3*pi/2])
                a = float(elem.r)
                b = float(elem.b if elem.b is not None else elem.r)
                ct, st = math.cos(elem.theta), math.sin(elem.theta)
                x_test = elem.x + a * np.cos(phi) * ct - b * np.sin(phi) * st
                y_test = elem.y + a * np.cos(phi) * st + b * np.sin(phi) * ct

            elif elem.kind == ATElementType.Line:
                half_len = elem.r
                fracs = np.array([-0.75, -0.25, 0.25, 0.75])
                s = fracs * half_len
                phi = (fracs + 1.0) * pi  # map to [0, 2π] for plotting
                x_test = elem.x + s * cos(elem.theta)
                y_test = elem.y + s * sin(elem.theta)

            else:
                raise ValueError(f"Unknown element type: {elem.kind}")

            # Exact evaluation
            Err = [self.calc_c(x, y) for x, y in zip(x_test, y_test)]
            min_val = round(float(np.min(Err)), 9)
            max_val = round(float(np.max(Err)), 9)
            mean_val = round(float(np.mean(Err)), 9)
            std_val = round(float(np.std(Err)), 9)

            print(f'Element {idx + 1}:')
            print(f'  Min = {min_val} mg/l')
            print(f'  Max = {max_val} mg/l')
            print(f'  Mean = {mean_val} mg/l')
            print(f'  Standard Deviation = {std_val} mg/l')

            stats[f"Min{idx + 1}"] = min_val
            stats[f"Max{idx + 1}"] = max_val
            stats[f"Mean{idx + 1}"] = mean_val
            stats[f"Std{idx + 1}"] = std_val

            all_elem_errors[idx] = (phi, [abs(e) for e in Err])

        # Save statistics file
        # Writes a human-readable summary containing the config parameters,
        # element geometry, computation time, L_max and interface length,
        # and the per-element boundary statistics computed above.
        stats_filename = os.path.join(self.run_dir, "stats.txt")

        with open(stats_filename, "w") as f:
            f.write("=== CONFIGURATION PARAMETERS ===\n")
            f.write(f"Number of elements: {self.num_elements_original}\n")
            f.write(f"Number of terms: {self.config.num_terms}\n")
            f.write(f"Domain increment: {self.config.dom_inc}\n")
            f.write(f"Alpha_t: {self.config.alpha_t}\n")
            f.write(f"Alpha_l: {self.config.alpha_l}\n")
            f.write(f"Beta: {self.config.beta}\n")
            f.write(f"Gamma: {self.config.gamma}\n")
            f.write(f"Ca: {self.config.ca}\n")
            f.write(f"Number of control points: {self.config.num_cp}\n")
            f.write(f"Orientation: {self.config.orientation}\n")
            f.write(f"Domain: x[{self.config.dom_xmin}, {self.config.dom_xmax}], "
                    f"y[{self.config.dom_ymin}, {self.config.dom_ymax}]\n")
            f.write(f"Dynamic domain extension: "
                    f"{'on' if getattr(self.config, 'dynamic_domain', True) else 'off'}\n")

            # How the coupled/decoupled decision was made for this run.
            info = getattr(self, "solve_info", None)
            if info:
                f.write("\n=== SOLVER ===\n")
                cond = info.get("cond")
                f.write(f"Decision: {info.get('decision')}\n")
                if cond is not None:
                    f.write(f"Condition number: {cond:.6e}\n")
                else:
                    f.write("Condition number: n/a (not computed for the decoupled solve)\n")
                f.write(f"Decoupling allowed: {info.get('decoupling_allowed')}\n")
                if info.get("n_coupling_groups") is not None:
                    f.write(f"Coupling groups found: {info.get('n_coupling_groups')}\n")
                if info.get("groups"):
                    f.write(f"Decoupled groups: {info.get('groups')}\n")
                if info.get("iterations") is not None:
                    f.write(f"Iterations: {info.get('iterations')} "
                            f"(max log-coefficient change "
                            f"{info.get('max_log_delta'):.2e}, "
                            f"{'converged' if info.get('converged') else 'hit iteration cap'})\n")
                f.write("Criterion: decouple when allow_decoupling is true and the "
                        "Ke coupling graph (|Ke| > 1e-300 between element centres) "
                        "splits into more than one group; the condition number is "
                        "not used. Decoupled groups still interact through "
                        "log-space cross-group corrections.\n")
                f.write(f"Reason: {info.get('reason')}\n")

            if self.probe_results:
                f.write("\n=== CONCENTRATION PROBES ===\n")
                f.write("(positive = donor regime, negative = acceptor regime)\n")
                for px, py, pc in self.probe_results:
                    f.write(f"c({px:g}, {py:g}) = {pc:.6g} mg/l\n")

            f.write("\n=== ELEMENTS ===\n")
            for eidx, elem in enumerate(self.config.elements):
                if elem.kind == ATElementType.Circle:
                    f.write(f"Element {eidx+1}: kind={elem.kind}, x={elem.x}, y={elem.y}, "
                            f"r={elem.r}, c={elem.c}, id={elem.id}\n")
                elif elem.kind == ATElementType.Ellipse:
                    f.write(f"Element {eidx+1}: kind={elem.kind}, x={elem.x}, y={elem.y}, "
                            f"a={elem.r}, b={elem.b}, theta={elem.theta}, c={elem.c}, id={elem.id}\n")
                else:
                    f.write(f"Element {eidx+1}: kind={elem.kind}, x={elem.x}, y={elem.y}, "
                            f"r={elem.r}, theta={elem.theta}, c={elem.c}, id={elem.id}\n")

            f.write("\n=== COMPUTATION INFO ===\n")
            f.write(f"CPU Time [hh:mm:ss]: {cpu_time}\n")
            if self.L_max is not None:
                f.write(f"\nL_max: {self.L_max}\n")
            if getattr(self, "interface_length", None) is not None:
                f.write(f"InterfaceLength: {self.interface_length:.6f} m\n")
            if getattr(self, "z_min_reached", None) is not None:
                domain_height = self.config.dom_ymax - self.config.dom_ymin
                capped = ((self.z_min_reached - self.config.dom_ymin)
                          <= 0.05 * domain_height)
                f.write(f"z_min_reached: {self.z_min_reached:.3f} m\n")
                f.write(f"VerticallyCapped: {'yes' if capped else 'no'}\n")

            f.write("\n=== ELEMENT BOUNDARY STATISTICS (4-point exact) ===\n")
            for k, v in stats.items():
                f.write(f"{k} = {v} mg/l\n")

        print(f"Statistics saved to: {stats_filename}")

        # Error plot — one marker per sample point per source element.
        # Uses the arrays stored above; no new calc_c calls needed.
        mpl.rcParams.update({'font.size': 22})
        plt.figure(figsize=(16, 9), dpi=150)

        styles = ['-o', '--s', ':^', '-.D']
        for idx, (phi_plot, abs_err) in all_elem_errors.items():
            plt.plot(phi_plot, abs_err,
                     styles[idx % len(styles)],
                     linewidth=2, markersize=8, label=f'Element {idx + 1}')

        plt.xlim([0, 2 * math.pi])
        plt.xlabel('Boundary position')
        plt.ylabel('Absolute error [mg/l]')
        # Use math-mode \circ rather than a literal '°': the 'science' style
        # enables text.usetex, and LaTeX rejects raw non-ASCII glyphs.
        plt.xticks(np.linspace(0, 2 * math.pi, 5),
                   [r'$0^\circ$', r'$90^\circ$', r'$180^\circ$',
                    r'$270^\circ$', r'$360^\circ$'])
        plt.legend(loc='best')
        plt.tight_layout()

        error_filename = os.path.join(self.run_dir, "error.pdf")
        plt.savefig(error_filename)
        print(f"Error plot saved to: {error_filename}")
        self._show_or_close()

    def _show_or_close(self):
        """
        Display the current figure inline when configured to, then close it.

        Writing the PDF is always done by the caller beforehand; this only
        controls whether the figure is *also* drawn into the IDE window.
        Showing requires an interactive matplotlib backend (see the backend
        note at the top of this module). main.py selects one automatically
        from "show_plots", so reaching the warning below means either another
        entry point imported this module, or auto-detection found no usable
        display — on Agg, plt.show() is a silent no-op, so warn rather than
        fail quietly.
        """
        if not getattr(self.config, "show_plots", False):
            plt.close()
            return

        if not INTERACTIVE_BACKEND:
            print(f"WARNING: show_plots is enabled but matplotlib resolved to "
                  f"the non-interactive '{matplotlib.get_backend()}' backend, "
                  f"so nothing can be displayed. Run through main.py, or set "
                  f"AEM_INTERACTIVE=1 before importing at_simulation. On Linux "
                  f"this can also mean no display or no tkinter is available. "
                  f"The PDF was still written.")
            plt.close()
            return

        plt.show()
        plt.close()

    # Input plot

    def plot_input(self):
        """
        Generate a two-panel visualization of the source-zone configuration.

        Left panel  — source zone rendered at true scale with equal aspect
                      ratio. Shows the real element shapes (circles,
                      ellipses, lines) colored by their prescribed
                      concentration. The source-zone extent Ws (rightmost
                      element edge) is marked with gold dashed lines.
        Right panel — the full simulation domain with the source zone
                      highlighted as a shaded band. Provides geometric
                      context for interpreting the result plot.

        Image auxiliary elements are excluded; only the user-defined source
        elements are drawn. Donor elements use the
        Reds colormap, acceptors use Blues_r. Dual colorbars at the bottom
        span the full donor and acceptor concentration ranges found in
        the config.

        Saves to sim_runs/<run_index>_<label>/input.pdf.
        """
        import matplotlib.patches as mpatches
        from matplotlib.gridspec import GridSpec

        elements = [e for e in self.config.elements
                    if not e.id.lower().startswith("image_")
                    and not e.id.lower().startswith("zero_")]
        if not elements:
            return

        concs = [e.c for e in elements]
        max_conc = max(concs)
        min_conc = min(concs)
        has_donor = max_conc > 0
        has_acceptor = min_conc < 0
        ca = self.config.ca

        donor_cmap = plt.cm.Reds
        acceptor_cmap = plt.cm.Blues_r
        donor_norm = mpl.colors.Normalize(vmin=0, vmax=max_conc if has_donor else 1)
        acc_norm = mpl.colors.Normalize(vmin=min_conc if has_acceptor else -ca, vmax=0)
        bg_color = acceptor_cmap(1.0)

        dom_xmin, dom_xmax = self.config.dom_xmin, self.config.dom_xmax
        dom_ymin, dom_ymax = self.config.dom_ymin, self.config.dom_ymax
        orientation = self.config.orientation

        all_x = [e.x for e in elements]
        all_r = [e.r for e in elements]
        ws = max(x + r for x, r in zip(all_x, all_r))
        src_xmin = -0.05 * max(ws, 1e-3)
        src_xmax = 1.15 * max(ws, 1e-3)

        def draw_elements_on(ax, lw=0.8):
            for e in elements:
                c_val = e.c
                color = (donor_cmap(donor_norm(c_val)) if c_val >= 0 and has_donor
                         else acceptor_cmap(acc_norm(c_val)) if c_val < 0 and has_acceptor
                         else donor_cmap(0.5) if c_val >= 0 else acceptor_cmap(0.5))

                if e.kind == ATElementType.Circle:
                    ax.add_patch(mpatches.Circle(
                        (e.x, e.y), e.r,
                        facecolor=color, edgecolor="black", linewidth=lw, zorder=3))
                elif e.kind == ATElementType.Ellipse:
                    ax.add_patch(mpatches.Ellipse(
                        (e.x, e.y), width=2*e.r,
                        height=2*(e.b if e.b is not None else e.r),
                        angle=math.degrees(e.theta),
                        facecolor=color, edgecolor="black", linewidth=lw, zorder=3))
                elif e.kind == ATElementType.Line:
                    hl = e.r
                    x1 = e.x - hl * math.cos(e.theta)
                    y1 = e.y - hl * math.sin(e.theta)
                    x2 = e.x + hl * math.cos(e.theta)
                    y2 = e.y + hl * math.sin(e.theta)
                    ax.plot([x1, x2], [y1, y2], color="black",
                            linewidth=lw*5, solid_capstyle="round", zorder=2)
                    ax.plot([x1, x2], [y1, y2], color=color,
                            linewidth=lw*4, solid_capstyle="round", zorder=3)

        mpl.rcParams.update({"font.size": 16})
        fig = plt.figure(figsize=(20, 10), dpi=150)  # dpi 150 for speed
        gs = GridSpec(1, 2, figure=fig, width_ratios=[1, 3], wspace=0.08)
        ax_src = fig.add_subplot(gs[0])
        ax_dom = fig.add_subplot(gs[1])

        ax_src.set_facecolor(bg_color)
        draw_elements_on(ax_src, lw=0.8)
        ax_src.set_xlim(src_xmin, src_xmax)
        ax_src.set_ylim(dom_ymin, dom_ymax)
        ax_src.set_aspect("equal")
        ax_src.xaxis.set_major_locator(MaxNLocator(nbins=3))
        ax_src.yaxis.set_major_locator(MaxNLocator(nbins=8))
        ax_src.set_xlabel("$x$ (m)", fontsize=15)
        ylabel = "$z$ (m)" if orientation == "vertical" else "$y$ (m)"
        ax_src.set_ylabel(ylabel, fontsize=15)
        ax_src.set_title("Source zone", fontsize=14, pad=4)
        ax_src.axvline(x=0.0, color="gold", linewidth=1.2, linestyle="--", zorder=4)
        ax_src.axvline(x=ws, color="gold", linewidth=1.2, linestyle="--", zorder=4)
        ax_src.text(0.98, 0.99, f"Ws = {ws:.3f} m",
                    transform=ax_src.transAxes, ha="right", va="top", fontsize=10,
                    color="goldenrod",
                    bbox=dict(facecolor="white", alpha=0.4, boxstyle="round,pad=0.2"))

        ax_dom.set_facecolor(bg_color)
        ax_dom.axvspan(0.0, ws, color="gold", alpha=0.18, zorder=1,
                       label=f"Source zone ($x \\leq {ws:.3f}$ m)")
        draw_elements_on(ax_dom, lw=0.5)
        ax_dom.set_xlim(dom_xmin, dom_xmax)
        ax_dom.set_ylim(dom_ymin, dom_ymax)
        ax_dom.xaxis.set_major_locator(MaxNLocator(nbins=7))
        ax_dom.yaxis.set_major_locator(MaxNLocator(nbins=8))
        ax_dom.set_xlabel("$x$ (m)", fontsize=15)
        ax_dom.set_yticklabels([])
        ax_dom.set_title("Full simulation domain", fontsize=14, pad=4)
        ax_dom.legend(loc="upper right", fontsize=11, framealpha=0.6)

        fig.subplots_adjust(bottom=0.18)

        def align_cbar_label(cb):
            """
            Left-align a colorbar's label, matching the alignment fix applied
            in plot_result.

            plot_result pins the label in *figure* coordinates using offsets
            hand-tuned to that figure. Those constants do not transfer here:
            this figure is two-panel, has a different size, and is saved with
            bbox_inches="tight", which re-crops at save time — pinning in
            figure coordinates puts the labels on top of the wrong colorbar.

            Instead only the x is overridden, in the label's own axes
            coordinates, leaving y at whatever matplotlib computed. Both
            colorbars span [ax_src, ax_dom] and therefore share an x range,
            so x=0 aligns the two labels flush-left with each other and with
            the left edge of the bars, whatever the surrounding layout does.
            """
            label = cb.ax.xaxis.label
            label.set_horizontalalignment("left")
            label.set_position((0.0, label.get_position()[1]))

        if has_donor:
            donor_levels = np.linspace(0, max_conc, 11)
            sm_d = plt.cm.ScalarMappable(cmap="Reds",
                                          norm=mpl.colors.Normalize(0, max_conc))
            sm_d.set_array([])
            cb_d = fig.colorbar(sm_d, ax=[ax_src, ax_dom], ticks=donor_levels,
                                label="Electron donor concentration [mg/l]",
                                location="bottom", pad=0.02, aspect=60)
            cb_d.ax.tick_params(labelsize=11)
            align_cbar_label(cb_d)

        abs_min = abs(min_conc) if has_acceptor else ca
        acc_levels = np.linspace(-abs_min, 0, 9)
        sm_a = plt.cm.ScalarMappable(cmap="Blues_r",
                                      norm=mpl.colors.Normalize(-abs_min, 0))
        sm_a.set_array([])
        cb_a = fig.colorbar(sm_a, ax=[ax_src, ax_dom], ticks=acc_levels,
                            label="Electron acceptor concentration [mg/l]",
                            location="bottom",
                            pad=0.10 if has_donor else 0.02, aspect=60)
        cb_a.set_ticklabels([f"{abs(t):.0f}" for t in acc_levels])
        cb_a.ax.tick_params(labelsize=11)
        align_cbar_label(cb_a)

        input_filename = os.path.join(self.run_dir, "input.pdf")
        plt.savefig(input_filename, bbox_inches="tight")
        self._show_or_close()
        print(f"Input plot saved to: {input_filename}")

    # Result plot

    def plot_result(self):
        """
        Generate the main concentration field plot and save it as PDF.

        Renders the full domain with:
          - Red filled contours (contourf) for donor concentrations (C > 0)
          - Blue filled contours for acceptor concentrations (C < 0)
          - A black line marking the zero-concentration contour (plume
            envelope), whose total length is reported as "interface length"
          - Dual colorbars at the bottom for quantitative reading

        For large grids (>10k points), the filled contours are rasterized
        in the PDF to keep file size manageable — the contourf polygons
        would otherwise produce very large vector PDFs. The zero-contour
        line is always rendered as a vector for crispness at any zoom.

        The aspect ratio follows config.plot_aspect: "scaled" uses equal
        x/y units (useful when the domain is roughly square); anything else
        uses automatic scaling (useful for long thin plume domains).

        Saves to sim_runs/<run_index>_<label>/plot.pdf.
        """
        max_val = float(np.max(self.result))
        min_val = float(np.min(self.result))
        abs_min = abs(min_val)
        xmin, xmax = self.config.dom_xmin, self.config.dom_xmax
        ymin, ymax = self.config.dom_ymin, self.config.dom_ymax

        # The field is not guaranteed to straddle zero. A weak source against a
        # high background gives an entirely acceptor field (max_val <= 0); a
        # very strong one gives an entirely donor field (min_val >= 0). In
        # either case np.linspace returns non-increasing levels and contourf
        # raises "Contour levels must be increasing" — which would throw away
        # the run after the solve has already been paid for. Draw only the
        # side that actually has data.
        has_donor = max_val > 0.0
        has_acceptor = min_val < 0.0

        donor_levels = np.linspace(0, max_val, 11) if has_donor else None
        acceptor_levels = np.linspace(-abs_min, 0, 9) if has_acceptor else None

        # Use 500 dpi for publication-quality result plots; lower for speed.
        plot_dpi = 500

        mpl.rcParams.update({"font.size": 22})
        fig, ax = plt.subplots(figsize=(10, 8), dpi=plot_dpi)

        # Rasterize the filled contour collections on large grids to keep
        # the PDF compact. The zero-contour line stays vector (zorder=6).
        n_grid_pts = self.result.size
        rasterize = n_grid_pts > 10_000
        if rasterize:
            ax.set_rasterization_zorder(5)

        X, Y = np.meshgrid(self.xaxis, self.yaxis)

        donor = None
        if has_donor:
            donor = ax.contourf(
                X, Y, self.result,
                levels=donor_levels, cmap='Reds', extend='max',
                zorder=1 if rasterize else None
            )
        acceptor = None
        if has_acceptor:
            acceptor = ax.contourf(
                X, Y, self.result,
                levels=acceptor_levels, cmap='Blues_r', extend='min',
                zorder=2 if rasterize else None
            )
        if not has_donor or not has_acceptor:
            side = "acceptor" if not has_donor else "donor"
            print(f"NOTE: the concentration field is entirely {side} "
                  f"(range [{min_val:.3f}, {max_val:.3f}] mg/l); plotting that "
                  f"side only.")
        Plume_max = ax.contour(
            X, Y, self.result,
            levels=[0], linewidths=2, colors='k',
            zorder=6 if rasterize else None
        )

        total_length = 0
        for path in Plume_max.get_paths():
            v = path.vertices
            segment_lengths = np.sqrt(np.diff(v[:, 0])**2 + np.diff(v[:, 1])**2)
            total_length += np.sum(segment_lengths)
        print(f"Total interface length: {total_length:.4f}")

        ax.xaxis.set_major_locator(MaxNLocator(nbins=7))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5))

        # Vertical runs are bounded above by the water table at z=0, so the
        # plot must end there and must show the 0 tick. Without this the view
        # follows the data instead, and the data rarely reaches 0: conc_array
        # builds the axis as arange(ymin, ymax+inc, inc), so unless dom_ymin
        # happens to be a whole multiple of dom_inc below 0, the top row lands
        # short (e.g. ymin=-16.875, inc=0.5 -> top row -0.375). The locator
        # still emits a 0 tick, but matplotlib hides it as out-of-view, which
        # is why the topmost label read -4. Pinning the limit also guarantees
        # nothing above the water table is ever drawn.
        if self.config.orientation == "vertical":
            ax.set_ylim(ymin, 0.0)

        ax.set_xlabel("$x$ (m)")
        ax.set_ylabel("$z$ (m)" if self.config.orientation == "vertical" else "$y$ (m)")

        plt.subplots_adjust(bottom=0.20)

        # Colorbar label alignment (AK's fix from main). Matplotlib centres the
        # colorbar label by default, so the donor and acceptor labels — which
        # differ in length — end up visually offset from one another. Pin both
        # to a common left-hand x in figure coordinates instead, so they stack
        # flush-left under the plot.
        x0 = 2.5 * ax.get_position().x0

        if has_donor:
            cbar_donor = fig.colorbar(
                donor, ticks=donor_levels,
                label='Electron donor concentration [mg/l]',
                location='bottom', pad=0.005, aspect=75)
            cbar_donor.ax.tick_params(labelsize=14)
            cbar_donor.ax.xaxis.label.set_horizontalalignment("left")
            cbar_donor.ax.xaxis.set_label_coords(
                x0, cbar_donor.ax.get_position().y0 - 0.025,
                transform=fig.transFigure)

        if has_acceptor:
            cbar_acceptor = fig.colorbar(
                acceptor, ticks=acceptor_levels,
                label='Electron acceptor concentration [mg/l]',
                location='bottom',
                pad=0.12 if has_donor else 0.005, aspect=75)
            cbar_acceptor.set_ticklabels([f"{abs(t):.0f}" for t in acceptor_levels])
            cbar_acceptor.ax.tick_params(labelsize=14)
            cbar_acceptor.ax.xaxis.label.set_horizontalalignment("left")
            cbar_acceptor.ax.xaxis.set_label_coords(
                x0, cbar_acceptor.ax.get_position().y0 - 0.018,
                transform=fig.transFigure)

        if self.config.plot_aspect == "scaled":
            plt.axis("scaled")

        plt.tight_layout()

        plot_filename = os.path.join(self.run_dir, "plot.pdf")
        plt.savefig(plot_filename, dpi=plot_dpi)
        print(f"Plot saved to: {plot_filename}")
        self._show_or_close()