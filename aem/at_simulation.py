# Written by Willi Kappler, willi.kappler@uni-tuebingen.de
# Based on code from Anton Köhler
"""
AEM Transport Simulation — main simulation class and supporting functions.

This module implements the Analytic Element Method (AEM) transport model for
simulating steady-state contaminant plumes in groundwater. The core workflow is:

  1. Load a configuration of source elements (circles, lines, ellipses)
  2. For vertical orientation, add mirror images and zero-isoline elements
     to enforce the water-table boundary condition
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
matplotlib.use('Agg')  # non-interactive backend — required for headless test runs
import matplotlib.pyplot as plt
import matplotlib.pyplot as plt_temp
import matplotlib as mpl
from matplotlib.ticker import MaxNLocator
from matplotlib.lines import Line2D
from multiprocessing import Pool, cpu_count
import multiprocessing

# Local imports:
from .at_config import ATConfiguration
from .at_element import ATElement, ATElementType

logger = logging.getLogger(__name__)

# Shared state for multiprocessing workers
# These module-level globals are populated in each worker process via
# _init_pool(). They allow _compute_point_shared() to access simulation
# state without pickling it on every task — which would be prohibitively
# expensive for 50k+ grid points.
_shared_elements = None
_shared_coeff = None
_shared_num_terms = None
_shared_alpha_l = None
_shared_alpha_t = None
_shared_beta = None
_shared_ca = None
_shared_gamma = None

def _init_pool(elements, coeff, num_terms, alpha_l, alpha_t, beta, ca, gamma):
    """
    Pool initializer that copies simulation state into each worker process.

    Called once per worker at pool startup (not once per task). The state
    then stays resident in the worker for the lifetime of the pool, so
    individual task dispatches only need to pass the (x, y) coordinates.
    """
    global _shared_elements, _shared_coeff, _shared_num_terms
    global _shared_alpha_l, _shared_alpha_t, _shared_beta, _shared_ca, _shared_gamma
    _shared_elements = elements
    _shared_coeff = coeff
    _shared_num_terms = num_terms
    _shared_alpha_l = alpha_l
    _shared_alpha_t = alpha_t
    _shared_beta = beta
    _shared_ca = ca
    _shared_gamma = gamma


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
        _shared_beta, _shared_ca, _shared_gamma
    ))


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
    x, y, elements, coeff, num_terms, alpha_l, alpha_t, beta, ca, gamma = args
    total_terms = 2 * num_terms - 1

    # Precompute order arrays once — reused across all elements
    orders_all = np.arange(num_terms)
    orders_odd = np.arange(1, num_terms) if num_terms > 1 else np.array([], dtype=int)

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

    total = F * math.exp(beta * x)
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

    Used in vertical orientation to enforce the no-flux boundary condition at
    the surface. The image has y → -y, c → -c, and theta → -theta (for lines
    and ellipses). For circles, theta is set to pi/2 as a canonical value.
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


def create_zero_isoline(elem: ATElement) -> ATElement:
    """
    Return a horizontal line element on y=0 that enforces C=0 along the
    surface above the source.

    Used in vertical orientation in combination with the mirrored image
    elements. The image pair handles the no-flux condition; the zero-isoline
    pins the concentration to zero on the surface directly above the source,
    preventing the solution from drifting along the water table.

    The isoline shares the source's x-position and half-length (r) so it
    covers the same horizontal extent.
    """
    return ATElement(kind=ATElementType.Line, x=elem.x, y=0.0,
                     c=0.0, r=elem.r, theta=0.0)


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
        self.validation_passed = None
        self.validation_reason = ""
        self.timer = _PhaseTimer()

    def run(self):
        """
        Execute the full simulation pipeline end-to-end.

        Pipeline stages:
          1. Element setup — for vertical orientation, adds mirror images
             and a zero-isoline element for water-table boundary conditions.
             Computes each element's Mathieu parameter q and outline points.
          2. solve_system — least-squares fit of expansion coefficients to
             match prescribed concentrations on all element boundaries.
          3. conc_array — parallel evaluation of the concentration field on
             the domain grid.
          4. Dynamic domain extension — if the plume reaches the x-boundary,
             extends dom_xmax and recomputes. Repeats up to MAX_EXTENSIONS
             times. Avoids wasting a full fine-grid pass on an undersized
             domain.
          5. Post-processing — L_max calculation, domain and concentration
             range checks.
          6. Output — input plot, statistics file, error plot, result plot,
             all saved under Results/<run_index>/.
        """
        if len(self.config.elements) < 1:
            raise ValueError("Simulation requires at least one element.")

        self.num_elements_original = len(self.config.elements)
        self.timer.start("element_setup")
        if self.config.orientation == "vertical":
            # Build the full element list: each source gets a mirror image,
            # and a single shared zero-isoline is added at the end.
            updated_elements = []
            for elem in self.config.elements:
                if elem.y > -(elem.r*np.sin(elem.theta)+0.1):
                    raise ValueError(f"Element '{elem.id}' must have y < -(r+0.1) for vertical orientation.")
                updated_elements.append(elem)
                mirrored = create_mirrored_element(elem)
                mirrored.id = f"image_{elem.id}"
                zero_isoline = create_zero_isoline(elem)
                zero_isoline.id = f"zero_{elem.id}"
                updated_elements.append(mirrored)
            updated_elements.append(zero_isoline)
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
            elem.calc_d_q(alpha_t, alpha_l, beta)
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
        # MAX_EXTENSIONS is reached. Each extension adds 50% beyond the
        # current L_max and triggers a fresh grid computation.
        MAX_EXTENSIONS = 3
        self.timer.start("calculate_lmax")
        self.calculate_lmax()

        for ext_round in range(MAX_EXTENSIONS):
            if self.L_max is None:
                break
            domain_width = self.config.dom_xmax - self.config.dom_xmin
            max_x_dist = self.L_max - self.config.dom_xmin
            if max_x_dist < 0.90 * domain_width:
                break  # plume fits

            new_xmax = self.L_max + 0.5 * max(self.L_max, domain_width)
            print(f"Dynamic domain extension #{ext_round+1}: "
                  f"dom_xmax {self.config.dom_xmax:.0f} -> {new_xmax:.0f} m  "
                  f"(L_max={self.L_max})")
            self.config.dom_xmax = new_xmax
            self.timer.stop()

            self.timer.start(f"conc_array_ext{ext_round+1}")
            self.conc_array(self.config.dom_xmin, self.config.dom_ymin,
                            self.config.dom_xmax, self.config.dom_ymax,
                            self.config.dom_inc)
            self.timer.stop()

            self.timer.start("calculate_lmax")
            self.calculate_lmax()

        self.check_domain_adequacy()
        self.check_concentration_range()
        self.validate_solution()
        self.timer.stop()

        results_dir = os.path.join("Results")
        os.makedirs(results_dir, exist_ok=True)
        self.run_index = self.get_next_run_index(results_dir)
        self.run_dir = os.path.join(results_dir, f"{self.run_index:04d}")
        os.makedirs(self.run_dir, exist_ok=True)

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
                              log10_floor=-14.0):
        """
        Test whether two elements are close enough that cross-terms between
        them are numerically significant.

        Computes |Ke| in both directions (e_i's basis evaluated at e_j's
        center, and vice versa) and returns True if either magnitude exceeds
        10^log10_floor. The q-dependent criterion matters because Ke's
        decay rate is sqrt(q)-dependent: for small q, Ke stays significant
        out to larger eta than for large q.
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
        Partition elements into connected components of "coupled" elements
        using a union-find algorithm.

        Two elements are coupled if _are_elements_coupled returns True.
        Elements within the same group must be solved together; elements
        in different groups can be solved independently. Returns a list
        of groups, each a list of element indices.
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
        groups = {}
        for i in range(ne):
            groups.setdefault(find(i), []).append(i)
        return list(groups.values())

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
                            alpha_l, alpha_t, beta, ca, gamma, n,
                            cross_term_floor=1e-250):
        """
        Assemble the least-squares matrix A and RHS vector b for a group
        of elements.

        For each element pair (i, j) in the group, evaluates element j's
        Mathieu basis functions at all of element i's control points in a
        single batched call.

        Cross-element blocks whose entries are all below cross_term_floor
        are zeroed out — these are contributions from distant elements that
        are numerically negligible and would only introduce noise.

        Self-element blocks along the diagonal use eta=0 for line elements.
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

        row_offset = 0
        for i_local, e_i in enumerate(group_elements):
            ncp_i = num_cp_per[i_local]
            outline_x = np.array([p[0] for p in e_i.outline])
            outline_y = np.array([p[1] for p in e_i.outline])

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

                # Self-diagonal line elements: evaluate on eta=0
                if e_j.kind == ATElementType.Line and i_local == j_local:
                    etas[:] = 0.0

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

                # Zero out negligible cross-element blocks
                if i_local != j_local:
                    block_slice = A[row_offset:row_offset+ncp_i,
                                    col_start:col_start+total_terms]
                    if np.max(np.abs(block_slice)) < cross_term_floor:
                        block_slice[:] = 0.0

            row_offset += ncp_i

        return A, b

    def _solve_scaled_lstsq(self, A, b, rcond=1e-10):
        """
        Solve A @ x = b in the least-squares sense with row and column scaling.

        Row scaling: each row divided by its max-abs value — prevents rows
        with very different magnitudes (near-source vs far-field control
        points) from dominating the least-squares residual.

        Column scaling: each column divided by its max-abs value — corrects
        for columns that are uniformly small (e.g. the zero-isoline columns
        evaluated at deep elements), which would otherwise inflate the
        condition number without reflecting genuine numerical instability.
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

    def _evaluate_group_field(self, group_indices, elements, coeff, n,
                              x, y, alpha_l, alpha_t):
        """
        Evaluate the F-field contribution from a specific subset of elements
        at a given (x, y) point.

        Used during decoupled iterative solving to compute the "known"
        cross-group contributions that must be subtracted from each group's
        RHS. Sums Mathieu basis functions only from elements in group_indices,
        not the full element list.
        """
        total_terms = 2 * n - 1
        orders_all = np.arange(n)
        orders_odd = np.arange(1, n) if n > 1 else np.array([], dtype=int)

        F = 0.0
        for idx in group_indices:
            elem = elements[idx]
            dx = x - elem.x
            dy = y - elem.y
            eta, psi = elem.uv(dx, dy, alpha_l, alpha_t)
            block = coeff[idx * total_terms: (idx + 1) * total_terms]

            ce_vals = elem.m.ce(orders_all, psi).real
            Ke_vals = elem.m.Ke(orders_all, eta).real
            Fi = block[0] * ce_vals[0] * Ke_vals[0]

            if n > 1:
                se_vals = elem.m.se(orders_odd, psi).real
                Ko_vals = elem.m.Ko(orders_odd, eta).real
                for j in range(1, n):
                    Fi += block[2*j-1] * se_vals[j-1] * Ko_vals[j-1]
                    Fi += block[2*j]   * ce_vals[j]   * Ke_vals[j]
            F += Fi
        return F

    # Solve strategies

    def _solve_coupled(self, elements, n, total_terms, alpha_l, alpha_t,
                       beta, ca, gamma):
        """
        Solve the full coupled system with all elements in one matrix.

        This is the simplest and typically most accurate approach when the
        matrix is well-conditioned. All element-element cross-terms are
        present, so there's no information loss. Used when the condition
        number of the assembled matrix is below the threshold in solve_system.
        """
        all_indices = list(range(len(elements)))
        A, b = self._build_group_system(
            all_indices, elements, alpha_l, alpha_t, beta, ca, gamma, n)
        coeffs, _ = self._solve_scaled_lstsq(A, b)
        coeff = np.zeros(len(elements) * total_terms)
        for li, gi in enumerate(all_indices):
            coeff[gi*total_terms:(gi+1)*total_terms] = \
                coeffs[li*total_terms:(li+1)*total_terms]
        return coeff

    def _solve_decoupled_iterative(self, elements, groups, n, total_terms,
                                   alpha_l, alpha_t, beta, ca, gamma):
        """
        Gauss-Seidel iteration over independent element groups.

        Each group is solved as a self-contained least-squares system, but
        the RHS is corrected by subtracting the known field contributions
        from all other groups. This accounts for cross-group coupling
        without assembling a single large matrix.

        The iteration converges when the coefficient vector changes by less
        than `tol` in relative L2 norm between successive rounds, or stops
        after `max_iter` rounds. Typically converges in 2-4 iterations when
        groups are well-separated.
        """
        num_elements = len(elements)
        group_data = []
        for group in groups:
            A, b_original = self._build_group_system(
                group, elements, alpha_l, alpha_t, beta, ca, gamma, n)
            control_points = []
            for g_idx in group:
                for (x_cp, y_cp) in elements[g_idx].outline:
                    control_points.append((x_cp, y_cp))
            group_data.append({
                'indices': group, 'A': A,
                'b_original': b_original, 'control_points': control_points,
            })

        coeff = np.zeros(num_elements * total_terms)
        max_iter = 8
        tol = 1e-6

        for iteration in range(max_iter):
            coeff_old = coeff.copy()
            for gi, gd in enumerate(group_data):
                group = gd['indices']
                b_corrected = gd['b_original'].copy()
                # Subtract contributions from every other group using the
                # current best estimate of their coefficients
                for gj, gd_other in enumerate(group_data):
                    if gi == gj:
                        continue
                    other_group = gd_other['indices']
                    for cp_idx, (x_cp, y_cp) in enumerate(gd['control_points']):
                        F_other = self._evaluate_group_field(
                            other_group, elements, coeff, n,
                            x_cp, y_cp, alpha_l, alpha_t)
                        b_corrected[cp_idx] -= F_other

                coeffs, _ = self._solve_scaled_lstsq(gd['A'], b_corrected)
                for local_idx, global_idx in enumerate(group):
                    start = global_idx * total_terms
                    local_start = local_idx * total_terms
                    coeff[start:start+total_terms] = coeffs[local_start:local_start+total_terms]

            delta = np.linalg.norm(coeff - coeff_old)
            norm = np.linalg.norm(coeff)
            rel_change = delta / norm if norm > 0 else delta
            logger.info(f"  Iteration {iteration+1}: rel_change={rel_change:.2e}")
            if rel_change < tol:
                print(f"Decoupled solve converged after {iteration+1} iterations "
                      f"(rel_change={rel_change:.2e})")
                return coeff

        print(f"Decoupled solve: {max_iter} iterations (rel_change={rel_change:.2e})")
        return coeff

    @staticmethod
    def _find_atomic_units(elements):
        """
        Classify elements into "atomic units" that cannot be split during
        decoupling, plus a list of "shared" elements that must be included
        in every solve group.

        In vertical orientation:
          - Each source element and its mirror image form an atomic unit
            (they must always be solved together because they enforce the
            no-flux water-table condition as a pair).
          - The zero-isoline element is shared across all groups because
            it enforces a condition that applies everywhere along y=0.

        In horizontal orientation, each element is its own atomic unit and
        there are no shared elements.

        Returns (units, shared) where units is a list of lists of indices
        and shared is a flat list of indices.
        """
        units = []
        shared = []
        i = 0
        while i < len(elements):
            eid = elements[i].id.lower() if elements[i].id else ""
            if eid.startswith("zero_"):
                shared.append(i)
                i += 1
            elif (not eid.startswith("image_")
                  and i + 1 < len(elements)
                  and (elements[i+1].id or "").lower().startswith("image_")):
                units.append([i, i+1])
                i += 2
            else:
                units.append([i])
                i += 1
        return units, shared

    def solve_system(self, alpha_l, alpha_t, beta, gamma, ca, n, M):
        """
        Top-level solver: try coupled, fall back to decoupled only when safe.

        Strategy:
          1. Assemble and solve the full coupled system with row+column scaling.
          2. Check the condition number. If below cond_threshold, done.
          3. If above threshold: check whether the Ke-based coupling graph
             yields multiple disconnected groups. If ALL elements are in one
             coupled group (log|Ke| >> -14 for every pair), the high condition
             number is due to matrix scale disparity — NOT exp-amplification
             instability — and the coupled result is still correct. Use it.
          4. Only if genuinely separable groups exist: split and run the
             decoupled iterative (Gauss-Seidel) solver.
          5. If splitting yields only one group despite the high cond, fall
             back to the coupled result.

        The resulting coefficient vector is stored in self.coeff.
        """
        elements = self.config.elements
        num_elements = len(elements)
        total_terms = 2 * n - 1
        cond_threshold = 1e14

        all_indices = list(range(num_elements))
        A, b = self._build_group_system(
            all_indices, elements, alpha_l, alpha_t, beta, ca, gamma, n)

        coeffs, residuals, rank, sv = np.linalg.lstsq(A, b, rcond=None)
        cond = np.inf
        if sv is not None and len(sv) > 0:
            cond = sv[0] / sv[-1] if sv[-1] > 0 else np.inf

        # Helper: store coupled result from the already-solved (A,b) system
        def _store_coupled():
            self.coeff = np.zeros(num_elements * total_terms)
            for li, gi in enumerate(all_indices):
                self.coeff[gi*total_terms:(gi+1)*total_terms] = \
                    coeffs[li*total_terms:(li+1)*total_terms]

        if cond < cond_threshold:
            _store_coupled()
            print(f"Coupled solve: OK (cond={cond:.1e})")
            return

        # High condition number detected. Before switching to decoupled,
        # check whether a Ke-based coupling graph actually separates into
        # multiple groups. If all elements are genuinely coupled (small q
        # → Ke decays slowly, so even distant elements interact), the high
        # cond is caused by column-scale disparity in the matrix (typically
        # the zero-isoline columns becoming tiny for deep elements) rather
        # than exp(beta*x) amplification instability. In that case the
        # coupled row-scaled lstsq result is correct and decoupling would
        # produce a wrong solution because the Gauss-Seidel iteration
        # cannot converge when groups are not genuinely independent.
        coupling_groups = self._find_coupling_groups(elements, alpha_l, alpha_t)
        all_one_group = len(coupling_groups) == 1

        if all_one_group:
            # All elements are mutually coupled — decoupling is not valid.
            # The high condition number is a scale-disparity artefact; the
            # coupled solve is still the correct answer.
            _store_coupled()
            print(f"Coupled solve: ill-conditioned (cond={cond:.1e}) "
                  f"but all elements coupled — keeping coupled result")
            return

        print(f"Coupled solve ill-conditioned (cond={cond:.1e}) "
              f"and {len(coupling_groups)} separable groups found "
              f"— switching to decoupled solve")

        units, shared = self._find_atomic_units(elements)
        groups = self._split_until_valid(
            all_indices, elements, units, shared, n, total_terms,
            alpha_l, alpha_t, beta, ca, gamma, cond_threshold)

        if len(groups) == 1:
            _store_coupled()
            print(f"Could not split further — using coupled result")
            return

        print(f"Split into {len(groups)} groups: "
              f"{[sorted(g) for g in groups]}")

        self.coeff = self._solve_decoupled_iterative(
            elements, groups, n, total_terms,
            alpha_l, alpha_t, beta, ca, gamma)

    def _split_until_valid(self, indices, elements, units, shared,
                           n, total_terms, alpha_l, alpha_t,
                           beta, ca, gamma, cond_threshold):
        """
        Recursively split a set of elements until each subgroup is
        well-conditioned.

        At each level: if the group's matrix is already well-conditioned,
        return it as a single group. Otherwise, find the largest spatial
        gap between atomic units (sorted by x, then y), split there, add
        the shared elements to each side, and recurse on both halves.

        Returns a flat list of groups (each a list of element indices)
        whose union covers all input indices.
        """
        index_set = set(indices)
        contained_units = [u for u in units if all(i in index_set for i in u)]

        if len(contained_units) <= 1:
            return [indices]

        A, b = self._build_group_system(
            indices, elements, alpha_l, alpha_t, beta, ca, gamma, n)
        coeffs, cond = self._solve_scaled_lstsq(A, b)

        if cond < cond_threshold:
            return [indices]

        sorted_units = sorted(contained_units,
                              key=lambda u: (elements[u[0]].x, elements[u[0]].y))

        max_gap = -1
        split_pos = 1
        for k in range(1, len(sorted_units)):
            prev_src = elements[sorted_units[k-1][0]]
            curr_src = elements[sorted_units[k][0]]
            gap = math.sqrt((curr_src.x - prev_src.x)**2 +
                            (curr_src.y - prev_src.y)**2)
            if gap > max_gap:
                max_gap = gap
                split_pos = k

        left_units = sorted_units[:split_pos]
        right_units = sorted_units[split_pos:]
        left = sorted(set([i for u in left_units for i in u] + shared))
        right = sorted(set([i for u in right_units for i in u] + shared))

        left_groups = self._split_until_valid(
            left, elements, units, shared, n, total_terms,
            alpha_l, alpha_t, beta, ca, gamma, cond_threshold)
        right_groups = self._split_until_valid(
            right, elements, units, shared, n, total_terms,
            alpha_l, alpha_t, beta, ca, gamma, cond_threshold)
        return left_groups + right_groups

    def _validate_group_boundary(self, group_indices, elements, coeff, n,
                                 alpha_l, alpha_t, beta, ca, gamma,
                                 max_rel_error=0.05):
        """
        Check whether a solved group's coefficients satisfy the boundary
        conditions on its own elements.

        Samples ~10 points along each element's outline, evaluates the
        F-field from this group only, and compares against the prescribed
        target value. Returns True if every element's mean error is below
        max_rel_error relative to its target magnitude.

        Used as a post-solve sanity check — if False, the group may need
        further splitting.
        """
        total_terms = 2 * n - 1
        for idx in group_indices:
            elem = elements[idx]
            outline = elem.outline
            step = max(1, len(outline) // 10)
            errors = []
            for (x_cp, y_cp) in outline[::step]:
                F = self._evaluate_group_field(
                    group_indices, elements, coeff, n,
                    x_cp, y_cp, alpha_l, alpha_t)
                f_tgt = self.f_target(x_cp, elem, ca, gamma, beta)
                if f_tgt is not None:
                    errors.append(abs(F - f_tgt))
            if not errors:
                continue
            mean_err = np.mean(errors)
            f_tgt_sample = self.f_target(elem.x, elem, ca, gamma, beta)
            denom = max(abs(f_tgt_sample), 1e-30) if f_tgt_sample is not None else 1e-30
            if mean_err / denom > max_rel_error:
                return False
        return True

    # Boundary condition target

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
          - Zero-isoline (Ci = 0): ca * exp(-beta*x)

        The image-element cases have flipped signs to enforce the no-flux
        mirror boundary condition at y=0.
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
        """
        n = self.config.num_terms
        alpha_l = self.config.alpha_l
        alpha_t = self.config.alpha_t
        total_coeffs = self.coeff
        total_terms = 2 * n - 1

        orders_all = np.arange(n)
        orders_odd = np.arange(1, n) if n > 1 else np.array([], dtype=int)

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

        total = F * np.exp(self.config.beta * x)
        if total > self.config.ca:
            return (total - self.config.ca) / self.config.gamma
        else:
            return total - self.config.ca

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
            self.config.beta, self.config.ca, self.config.gamma
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

    # Post-processing

    def generate_filename_suffix(self):
        """
        Build a descriptive filename suffix for output files.

        Format: <N>-elements_<num_terms>-terms_acceptor-<yes|no>_inc-<dom_inc>
        Used to keep output files self-describing when there are multiple
        runs in the Results directory.
        """
        n_elements = self.num_elements_original
        has_acceptor = any(elem.c < 0 for elem in self.config.elements)
        acceptor_str = "acceptor-yes" if has_acceptor else "acceptor-no"
        return f"{n_elements}-elements_{self.config.num_terms}-terms_{acceptor_str}_inc-{self.config.dom_inc}"

    def get_next_run_index(self, results_dir):
        """
        Return the next unused numeric run index for naming the output
        subdirectory.

        Scans <results_dir> for subdirectories named with zero-padded
        integers (0001, 0002, ...) and returns the highest + 1. Returns 1
        if the directory doesn't exist or has no numeric subdirectories.
        """
        if not os.path.exists(results_dir):
            return 1
        max_index = 0
        for entry in os.listdir(results_dir):
            if os.path.isdir(os.path.join(results_dir, entry)):
                try:
                    max_index = max(max_index, int(entry))
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

        if paths:
            max_x_overall = -np.inf
            for p in paths:
                v = p.vertices
                if v is None or len(v) == 0:
                    continue
                max_x_path = np.max(v[:, 0])
                if max_x_path > max_x_overall:
                    max_x_overall = max_x_path
                    chosen = v

            if chosen is not None and len(chosen) > 1:
                self.L_max = int(max_x_overall * self.config.dom_inc)
                diffs = np.diff(chosen, axis=0)
                self.interface_length = float(
                    np.sum(np.hypot(diffs[:, 0], diffs[:, 1])) * self.config.dom_inc)

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
        Image and zero-isoline auxiliary elements are skipped; their boundary
        concentrations differ from their stored c values by design.

        The 4 sample positions are:
          Circle / Ellipse: cardinal angles 0, π/2, π, 3π/2
          Line: fractions -3/4, -1/4, +1/4, +3/4 of the half-length
        """
        from math import cos, sin, pi

        stats = {}
        all_elem_errors = {}

        print("\n=== ELEMENT BOUNDARY STATISTICS ===")
        for idx, elem in enumerate(self.config.elements):
            # Image and zero-isoline elements have boundaries outside the
            # computation domain
            eid = elem.id.lower() if elem.id else ""
            if eid.startswith("image_") or eid.startswith("zero_"):
                print(f'Element {idx + 1}: ({eid}) — skipped (auxiliary element)')
                continue

            if elem.kind == ATElementType.Circle:
                phi = np.array([0.0, pi/2, pi, 3*pi/2])
                x_test = elem.x + (elem.r + 1e-9) * np.cos(phi)
                y_test = elem.y + (elem.r + 1e-9) * np.sin(phi)

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
        filename_suffix = self.generate_filename_suffix()
        stats_filename = os.path.join(
            self.run_dir, f"{self.run_index:04d}_stats_{filename_suffix}.txt")

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
        plt.xticks(np.linspace(0, 2 * math.pi, 5),
                   ['0°', '90°', '180°', '270°', '360°'])
        plt.legend(loc='best')
        plt.tight_layout()

        error_filename = os.path.join(
            self.run_dir, f"{self.run_index:04d}_error_{filename_suffix}.pdf")
        plt.savefig(error_filename)
        plt.close()
        print(f"Error plot saved to: {error_filename}")

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

        Image and zero-isoline auxiliary elements are excluded; only the
        user-defined source elements are drawn. Donor elements use the
        Reds colormap, acceptors use Blues_r. Dual colorbars at the bottom
        span the full donor and acceptor concentration ranges found in
        the config.

        Saves to Results/<run_index>/<run_index>_input_<suffix>.pdf.
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
                       label=f"Source zone (x ≤ {ws:.3f} m)")
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
        if has_donor:
            donor_levels = np.linspace(0, max_conc, 11)
            sm_d = plt.cm.ScalarMappable(cmap="Reds",
                                          norm=mpl.colors.Normalize(0, max_conc))
            sm_d.set_array([])
            cb_d = fig.colorbar(sm_d, ax=[ax_src, ax_dom], ticks=donor_levels,
                                label="Donor Concentration C_D [mg/L]",
                                location="bottom", pad=0.02, aspect=60)
            cb_d.ax.tick_params(labelsize=11)

        abs_min = abs(min_conc) if has_acceptor else ca
        acc_levels = np.linspace(-abs_min, 0, 9)
        sm_a = plt.cm.ScalarMappable(cmap="Blues_r",
                                      norm=mpl.colors.Normalize(-abs_min, 0))
        sm_a.set_array([])
        cb_a = fig.colorbar(sm_a, ax=[ax_src, ax_dom], ticks=acc_levels,
                            label="Acceptor Concentration C_A [mg/L]",
                            location="bottom",
                            pad=0.10 if has_donor else 0.02, aspect=60)
        cb_a.set_ticklabels([f"{abs(t):.0f}" for t in acc_levels])
        cb_a.ax.tick_params(labelsize=11)

        filename_suffix = self.generate_filename_suffix()
        input_filename = os.path.join(
            self.run_dir, f"{self.run_index:04d}_input_{filename_suffix}.pdf")
        plt.savefig(input_filename, bbox_inches="tight")
        plt.close()
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

        Saves to Results/<run_index>/<run_index>_plot_<suffix>.pdf.
        """
        max_val = float(np.max(self.result))
        min_val = float(np.min(self.result))
        abs_min = abs(min_val)
        xmin, xmax = self.config.dom_xmin, self.config.dom_xmax
        ymin, ymax = self.config.dom_ymin, self.config.dom_ymax

        donor_levels = np.linspace(0, max_val, 11)
        acceptor_levels = np.linspace(-abs_min, 0, 9)

        # Use 150 dpi for diagnostic runs; bump to 300 for publication quality.
        plot_dpi = 150

        mpl.rcParams.update({"font.size": 22})
        fig, ax = plt.subplots(figsize=(16, 9), dpi=plot_dpi)

        # Rasterize the filled contour collections on large grids to keep
        # the PDF compact. The zero-contour line stays vector (zorder=6).
        n_grid_pts = self.result.size
        rasterize = n_grid_pts > 10_000
        if rasterize:
            ax.set_rasterization_zorder(5)

        X, Y = np.meshgrid(self.xaxis, self.yaxis)

        donor = ax.contourf(
            X, Y, self.result,
            levels=donor_levels, cmap='Reds', extend='max',
            zorder=1 if rasterize else None
        )
        acceptor = ax.contourf(
            X, Y, self.result,
            levels=acceptor_levels, cmap='Blues_r', extend='min',
            zorder=2 if rasterize else None
        )
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
        ax.set_xlabel("$x$ (m)")
        ax.set_ylabel("$z$ (m)" if self.config.orientation == "vertical" else "$y$ (m)")

        plt.subplots_adjust(bottom=0.20)

        cbar_donor = fig.colorbar(
            donor, ticks=donor_levels,
            label='Donor Concentration C_D [mg/L]',
            location='bottom', pad=0.02, aspect=75)
        cbar_donor.ax.tick_params(labelsize=14)

        cbar_acceptor = fig.colorbar(
            acceptor, ticks=acceptor_levels,
            label='Acceptor Concentration C_A [mg/L]',
            location='bottom', pad=0.12, aspect=75)
        cbar_acceptor.set_ticklabels([f"{abs(t):.0f}" for t in acceptor_levels])
        cbar_acceptor.ax.tick_params(labelsize=14)

        if self.config.plot_aspect == "scaled":
            plt.axis("scaled")

        plt.tight_layout()

        filename_suffix = self.generate_filename_suffix()
        plot_filename = os.path.join(
            self.run_dir, f"{self.run_index:04d}_plot_{filename_suffix}.pdf")
        plt.savefig(plot_filename, dpi=plot_dpi)
        plt.close()
        print(f"Plot saved to: {plot_filename}")
