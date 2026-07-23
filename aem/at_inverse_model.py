import os
import sys
import datetime
import numpy as np
from math import cos, sin, pi
import matplotlib.pyplot as plt

from .at_config import ATConfiguration
from .at_element import ATElement, ATElementType
from .at_simulation import ATSimulation, create_mirrored_element

# Default inverse-modelling search configuration
PARAM_SEARCH_DEFAULTS = {
    # transverse dispersivity alpha_t [m]
    "alpha_t": {
        "lower": 0.001,
        "upper": 0.1,
        "initial_step_factor": 1.0 / 500.0,  # start with (ub-lb)/500
        "step_growth": 3.0,                  # each failure → step *= 3
        "max_step_factor": 0.2,              # step <= 0.2 * (ub - lb)
        "L_tolerance": 10.0,                  # |L_max - target| [m]
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
    # Radius r [m] – absolute global bounds (independent of source modifier)
    "r": {
        "lower": 0.5,
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

# Default fixed dispersivities used during inverse modelling.
# These values are applied depending on which parameter is being estimated:
#   - When estimating alpha_t, alpha_l is fixed to FIXED_ALPHA_L
#   - When estimating alpha_l, alpha_t is fixed to FIXED_ALPHA_T
#   - When estimating r/C0/ca/gamma → alpha_l and alpha_t are fixed to
#       ALPHA_L_WHEN_ESTIMATING_OTHERS and ALPHA_T_WHEN_ESTIMATING_OTHERS respectively.

FIXED_ALPHA_T = 0.1   # m
FIXED_ALPHA_L = 1.0   # m
ALPHA_T_WHEN_ESTIMATING_OTHERS = 0.1 #m
ALPHA_L_WHEN_ESTIMATING_OTHERS = 1.0 #m


# Global L_max tolerance (meters)
L_TOLERANCE_DEFAULT = 10.0

# Default stagnation limit for inverse solver
MAX_STAGNATION_DEFAULT = 5


#Folder path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "inverse_model_files")
os.makedirs(FILES_DIR, exist_ok=True)

class TeeOutput:
    """Write to both file and console simultaneously"""

    def __init__(self, file_handle, console_handle):
        self.file_handle = file_handle
        self.console_handle = console_handle

    def write(self, text):
        self.file_handle.write(text)
        self.console_handle.write(text)
        self.file_handle.flush()
        self.console_handle.flush()

    def flush(self):
        self.file_handle.flush()
        self.console_handle.flush()

def _in_files_dir(p: str) -> str:
    """Put relative filenames inside inverse_model_files; keep absolute paths as-is."""
    if os.path.isabs(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p
    return os.path.join(FILES_DIR, os.path.basename(p))


def _read_cases_with_optional_header(path: str):
    """Read cases from an input file.

    Supports:
    - Header row (first non-empty row contains any letters) which is ignored as data.
    - Column-based rows (dicts keyed by header names).
    - Backward compatible positional rows: r C0 ca gamma target [alpha_t alpha_l]

    Empty strings/NA/NaN are treated as missing.
    """
    raw = [ln.strip() for ln in open(path, "r") if ln.strip()]
    if not raw:
        return [], None

    first = raw[0]
    has_letters = any(ch.isalpha() for ch in first)

    def _clean(v):
        if v is None:
            return None
        v = str(v).strip()
        if v == "" or v.upper() in ("NA", "NAN"):
            return None
        return v

    if has_letters:
        header = first.split()
        data_lines = raw[1:]
        cases = []
        for ln in data_lines:
            parts = ln.split()
            # allow short rows; pad with None
            parts = parts + [None] * max(0, (len(header) - len(parts)))
            row = {k: _clean(v) for k, v in zip(header, parts)}
            cases.append(row)
        return cases, header

    # old positional format
    cases = []
    for ln in raw:
        parts = ln.split()
        cases.append({
            "r": _clean(parts[0] if len(parts) > 0 else None),
            "C0": _clean(parts[1] if len(parts) > 1 else None),
            "ca": _clean(parts[2] if len(parts) > 2 else None),
            "gamma": _clean(parts[3] if len(parts) > 3 else None),
            "target": _clean(parts[4] if len(parts) > 4 else None),
            # optional extras (if appended without header)
            "alpha_t": _clean(parts[5] if len(parts) > 5 else None),
            "alpha_l": _clean(parts[6] if len(parts) > 6 else None),
        })
    return cases, None

#
# Inverse-modelling overview:
#   - compute_lmax / compute_lmax_general: run a forward simulation and compute L_max.
#   - process_input_file_with_logging: read input lines, choose bounds and fixed parameters,
#       and call estimate_parameter_scanned for each case.
#   - estimate_parameter_scanned: single generic inverse solver that performs
#       dynamic scanning between lower/upper bounds and bisection to match target L_max.

def compute_lmax(alpha, r, C0, Ca, gamma, orientation, elem_kind, target_Lmax, print_context=None):
    cfg = ATConfiguration.from_json("simulation_config.json")
    cfg.alpha_t = alpha
    cfg.ca = Ca
    cfg.gamma = gamma
    cfg.orientation = orientation
    cfg.dom_inc = 0.5
    if target_Lmax is not None:
        cfg.dom_xmax = max(cfg.dom_xmax, target_Lmax * 1.1)

    if orientation == "vertical":
        if elem_kind == "Circle":
            base = ATElement(ATElementType.Circle, x=0.0, y=-(r + 0.01), c=C0, r=r)
        elif elem_kind == "Line":
            base = ATElement(ATElementType.Line, x=0.0, y=-(r + 0.01), c=C0, r=r)
        else:
            raise ValueError(f"Unknown element type: {elem_kind}")
        img = create_mirrored_element(base)
        img.id = f"image_{base.id}"
        cfg.elements = [base, img]
        cfg.dom_ymax = 0.0
    else:
        if elem_kind == "Circle":
            base = ATElement(ATElementType.Circle, x=0.0, y=0.0, c=C0, r=r)
        else:
            base = ATElement(ATElementType.Line, x=0.0, y=0.0, c=C0, r=r)
        cfg.elements = [base]

    for e in cfg.elements:
        e.calc_d_q(cfg.alpha_t, cfg.alpha_l, cfg.beta)
        e.set_outline(cfg.num_cp)

    sim = ATSimulation(cfg)
    sim.solve_system(cfg.alpha_l, cfg.alpha_t, cfg.beta, cfg.gamma, cfg.ca, cfg.num_terms, cfg.num_cp)
    sim.conc_array(cfg.dom_xmin, cfg.dom_ymin, cfg.dom_xmax, cfg.dom_ymax, cfg.dom_inc)
    sim.print_context = print_context
    sim.calculate_lmax()
    return sim.L_max, sim

def compute_lmax_general(
        r, C0, Ca, gamma, alpha_t, alpha_l,
        orientation="horizontal", elem_kind="Circle", target_Lmax=None, print_context=None
):
    """
    Computes L_max with general parameters.
    """
    cfg = ATConfiguration.from_json("simulation_config.json")
    # Set physical / transport parameters
    cfg.alpha_t = float(alpha_t)
    cfg.alpha_l = float(alpha_l)
    cfg.ca = float(Ca)
    cfg.gamma = float(gamma)
    cfg.orientation = orientation
    # Grid increment
    cfg.dom_inc = 0.5

    # Expand domain in x if target_Lmax is known
    if target_Lmax is not None and cfg.dom_xmax < target_Lmax * 1.1:
        cfg.dom_xmax = target_Lmax * 1.1

    # Build elements
    if orientation == "vertical":
        if elem_kind == "Circle":
            base = ATElement(ATElementType.Circle, x=0.0, y=-(r + 0.01), c=C0, r=r)
        elif elem_kind == "Line":
            base = ATElement(ATElementType.Line, x=0.0, y=-(r + 0.01), c=C0, r=r)
        else:
            raise ValueError(f"Unknown element type: {elem_kind}")
        img = create_mirrored_element(base)
        img.id = f"image_{base.id}"
        cfg.elements = [base, img]
        cfg.dom_ymax = 0.0
    else:
        if elem_kind == "Circle":
            base = ATElement(ATElementType.Circle, x=0.0, y=0.0, c=C0, r=r)
        elif elem_kind == "Line":
            base = ATElement(ATElementType.Line, x=0.0, y=0.0, c=C0, r=r)
        else:
            raise ValueError(f"Unknown element type: {elem_kind}")
        cfg.elements = [base]

    #run simulation
    for e in cfg.elements:
        e.calc_d_q(cfg.alpha_t, cfg.alpha_l, cfg.beta)
        e.set_outline(cfg.num_cp)

    sim = ATSimulation(cfg)
    sim.solve_system(cfg.alpha_l, cfg.alpha_t, cfg.beta, cfg.gamma, cfg.ca, cfg.num_terms, cfg.num_cp)
    sim.conc_array(cfg.dom_xmin, cfg.dom_ymin, cfg.dom_xmax, cfg.dom_ymax, cfg.dom_inc)
    sim.print_context = print_context
    sim.calculate_lmax()
    return sim.L_max, sim



def save_statistics(sim, line_index, statsfile):
    """
    Save boundary error statistics to 'find_alpha_stats.txt'
    """
    phi = np.linspace(0, 2 * pi, 360)
    stats_file = statsfile

    with open(stats_file, "a") as f:
        f.write(f"\n=== Stats for Line {line_index} ===\n")
        for idx, elem in enumerate(sim.config.elements):
            if elem.kind == ATElementType.Circle:
                x_test = elem.x + (elem.r + 1e-9) * np.cos(phi)
                y_test = elem.y + (elem.r + 1e-9) * np.sin(phi)
            elif elem.kind == ATElementType.Line:
                half_len = elem.r
                s = np.linspace(-half_len + 1e-9, half_len - 1e-9, 360)
                theta = elem.theta
                x_test = elem.x + s * cos(theta)
                y_test = elem.y + s * sin(theta)
            else:
                raise ValueError(f"Unknown element type: {elem.kind}")

            Err = [sim.calc_c(x, y) for x, y in zip(x_test, y_test)]
            min_val = round(np.min(Err), 9)
            max_val = round(np.max(Err), 9)
            mean_val = round(np.mean(Err), 9)
            std_val = round(np.std(Err), 9)

            f.write(f"Element {idx + 1}:\n")
            f.write(f"  Min = {min_val} mg/l\n")
            f.write(f"  Max = {max_val} mg/l\n")
            f.write(f"  Mean = {mean_val} mg/l\n")
            f.write(f"  Standard Deviation = {std_val} mg/l\n")



def process_input_file_with_logging(
        input_file,
        output_file=None,
        statsfile=None,
        orientation="horizontal",
        elem_kind="Circle",
        source_thickness_modifier=1.0,
        tolerance: float = None,
        max_stagnation: int = None,
        estimate_param: str = "alpha_t",
        lower_bound: float = None,
        upper_bound: float = None
):
    """Function that logs parameters and outputs per input line interleaved."""
    input_file = _in_files_dir(input_file)
    output_file = _in_files_dir(output_file)
    statsfile = _in_files_dir(statsfile)
    log_file = os.path.join(FILES_DIR, "findalpha_log.txt")

    # Use editable module default if not provided
    if max_stagnation is None:
        max_stagnation = int(MAX_STAGNATION_DEFAULT)
    else:
        max_stagnation = int(max_stagnation)

    with open(log_file, 'a') as f:
        # Add timestamp header for new run
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write("\n" + "*" * 80 + "\n")
        f.write(f"NEW RUN STARTED AT: {timestamp}\n")
        f.write("*" * 80 + "\n")
        # Write parameters
        f.write("FINDALPHA MODE PARAMETERS:\n")
        f.write("=" * 80 + "\n")
        f.write(f"INPUT_FILE: {input_file}, OUTPUT_FILE: {output_file}, STATSFILE: {statsfile}\n")
        f.write(f", ORIENTATION: {orientation}, ELEM_KIND: {elem_kind}, SOURCE_THICKNESS_MODIFIER: {source_thickness_modifier}, \n")
        f.write(f" TOLERANCE: {tolerance}, MAX_STAGNATION: {max_stagnation}\n")
        f.write(f" ESTIMATE_PARAM: {estimate_param}, LOWER_BOUND: {lower_bound}, UPPER_BOUND: {upper_bound}\n")

        # Set up tee output to write to both file and console
        original_stdout = sys.stdout
        original_stderr = sys.stderr


        try:
            # Create tee objects
            tee_stdout = TeeOutput(f, original_stdout)
            tee_stderr = TeeOutput(f, original_stderr)
            sys.stdout = tee_stdout
            sys.stderr = tee_stderr

            # Print target parameter once per run
            print("=" * 80)
            print(f"Target parameter: {estimate_param}")
            print("=" * 80)

            # Clear stats file
            open(statsfile, "w").close()
            cases, header = _read_cases_with_optional_header(input_file)
            results, skipped = [], []

            for i, row in enumerate(cases, 1):
                f.write("=" * 80 + "\n")
                f.write(f"Input Line {i}: {row}\n")
                # Parse inputs (supports header-based or positional files)
                def _f(name, default=None):
                    v = row.get(name, None)
                    return default if v is None else float(v)

                r = _f("r")
                C0 = _f("C0")
                Ca = _f("ca")
                gamma = _f("gamma")

                # target can be labelled 'target' or 'target_Lmax'
                target = _f("target", None)
                if target is None:
                    target = _f("target_Lmax")

                # optional per-case dispersivities
                alpha_t_in = _f("alpha_t", None)
                alpha_l_in = _f("alpha_l", None)

                # for error reporting
                params = [r, C0, Ca, gamma, target, alpha_t_in, alpha_l_in]

                if estimate_param == "r":
                    r_eff = r
                else:
                    r_eff = r * source_thickness_modifier

                print("=" * 80)
                print(f"Processing line {i}: target_Lmax = {target}")
                if alpha_t_in is not None or alpha_l_in is not None:
                    print(f"Case overrides: alpha_t={alpha_t_in} alpha_l={alpha_l_in}")
                # print(f"Target parameter: {estimate_param}")  # Removed per instructions
                print("=" * 80)
                try:
                    # Decide default bounds if not provided using PARAM_SEARCH_DEFAULTS
                    pdefs = PARAM_SEARCH_DEFAULTS.get(estimate_param, {})
                    lb, ub = lower_bound, upper_bound

                    if lb is None or ub is None:
                        if estimate_param in ("alpha_t", "alpha_l"):
                            lb = float(pdefs.get("lower", 1e-3)) if lb is None else lb
                            ub = float(pdefs.get("upper", 1.0))  if ub is None else ub
                        elif estimate_param == "r":
                            # Use absolute global bounds for radius, independent of r_eff
                            lb = float(pdefs.get("lower", 0.5)) if lb is None else lb
                            ub = float(pdefs.get("upper", 8.0))  if ub is None else ub
                        elif estimate_param in ("C0", "ca", "gamma"):
                            base_map = {"C0": C0, "ca": Ca, "gamma": gamma}
                            base = float(base_map[estimate_param])
                            fl = float(pdefs.get("factor_lower", 0.5))
                            fu = float(pdefs.get("factor_upper", 2.0))
                            raw_lb = fl * base
                            raw_ub = fu * base
                            min_abs = float(pdefs.get("min_abs", raw_lb))
                            max_abs = float(pdefs.get("max_abs", raw_ub))
                            lb = raw_lb if lb is None else lb
                            ub = raw_ub if ub is None else ub
                            lb = max(min_abs, lb)
                            ub = min(max_abs, ub)
                        else:
                            raise ValueError(f"Unknown estimate_param: {estimate_param}")

                    if not (np.isfinite(lb) and np.isfinite(ub) and lb < ub):
                        raise ValueError(f"Invalid bounds: lower={lb}, upper={ub}")

                    # Fixed parameters with per-case override support
                    fixed = {
                        "r": r_eff,
                        "C0": C0,
                        "ca": Ca,
                        "gamma": gamma,
                    }
                    if estimate_param == "alpha_t":
                        # estimating alpha_t → alpha_l fixed
                        fixed["alpha_l"] = alpha_l_in if alpha_l_in is not None else FIXED_ALPHA_L
                    elif estimate_param == "alpha_l":
                        # estimating alpha_l → alpha_t fixed
                        fixed["alpha_t"] = alpha_t_in if alpha_t_in is not None else FIXED_ALPHA_T
                    else:
                        # estimating other parameters → both dispersivities fixed
                        fixed["alpha_t"] = alpha_t_in if alpha_t_in is not None else ALPHA_T_WHEN_ESTIMATING_OTHERS
                        fixed["alpha_l"] = alpha_l_in if alpha_l_in is not None else ALPHA_L_WHEN_ESTIMATING_OTHERS

                    # L_max tolerance: global default unless overridden
                    if tolerance is None:
                        L_tol = float(L_TOLERANCE_DEFAULT)
                    else:
                        L_tol = float(tolerance)

                    # Run the dynamic-scan -> bracket -> bisect
                    p_hat, L, sim = estimate_parameter_scanned(
                        estimate_param,
                        lb,
                        ub,
                        fixed,
                        target,
                        orientation=orientation,
                        elem_kind=elem_kind,
                        L_tolerance=L_tol,
                        param_defaults=pdefs,
                        max_stagnation=max_stagnation
                    )

                    # Pretty symbol for the parameter
                    sym = {
                        "alpha_t": "αₜ",
                        "alpha_l": "αₗ",
                        "r": "r",
                        "C0": "C₀",
                        "ca": "Cₐ",
                        "gamma": "γ"
                    }[estimate_param]

                    warning = ""
                    if estimate_param == "alpha_t" and p_hat > 0.1:
                        warning = " [WARNING: αₜ > 0.1]"

                    result = (
                        f"Line {i}: aq = {r}, r={r_eff: .3f}, C0={C0}, Ca={Ca}, γ={gamma}, "
                        f"target={target} → {sym}={p_hat:.6f}, Lmax={L:.6f}{warning}"
                    )
                    results.append(result)

                    if sim is not None:
                        save_statistics(sim, i, statsfile)

                except Exception as e:
                    err_msg = f"Line {i}: params={params}  ERROR: {e}"
                    print(f"  [ERROR] {e}")
                    skipped.append(err_msg)

            with open(output_file, "w") as out_f:
                for line in results:
                    out_f.write(line + "\n")
                out_f.write("\nSkipped Cases:\n")
                for line in skipped:
                    out_f.write(line + "\n")
            print(f"Wrote {len(results)} results, {len(skipped)} skipped to '{output_file}'")

        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

def estimate_parameter_scanned(
        param_name: str,
        lower_bound: float,
        upper_bound: float,
        fixed_params: dict,
        target_Lmax: float,
        orientation: str = "horizontal",
        elem_kind: str = "Circle",
        L_tolerance: float = 1e-3,
        param_defaults: dict = None,
        max_scan_steps: int = 300,
        max_bisect_iter: int = 60,
        max_stagnation: int = None
):
    """
    generalized dynamic-scan -> bracket -> bisection:

      1) Dynamically scan upward from lower_bound with a tiny step that grows
         quickly when no valid L_max is found.
      2) Dynamically scan downward from upper_bound similarly.
      3) If target is not bracketed, scan between to find a sign change.
      4) Run bisection within the bracketing interval.

    No explicit start value: only lower_bound, upper_bound, and dynamic step sizes.
    """
    param_defaults = param_defaults or {}
    lb = float(lower_bound)
    ub = float(upper_bound)

    # Use editable module default if not provided
    if max_stagnation is None:
        max_stagnation = int(MAX_STAGNATION_DEFAULT)
    else:
        max_stagnation = int(max_stagnation)

    if not (np.isfinite(lb) and np.isfinite(ub) and lb < ub):
        raise ValueError(f"Bad bounds: lower={lb}, upper={ub}")

    def eval_param(val):
        fp = dict(fixed_params)
        if param_name == "r":
            fp["r"] = float(val)
        elif param_name == "C0":
            fp["C0"] = float(val)
        elif param_name == "ca":
            fp["ca"] = float(val)
        elif param_name == "gamma":
            fp["gamma"] = float(val)
        elif param_name == "alpha_t":
            fp["alpha_t"] = float(val)
        elif param_name == "alpha_l":
            fp["alpha_l"] = float(val)

        if "alpha_t" not in fp or "alpha_l" not in fp:
            raise ValueError("Both alpha_t and alpha_l must be defined before simulation.")

        ctx = f"{param_name}={float(val):.6g}"
        L, sim = compute_lmax_general(
            fp["r"], fp["C0"], fp["ca"], fp["gamma"],
            fp["alpha_t"], fp["alpha_l"],
            orientation=orientation, elem_kind=elem_kind, target_Lmax=target_Lmax,
            print_context=ctx
        )

        # Standardized per-evaluation print (covers lower/upper scans and mid-scan too)
        if L is None or (isinstance(L, float) and np.isnan(L)):
            print(f"L_max({ctx}) = -")
        else:
            print(f"L_max({ctx}) = {L}")

        return L, sim

    # Dynamic step parameters
    span = ub - lb
    init_factor = float(param_defaults.get("initial_step_factor", 1.0 / 500.0))
    growth = float(param_defaults.get("step_growth", 3.0))
    max_factor = float(param_defaults.get("max_step_factor", 0.2))

    base_step = max(span * init_factor, 1e-6 * max(1.0, abs(lb)))
    max_step = max(span * max_factor, base_step)

    def dynamic_scan_up(start_val):
        p = float(start_val)
        step = base_step
        fail_count = 0
        for _ in range(max_scan_steps):
            if p > ub:
                break
            try:
                Lp, simp = eval_param(p)
                if Lp is not None and not np.isnan(Lp):
                    return p, Lp, simp
            except Exception:
                pass

            # failed attempt
            fail_count += 1
            if fail_count >= 3:
                step = min(step * growth, max_step)
                fail_count = 0

            p += step
        return None, None, None

    def dynamic_scan_down(start_val):
        q = float(start_val)
        step = base_step
        fail_count = 0
        for _ in range(max_scan_steps):
            if q < lb:
                break
            try:
                Lq, simq = eval_param(q)
                if Lq is not None and not np.isnan(Lq):
                    return q, Lq, simq
            except Exception:
                pass

            # failed attempt
            fail_count += 1
            if fail_count >= 3:
                step = min(step * growth, max_step)
                fail_count = 0

            q -= step
        return None, None, None

    #Upward scan from lower_bound
    p, Lp, simp = dynamic_scan_up(lb)
    if Lp is None or np.isnan(Lp):
        raise RuntimeError(
            f"Could not compute a valid L_max when scanning up from lower bound {lb} "
            f"up to {ub} for parameter {param_name}."
        )
    f_p = Lp - target_Lmax

    #Downward scan from upper_bound
    q, Lq, simq = dynamic_scan_down(ub)
    if Lq is None or np.isnan(Lq):
        raise RuntimeError(
            f"Could not compute a valid L_max when scanning down from upper bound {ub} "
            f"down to {lb} for parameter {param_name}."
        )
    f_q = Lq - target_Lmax

    # Immediate rejection if target is outside attainable L_max range at the bounds
    L_lo = min(Lp, Lq)
    L_hi = max(Lp, Lq)
    if target_Lmax < (L_lo - L_tolerance) or target_Lmax > (L_hi + L_tolerance):
        raise RuntimeError(
            f"Target L_max={target_Lmax} not within bounds implied by parameter interval [{lb}, {ub}]. "
            f"Computed L_max range at bounds: [{L_lo}, {L_hi}]."
        )

    # If either bound already matches within tolerance, stop immediately
    if abs(f_p) <= L_tolerance:
        return p, Lp, simp
    if abs(f_q) <= L_tolerance:
        return q, Lq, simq

    # Ensure bracketing; if not, scan between p and q for sign change
    if f_p * f_q > 0:
        last_val, last_f = p, f_p
        n_mid = 50
        mid_step = (q - p) / float(n_mid)
        found = False
        x = p + mid_step
        while x <= q:
            Lx, simx = eval_param(x)
            fx = Lx - target_Lmax
            if abs(fx) <= L_tolerance:
                return x, Lx, simx
            if last_f * fx <= 0:
                p, f_p = last_val, last_f
                q, f_q = x, fx
                found = True
                break
            last_val, last_f = x, fx
            x += mid_step
        if not found:
            raise RuntimeError(
                f"Target L_max not bracketed in [{lb}, {ub}] for parameter {param_name}. "
                f"L(lb)={Lp}, L(ub)={Lq}, target={target_Lmax}."
            )

    # Bisection
    best_sim = None
    best_mid = None
    best_abs = float("inf")
    stagn = 0
    last_best_abs = None

    for _ in range(int(max_bisect_iter)):
        mid = 0.5 * (p + q)
        Lm, simm = eval_param(mid)
        diff = Lm - target_Lmax
        absdiff = abs(diff)

        # track best-so-far
        if absdiff < best_abs:
            best_abs = absdiff
            best_mid = mid
            best_sim = simm

        print(
            f"[bisect] target={target_Lmax:.8g} | {param_name}={mid:.8g} | "
            f"L_max ({param_name}={mid:.8g}) = {Lm:.8g} | diff={diff:.8g}"
        )

        # tolerance break (robust)
        if absdiff <= L_tolerance:
            return mid, Lm, simm

        # stagnation break: if best_abs no longer improves
        if last_best_abs is None:
            last_best_abs = best_abs
        else:
            if abs(last_best_abs - best_abs) < 1e-12:
                stagn += 1
            else:
                stagn = 0
            last_best_abs = best_abs

        if stagn >= int(max_stagnation):
            # Return best-so-far if we're stuck
            if best_mid is not None:
                Lb, sim_b = eval_param(best_mid)
                return best_mid, Lb, sim_b or best_sim
            break

        # usual bisection interval update
        if f_p * diff <= 0:
            q, f_q = mid, diff
        else:
            p, f_p = mid, diff

    # If bisection exhausted, return best-so-far (or midpoint if none)
    if best_mid is None:
        best_mid = 0.5 * (p + q)
    Lm, simm = eval_param(best_mid)
    return best_mid, Lm, simm or best_sim