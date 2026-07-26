from __future__ import annotations

import base64
import io
import logging
import math
import os
import shutil
import signal
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

try:
    import flopy
except Exception:  # pragma: no cover
    flopy = None

try:
    from scipy.special import erfinv
except Exception:  # pragma: no cover
    erfinv = None

try:
    from scipy.ndimage import zoom as _nd_zoom
except Exception:  # pragma: no cover
    _nd_zoom = None

logger = logging.getLogger(__name__)
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s | %(message)s"))
    logger.addHandler(console_handler)
logger.setLevel(logging.INFO)
logger.propagate = False


@dataclass(frozen=True)
class NumericalModelResult:
    plume_length: float
    plot_html: str
    concentration: np.ndarray
    x_grid: np.ndarray
    z_grid: np.ndarray
    plot_png: bytes = b""
    domain_length: float = 0.0
    aquifer_thickness: float = 0.0
    peclet: float = 0.0
    courant: float = 5.0
    perlen: float = 0.0
    k_warning: str = ""
    head_file: bytes = b""
    concentration_file: bytes = b""


@dataclass(frozen=True)
class HorizontalModelResult:
    plume_length: float
    concentration: np.ndarray
    x_grid: np.ndarray
    y_grid: np.ndarray
    plot_png: bytes = b""
    domain_length: float = 0.0
    domain_width: float = 0.0
    peclet: float = 0.0
    courant: float = 5.0
    perlen: float = 0.0
    k_warning: str = ""
    head_file: bytes = b""
    concentration_file: bytes = b""


def _resolve_executable(env_name: str, fallback_names: list[str]) -> str:
    configured = os.getenv(env_name)
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.exists():
            raise RuntimeError(
                f"Executable not found for {env_name}: configured path '{configured_path}'. "
                f"Searched configured path, .modflow_bin/, solvers/, bin/, and PATH. "
                f"Set {env_name} to an existing MODFLOW 6 executable."
            )
        if os.name != "nt" and configured_path.suffix.lower() == ".exe":
            raise RuntimeError(
                f"{env_name} points to a Windows executable ({configured_path.name}), "
                "which cannot run inside Docker/Linux. Provide a Linux binary instead."
            )
        resolved = str(configured_path.resolve())
        logger.info("Resolved %s executable: %s", env_name, resolved)
        return resolved

    local_dirs = [
        Path.cwd() / ".modflow_bin",
        Path.cwd() / "solvers",
        Path.cwd() / "bin",
    ]
    windows_only: list[str] = []

    for name in fallback_names:
        found = shutil.which(name)
        if found:
            found_path = Path(found).resolve()
            if os.name != "nt" and found_path.suffix.lower() == ".exe":
                windows_only.append(str(found_path))
                continue
            resolved = str(found_path)
            logger.info("Resolved %s executable from PATH: %s", env_name, resolved)
            return resolved
        for directory in local_dirs:
            local = directory / name
            if local.exists():
                if os.name != "nt" and local.suffix.lower() == ".exe":
                    windows_only.append(str(local))
                    continue
                resolved = str(local.resolve())
                logger.info("Resolved %s executable: %s", env_name, resolved)
                return resolved

    if os.name != "nt" and windows_only:
        raise RuntimeError(
            f"Only Windows solver binaries were found for {env_name}: {windows_only}. "
            "Docker numerical runs require Linux solver binaries in solvers/ or on PATH."
        )
    raise RuntimeError(
        f"Executable not found for {env_name}. Searched .modflow_bin/, solvers/, bin/, and PATH "
        f"for {fallback_names}. Set {env_name} to an existing MODFLOW 6 executable."
    )


def _mf6_exe() -> str:
    return _resolve_executable("MF6_EXE", ["mf6.exe", "mf6"])


def _nstp(Lx: float, ncol: int, prsity: float, al: float, h1: float, h2: float, hk: float, perlen: float) -> int:
    """Number of timesteps at Courant = 1 (matching Orlando's script approach)."""
    gradient = (h1 - h2) / Lx
    q = hk * gradient
    v = q / prsity
    if v <= 0:
        raise ValueError("Head at left boundary must be greater than head at right boundary.")
    delr = Lx / ncol
    dt_target = delr / v
    return max(int(math.ceil(perlen / dt_target)), 1)


def _steady_state_perlen(Lx, prsity, h1, h2, hk, plume_length, buffer_days=1000.0):
    """Auto simulation time: advective travel time to reach the (analytical) plume
    length, plus a buffer to settle into a steady shape. Used when perlen is None so
    the fixed placeholder time can be dropped (Anton: time should not be a user input).
    Falls back to the domain length when no analytical plume length is supplied."""
    gradient = (h1 - h2) / Lx
    v = hk * gradient / prsity
    if v <= 0:
        raise ValueError("Head at left boundary must be greater than head at right boundary.")
    return (float(plume_length) / v) + float(buffer_days)


def balanced_source_buffers(domain_thickness: float, source_thickness: float) -> tuple[float, float]:
    """Center a source vertically when the user has not supplied buffer overrides."""
    if domain_thickness <= 0 or source_thickness <= 0:
        raise ValueError("Domain thickness and source thickness must be positive.")
    if source_thickness > domain_thickness:
        raise ValueError("Source thickness must fit within aquifer thickness.")
    buffer = (domain_thickness - source_thickness) / 2.0
    return buffer, buffer


def _plume_length(x_grid: np.ndarray, y_grid: np.ndarray, concentration: np.ndarray, c0: float) -> float:
    finite = concentration[np.isfinite(concentration)]
    if not finite.size or not (float(np.nanmin(finite)) < c0 < float(np.nanmax(finite))):
        return 0.0
    fig, ax = plt.subplots()
    try:
        cs = ax.contour(x_grid, y_grid, concentration, levels=[c0])
        segs = cs.allsegs[0] if getattr(cs, "allsegs", None) else []
        xs = [pt[0] for seg in segs for pt in seg]
        return float(max(xs)) if xs else 0.0
    finally:
        plt.close(fig)


def _check_run(success: bool, buff, label: str) -> None:
    if not success:
        detail = "\n".join(str(line) for line in (buff or []))
        raise RuntimeError(f"{label} execution failed.\n{detail}")


def _numerical_max_cells() -> int:
    return int(os.getenv("NUMERICAL_MAX_CELLS", os.getenv("MAX_GRID_CELLS", "40000")))


def _solver_timeout_seconds() -> float:
    return float(os.getenv("NUMERICAL_SOLVER_TIMEOUT_S", os.getenv("SOLVER_TIMEOUT_SECONDS", "0")))


def _k_range_warning(hk: float) -> str:
    """Accept any K but warn when it is outside the typical sand-aquifer range
    (configurable). Implements the agreed 'accept + warn' policy (O9)."""
    lo = float(os.getenv("NUMERICAL_HK_MIN_M_PER_DAY", "1"))
    hi = float(os.getenv("NUMERICAL_HK_MAX_M_PER_DAY", "100"))
    if hk < lo or hk > hi:
        msg = (f"Hydraulic conductivity K = {hk:g} m/d is outside the typical "
               f"range ({lo:g}-{hi:g} m/d); results may be unrealistic.")
        logger.warning(msg)
        return msg
    return ""


def _display_field(arr, ny: int = 240, nx: int = 480):
    """Upsample a coarse concentration slice for a smooth, detailed render (DISPLAY ONLY;
    does not affect plume_length, the C0 threshold, or any returned data). Falls back to the
    raw array when scipy is unavailable or the grid is already fine."""
    a = np.asarray(arr, dtype=float)
    if _nd_zoom is None or a.ndim != 2:
        return a
    fy = max(1, int(round(ny / max(a.shape[0], 1))))
    fx = max(1, int(round(nx / max(a.shape[1], 1))))
    if fy == 1 and fx == 1:
        return a
    return _nd_zoom(a, (fy, fx), order=1)


def _check_grid_size(ncol: int, nrow: int, *, grid_size=None, domain_length=None, cross_extent=None) -> None:
    total = ncol * nrow
    max_cells = _numerical_max_cells()
    if total > max_cells:
        detail = ""
        if grid_size is not None and domain_length is not None and cross_extent is not None:
            recommended = math.sqrt((float(domain_length) * float(cross_extent)) / float(max_cells))
            detail = (
                f" Derived domain is L_D={float(domain_length):.2f} m by {float(cross_extent):.2f} m "
                f"with grid size {float(grid_size):.6g} m. Use grid size >= {recommended:.2f} m "
                "for this domain, or reduce the source/chemistry values that set L_D and width."
            )
        raise ValueError(
            f"Grid too large: {ncol} x {nrow} = {total:,} cells exceeds the "
            f"{max_cells:,}-cell limit. Increase Delta X / Delta Z "
            f"(or Delta Y for horizontal runs) to coarsen the grid.{detail}"
        )


def _grid_points(length: float, count: int) -> np.ndarray:
    return np.linspace(0.0, float(length), int(count))


def _cell_centers(cell_size: float, count: int) -> np.ndarray:
    """Cell-center coordinates for `count` cells of width `cell_size`.

    Use the actual simulated grid width (`count * cell_size`) instead of
    stretching `count` points across an analytical, pre-truncation domain.
    """
    return (np.arange(int(count)) + 0.5) * float(cell_size)


def _horizontal_plume_length_from_source_extent(
    concentration: np.ndarray,
    c0: float,
    delr: float,
    delc: float,
) -> float:
    finite = concentration[np.isfinite(concentration)]
    if not finite.size or not (float(np.nanmin(finite)) < c0 < float(np.nanmax(finite))):
        return 0.0
    nrow, ncol = concentration.shape
    extent = [0.0, ncol * float(delr), 0.0, nrow * float(delc)]
    fig, ax = plt.subplots()
    try:
        cs = ax.contour(concentration, [c0], colors="k", linewidths=2, extent=extent)
        xs = [pt[0] for seg in cs.allsegs[0] for pt in seg]
        return float(max(xs)) if xs else 0.0
    finally:
        plt.close(fig)


@contextmanager
def _timed_stage(label: str):
    started = time.perf_counter()
    logger.info("START %s", label)
    try:
        yield
    except Exception:
        logger.exception("FAILED %s after %.3f s", label, time.perf_counter() - started)
        raise
    logger.info("DONE %s in %.3f s", label, time.perf_counter() - started)


def _log_solver_output(label: str, stdout: str, stderr: str) -> None:
    for line in stdout.splitlines():
        logger.info("%s stdout | %s", label, line)
    for line in stderr.splitlines():
        logger.warning("%s stderr | %s", label, line)


def _terminate_solver_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        return


def _checked_run_sim(sim, label: str) -> None:
    """Run MF6 directly so a timeout can terminate the external solver process."""
    executable = str(Path(sim.exe_name).resolve())
    workspace = Path(sim.simulation_data.mfpath.get_sim_path()).resolve()
    timeout = _solver_timeout_seconds()
    logger.info("%s executable: %s", label, executable)
    logger.info("%s workspace: %s", label, workspace)
    logger.info("%s report=True capture enabled for solver stdout/stderr", label)

    with _timed_stage(f"{label} run_model"):
        proc = subprocess.Popen(
            [executable],
            cwd=workspace,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
            start_new_session=(os.name != "nt"),
        )
        if timeout > 0:
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                _terminate_solver_process(proc)
                stdout, stderr = proc.communicate()
                _log_solver_output(label, stdout, stderr)
                raise RuntimeError(
                    f"{label} timed out after {timeout:g} s and was terminated. "
                    "Use a coarser grid or a shorter simulation time."
                )
        else:
            stdout, stderr = proc.communicate()
        _log_solver_output(label, stdout, stderr)
        success = proc.returncode == 0 and "normal termination" in f"{stdout}\n{stderr}".lower()
        _check_run(success, [stdout, stderr], label)


def _log_grid(orientation: str, domain_length: float, cross_extent: float, ncol: int, nrow: int) -> None:
    logger.info(
        "%s numerical grid: L_D=%.6f m, A_T=%.6f m, n_cols=%d, n_rows=%d, cells=%d",
        orientation,
        domain_length,
        cross_extent,
        ncol,
        nrow,
        ncol * nrow,
    )


def run_numerical_model_horizontal(
    source_thickness: float,
    grid_size: float,
    al: float,
    at: float,
    gamma: float,
    cd: float,
    ca: float,
    prsity: float = 0.3,
    hk: float = 8.64,
    gradient: float = 0.0125,
    h_left: float = 20.0,
) -> HorizontalModelResult:
    """Plan-view (horizontal) reactive transport, matching Orlando's horizontal_W.py.

    Seven modifiable inputs: source_thickness (Sw), grid_size, al, at, gamma, Cd, Ca.
    Domain length L_D and width are DERIVED (Cirpka analytical, x1.5); heads come from a
    fixed gradient; simulation time is auto (travel time + 1000 d) at Courant target 5.
    porosity, K and gradient are standard defaults the caller may override.
    """
    if flopy is None:
        raise RuntimeError("flopy is not installed.")
    if erfinv is None:
        raise RuntimeError("scipy is required for the horizontal analytical domain length.")
    if min(source_thickness, grid_size, al, at, gamma, cd, ca, prsity, hk) <= 0:
        raise ValueError("All horizontal inputs must be positive.")

    delr = delc = float(grid_size)
    nlay = 1
    Ly = source_thickness * 10.0                 # domain width = 10 * Sw
    Lx = 1.5 * (source_thickness ** 2) / (16.0 * at * (erfinv(ca / (gamma * cd + ca)) ** 2))
    ncol = int(Lx / delr)
    nrow = int(Ly / delc)
    if ncol < 2 or nrow < 2:
        raise ValueError("Derived grid is too small; reduce the grid size.")
    _log_grid("Horizontal", Lx, Ly, ncol, nrow)
    _check_grid_size(ncol, nrow, grid_size=grid_size, domain_length=Lx, cross_extent=Ly)

    q = hk * gradient
    v = q / prsity
    if v <= 0:
        raise ValueError("Seepage velocity must be positive (check K and gradient).")
    peclet = delr / al
    perlen = float(int(Lx / v + 1000.0))
    dt_target = 5.0 * delr / v                    # Courant target = 5
    nts = max(int(math.ceil(perlen / dt_target)), 1)
    h1 = float(h_left)
    h2 = float(h1 - gradient * Lx)
    c0 = ca

    with _timed_stage("Horizontal executable resolution"):
        mf6 = _mf6_exe()
    run_root = Path.cwd() / ".numerical_runs"
    run_root.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(dir=run_root) as tmpdir:
        workdir = Path(tmpdir)
        mid = workdir.name.replace("-", "_")[:6]
        flow_name = f"gwf{mid}"
        gwf_ws = workdir / "gwf_base"

        # Flow model
        sim = flopy.mf6.MFSimulation(sim_name=flow_name, sim_ws=str(gwf_ws), exe_name=mf6)
        flopy.mf6.ModflowTdis(sim, perioddata=[[perlen, nts, 1.0]])
        flopy.mf6.ModflowIms(
            sim, print_option="SUMMARY", complexity="SIMPLE",
            outer_dvclose=1e-3, inner_dvclose=1e-3,
            outer_maximum=100, inner_maximum=200, relaxation_factor=0.97,
        )
        gwf = flopy.mf6.ModflowGwf(sim, modelname=flow_name)
        flopy.mf6.ModflowGwfdis(gwf, nlay=nlay, nrow=nrow, ncol=ncol,
                                delr=delr, delc=delc, top=0.0, botm=-1.0)
        chd_cells = [[(0, i, 0), h1] for i in range(nrow)] + \
                    [[(0, i, ncol - 1), h2] for i in range(nrow)]
        flopy.mf6.ModflowGwfchd(gwf, stress_period_data={0: chd_cells})
        strt = np.full((nlay, nrow, ncol), (h1 + h2) / 2.0, dtype=np.float32)
        strt[:, :, 0] = h1
        strt[:, :, -1] = h2
        flopy.mf6.ModflowGwfic(gwf, strt=strt)
        flopy.mf6.ModflowGwfnpf(gwf, save_specific_discharge=True, save_saturation=True,
                                icelltype=0, k=hk)
        flopy.mf6.ModflowGwfoc(
            gwf, budget_filerecord=f"{flow_name}.cbc", head_filerecord=f"{flow_name}.hds",
            saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")])
        gwf.name_file.save_flows = True
        with _timed_stage("MF6 horizontal flow write_input"):
            sim.write_simulation()
        _checked_run_sim(sim, "MF6 horizontal flow")

        # Transport model
        sim_name = f"gwt{mid}"
        run_name = f"tr{mid}"
        run_dir = workdir / "transport"
        simf = flopy.mf6.MFSimulation(sim_name=sim_name, sim_ws=str(run_dir), exe_name=mf6)
        flopy.mf6.ModflowTdis(simf, perioddata=[[perlen, nts, 1.0]])
        gwt = flopy.mf6.ModflowGwt(simf, modelname=run_name, save_flows=True)
        flopy.mf6.ModflowIms(simf, linear_acceleration="bicgstab")
        flopy.mf6.ModflowGwtdis(gwt, nlay=nlay, nrow=nrow, ncol=ncol,
                                delr=delr, delc=delc, top=0.0, botm=-1.0)
        flopy.mf6.ModflowGwtic(gwt, strt=np.full((nlay, nrow, ncol), 0, dtype=np.float32))
        flopy.mf6.ModflowGwtmst(gwt, porosity=prsity)
        flopy.mf6.ModflowGwtadv(gwt, scheme="TVD")
        flopy.mf6.ModflowGwtdsp(gwt, alh=np.full((nlay, nrow, ncol), al), ath1=at)
        flopy.mf6.ModflowGwtssm(gwt)

        n_src = max(int(np.round(source_thickness / delc)), 1)
        ci = nrow // 2
        half = n_src // 2
        if n_src % 2 == 0:
            s_start, s_end = ci - half, ci + half
        else:
            s_start, s_end = ci - half, ci + half + 1
        s_start = max(s_start, 0)
        s_end = min(s_end, nrow)
        source_conc = (gamma * cd) + ca
        cnc_cells = [((0, k, 0), source_conc) for k in range(s_start, s_end)]
        cnc_cells += [((0, 0, col), 0) for col in range(ncol)]
        cnc_cells += [((0, nrow - 1, col), 0) for col in range(ncol)]
        flopy.mf6.ModflowGwtcnc(gwt, stress_period_data={0: cnc_cells}, filename=f"{run_name}.cnc")
        flopy.mf6.ModflowGwtfmi(gwt, packagedata=[
            ("GWFHEAD", str(gwf_ws / f"{flow_name}.hds")),
            ("GWFBUDGET", str(gwf_ws / f"{flow_name}.cbc")),
        ])
        flopy.mf6.ModflowGwtoc(
            gwt, budget_filerecord=f"{sim_name}_gwt.cbc",
            concentration_filerecord=f"{sim_name}.ucn",
            saverecord=[("CONCENTRATION", "LAST"), ("BUDGET", "LAST")])
        with _timed_stage("MF6 horizontal transport write_input"):
            simf.write_simulation()
        _checked_run_sim(simf, "MF6 horizontal transport")

        conc_slice = np.asarray(gwt.output.concentration().get_data()[0], dtype=float)
        x_grid = _cell_centers(delr, ncol)
        y_grid = _cell_centers(delc, nrow)
        plume_length = _horizontal_plume_length_from_source_extent(conc_slice, c0, delr, delc)
        logger.info("MF6 horizontal plume_length=%.6f m", plume_length)

        _hds = gwf_ws / f"{flow_name}.hds"
        _ucn = run_dir / f"{sim_name}.ucn"
        head_file = _hds.read_bytes() if _hds.exists() else b""
        concentration_file = _ucn.read_bytes() if _ucn.exists() else b""

        # Real backward transform (Ca/Cd), right-side colorbars, schema annotations.
        plot_png = b""
        try:
            with _timed_stage("MF6 horizontal contour build"):
                C0 = ca
                disp = conc_slice
                oxygen = np.ma.masked_where(disp >= C0, C0 - disp)
                donor = np.ma.masked_where(disp <= C0, (disp - C0) / gamma)
                extent = [0.0, ncol * delr, 0.0, nrow * delc]
                fig, ax = plt.subplots(figsize=(11, 4))
                fig.subplots_adjust(right=0.80, bottom=0.16)
                im1 = ax.imshow(oxygen, cmap="Blues", vmin=0, vmax=ca, origin="lower",
                                extent=extent, aspect="auto", interpolation="nearest")
                im2 = ax.imshow(donor, cmap="Reds", vmin=0, vmax=cd, origin="lower",
                                extent=extent, aspect="auto", interpolation="nearest")
                ax.contour(disp, [C0], colors="k", linewidths=2.0, extent=extent)
                ax.set_xlabel("Distance Lx [m]")
                ax.set_ylabel("Horizontal Width [m]")
                ax.set_title("Contaminant Plume \u2014 Horizontal Model (Plan View)")
                sy0 = (Ly - source_thickness) / 2.0
                sy1 = (Ly + source_thickness) / 2.0
                ax.plot([0, 0], [sy0, sy1], color="#7a0a0a", lw=7, solid_capstyle="butt",
                        clip_on=False, zorder=5)
                ax.text((ncol * delr) * 0.012, (sy0 + sy1) / 2.0, "CD (Sw)", color="#7a0a0a",
                        ha="left", va="center", fontsize=8, zorder=7,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
                ax.text((ncol * delr) * 0.5, (nrow * delc) * 0.95, "CA", color="navy", ha="center", va="top", fontsize=10)
                if plume_length > 0:
                    ax.axvline(
                        plume_length,
                        color="k",
                        lw=1.2,
                        ls="--",
                        zorder=6,
                        label=f"Maximum Plume Length L_max = {plume_length:.1f} m",
                    )
                    ax.text(plume_length - (ncol * delr) * 0.006, (nrow * delc) * 0.5,
                            f"$L^n_{{max}}$ = {plume_length:.2f} m", color="k",
                            ha="right", va="center", fontsize=8, rotation=90, zorder=7,
                            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))
                    ax.legend()
                fig.text(0.5, 0.015,
                         f"$L_D$ = {Lx:.2f} m (1.5\u00b7$L_{{max}}$, Cirpka et al. 2005)   |   "
                         f"\u0394x=\u0394y = {delr:.2f} m   |   porosity = {prsity:.2f}   |   "
                         f"K = {hk:.2f} m/d   |   gradient = {gradient:.4f}   |   "
                         f"P\u00e9clet = {peclet:.2f}   |   Courant target = 5",
                         ha="center", fontsize=7, color="dimgray")
                pos = ax.get_position()
                cax_ca = fig.add_axes([pos.x1 + 0.02, pos.y0, 0.015, pos.height])
                cax_cd = fig.add_axes([pos.x1 + 0.10, pos.y0, 0.015, pos.height])
                cb_ca = fig.colorbar(im1, cax=cax_ca)
                cb_cd = fig.colorbar(im2, cax=cax_cd)
                cb_ca.ax.set_title(r"$C_a$ [mg/L]", pad=10)
                cb_cd.ax.set_title(r"$C_d$ [mg/L]", pad=10)
                buf = io.BytesIO()
                plt.savefig(buf, format="png", bbox_inches="tight", dpi=300)
                plt.close(fig)
                plot_png = buf.getvalue()
        except Exception:
            logger.exception("Horizontal PDF contour image build failed")

    return HorizontalModelResult(
        plume_length=plume_length,
        concentration=conc_slice,
        x_grid=x_grid,
        y_grid=y_grid,
        plot_png=plot_png,
        domain_length=Lx,
        domain_width=Ly,
        peclet=peclet,
        courant=5.0,
        perlen=perlen,
        k_warning=_k_range_warning(hk),
        head_file=head_file,
        concentration_file=concentration_file,
    )


def run_numerical_model(
    Lz: float,
    grid_size: float,
    al: float,
    atv: float,
    gamma: float,
    cd: float,
    ca: float,
    prsity: float = 0.3,
    hk: float = 8.64,
    gradient: float = 0.0125,
    h_left: float = 20.0,
) -> NumericalModelResult:
    """Vertical cross-section reactive transport, matching Orlando's vertical_W.py.

    Seven modifiable inputs: Lz (aquifer thickness), grid_size, al, atv, gamma, Cd, Ca.
    Domain length L_D is DERIVED (Liedl analytical, x1.5); heads from a fixed gradient;
    simulation time auto (travel time + 1000 d) at Courant target 5. Source spans the
    full thickness (top cell kept clean); no right-hand boundary (Orlando's choice).
    """
    if flopy is None:
        raise RuntimeError("flopy is not installed.")
    if min(Lz, grid_size, al, atv, gamma, cd, ca, prsity, hk) <= 0:
        raise ValueError("All vertical inputs must be positive.")

    model_nrow = 1
    delc = 1.0
    delv = float(grid_size)
    delr = delv
    nlay = int(Lz / delv)
    if nlay < 2:
        raise ValueError("Derived layer count is too small; reduce the grid size.")
    botm = np.linspace(0.0 - delv, -Lz, nlay)
    Lx = 1.5 * (4.0 * Lz ** 2) / (np.pi ** 2 * atv) * np.log((4.0 * gamma * cd + ca) / (np.pi * ca))
    if not np.isfinite(Lx) or Lx <= 0:
        raise ValueError("Vertical analytical domain length is invalid for these inputs.")
    ncol = int(Lx / delr)
    if ncol < 2:
        raise ValueError("Derived column count is too small; reduce the grid size.")
    _log_grid("Vertical", Lx, Lz, ncol, nlay)
    _check_grid_size(ncol, nlay, grid_size=grid_size, domain_length=Lx, cross_extent=Lz)

    q = hk * gradient
    v = q / prsity
    if v <= 0:
        raise ValueError("Seepage velocity must be positive (check K and gradient).")
    peclet = delr / al
    perlen = float(int(Lx / v + 1000.0))
    dt_target = 5.0 * delr / v                    # Courant target = 5
    nts = max(int(math.ceil(perlen / dt_target)), 1)
    h1 = float(h_left)
    h2 = float(h1 - gradient * Lx)
    c0 = ca

    with _timed_stage("Vertical executable resolution"):
        mf6 = _mf6_exe()
    run_root = Path.cwd() / ".numerical_runs"
    run_root.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(dir=run_root) as tmpdir:
        workdir = Path(tmpdir)
        mid = workdir.name.replace("-", "_")[:6]
        flow_name = f"gwf{mid}"
        gwf_ws = workdir / "gwf_base"

        # Flow model
        sim = flopy.mf6.MFSimulation(sim_name=flow_name, sim_ws=str(gwf_ws), exe_name=mf6)
        flopy.mf6.ModflowTdis(sim, perioddata=[[perlen, nts, 1.0]])
        flopy.mf6.ModflowIms(
            sim, print_option="SUMMARY", complexity="SIMPLE",
            outer_dvclose=1e-3, inner_dvclose=1e-3,
            outer_maximum=100, inner_maximum=200, relaxation_factor=0.97,
        )
        gwf = flopy.mf6.ModflowGwf(sim, modelname=flow_name)
        flopy.mf6.ModflowGwfdis(gwf, nlay=nlay, nrow=model_nrow, ncol=ncol,
                                delr=delr, delc=delc, top=0.0, botm=botm)
        chd_cells = [[(lay, 0, 0), h1] for lay in range(nlay)] + \
                    [[(lay, 0, ncol - 1), h2] for lay in range(nlay)]
        flopy.mf6.ModflowGwfchd(gwf, stress_period_data={0: chd_cells})
        strt = np.full((nlay, model_nrow, ncol), (h1 + h2) / 2.0, dtype=np.float32)
        strt[:, :, 0] = h1
        strt[:, :, -1] = h2
        flopy.mf6.ModflowGwfic(gwf, strt=strt)
        flopy.mf6.ModflowGwfnpf(gwf, save_specific_discharge=True, save_saturation=True,
                                icelltype=0, k=hk)
        flopy.mf6.ModflowGwfoc(
            gwf, budget_filerecord=f"{flow_name}.cbc", head_filerecord=f"{flow_name}.hds",
            saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")])
        gwf.name_file.save_flows = True
        with _timed_stage("MF6 vertical flow write_input"):
            sim.write_simulation()
        _checked_run_sim(sim, "MF6 vertical flow")

        # Transport model
        sim_name = f"gwt{mid}"
        run_name = f"tr{mid}"
        run_dir = workdir / "transport"
        simf = flopy.mf6.MFSimulation(sim_name=sim_name, sim_ws=str(run_dir), exe_name=mf6)
        flopy.mf6.ModflowTdis(simf, perioddata=[[perlen, nts, 1.0]])
        gwt = flopy.mf6.ModflowGwt(simf, modelname=run_name, save_flows=True)
        flopy.mf6.ModflowIms(simf, linear_acceleration="bicgstab")
        flopy.mf6.ModflowGwtdis(gwt, nlay=nlay, nrow=model_nrow, ncol=ncol,
                                delr=delr, delc=delc, top=0.0, botm=botm)
        flopy.mf6.ModflowGwtic(gwt, strt=np.full((nlay, model_nrow, ncol), 0, dtype=np.float32))
        flopy.mf6.ModflowGwtmst(gwt, porosity=prsity)
        flopy.mf6.ModflowGwtadv(gwt, scheme="TVD")
        flopy.mf6.ModflowGwtdsp(gwt, alh=np.full((nlay, model_nrow, ncol), al), ath1=atv)
        flopy.mf6.ModflowGwtssm(gwt)

        source_conc = (gamma * cd) + ca
        cnc_cells = [((lay, 0, 0), source_conc) for lay in range(1, nlay)]
        cnc_cells += [((0, 0, col), 0) for col in range(ncol)]
        flopy.mf6.ModflowGwtcnc(gwt, stress_period_data={0: cnc_cells}, filename=f"{run_name}.cnc")
        flopy.mf6.ModflowGwtfmi(gwt, packagedata=[
            ("GWFHEAD", str(gwf_ws / f"{flow_name}.hds")),
            ("GWFBUDGET", str(gwf_ws / f"{flow_name}.cbc")),
        ])
        flopy.mf6.ModflowGwtoc(
            gwt, budget_filerecord=f"{sim_name}_gwt.cbc",
            concentration_filerecord=f"{sim_name}.ucn",
            saverecord=[("CONCENTRATION", "LAST"), ("BUDGET", "LAST")])
        with _timed_stage("MF6 vertical transport write_input"):
            simf.write_simulation()
        _checked_run_sim(simf, "MF6 vertical transport")

        conc = np.asarray(gwt.output.concentration().get_data(), dtype=float)
        conc_slice = conc[:, 0, :]
        # Cell-center coordinates over the actual simulated extent (ncol*delr by
        # nlay*delv), matching the reference script's extent-based contour mapping
        # so the plume length agrees with vertical_W.py.
        x_grid = _cell_centers(delr, ncol)
        z_grid = _cell_centers(delv, nlay)
        plume_length = _plume_length(x_grid, z_grid, conc_slice, c0)
        logger.info("MF6 vertical plume_length=%.6f m", plume_length)

        _hds = gwf_ws / f"{flow_name}.hds"
        _ucn = run_dir / f"{sim_name}.ucn"
        head_file = _hds.read_bytes() if _hds.exists() else b""
        concentration_file = _ucn.read_bytes() if _ucn.exists() else b""

        plot_bytes = b""
        plot_url = ""
        try:
            with _timed_stage("MF6 vertical contour build"):
                C0 = ca
                disp = _display_field(conc_slice)
                oxygen = np.ma.masked_where(disp >= C0, C0 - disp)
                donor = np.ma.masked_where(disp <= C0, (disp - C0) / gamma)
                extent = [0.0, Lx, Lz, 0.0]
                fig, ax = plt.subplots(figsize=(11, 5))
                fig.subplots_adjust(right=0.80)
                im1 = ax.imshow(oxygen, cmap="Blues", vmin=0, vmax=ca, origin="upper",
                                extent=extent, aspect="auto", interpolation="bilinear")
                im2 = ax.imshow(donor, cmap="Reds", vmin=0, vmax=cd, origin="upper",
                                extent=extent, aspect="auto", interpolation="bilinear")
                ax.contour(disp, [C0], colors="k", linewidths=2.0, origin="upper", extent=extent)
                ax.set_xlabel("Distance [m]")
                ax.set_ylabel("Depth [m]")
                ax.set_title("Contaminant Plume \u2014 Vertical Model")
                delv_a = Lz / nlay
                ax.plot([0, 0], [delv_a, Lz], color="#7a0a0a", lw=7, solid_capstyle="butt",
                        clip_on=False, zorder=5)
                ax.text(Lx * 0.012, (delv_a + Lz) / 2.0, "CD (ST)", color="#7a0a0a",
                        ha="left", va="center", fontsize=8, zorder=7,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.8))
                ax.text(Lx * 0.5, Lz * 0.06, "CA", color="navy", ha="center", va="top", fontsize=10)
                if plume_length > 0:
                    ax.axvline(plume_length, color="k", lw=1.2, ls="--", zorder=6)
                    ax.text(plume_length - Lx * 0.006, Lz * 0.5,
                            f"$L^n_{{max}}$ = {plume_length:.2f} m", color="k",
                            ha="right", va="center", fontsize=8, rotation=90, zorder=7,
                            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.75))
                fig.text(0.5, 0.005,
                         f"$L_D$ = {Lx:.2f} m (1.5\u00b7$L_{{max}}$, Liedl et al. 2005)   |   "
                         f"\u0394x=\u0394z = {delr:.2f} m   |   porosity = {prsity:.2f}   |   "
                         f"K = {hk:.2f} m/d   |   gradient = {gradient:.4f}   |   "
                         f"P\u00e9clet = {peclet:.2f}   |   Courant target = 5",
                         ha="center", fontsize=7, color="dimgray")
                pos = ax.get_position()
                cax_ca = fig.add_axes([pos.x1 + 0.02, pos.y0, 0.015, pos.height])
                cax_cd = fig.add_axes([pos.x1 + 0.10, pos.y0, 0.015, pos.height])
                fig.colorbar(im1, cax=cax_ca).set_label("CA [mg/L]")
                fig.colorbar(im2, cax=cax_cd).set_label("CD [mg/L]")
                img = io.BytesIO()
                fig.savefig(img, format="png", bbox_inches="tight", dpi=150)
                plt.close(fig)
                plot_bytes = img.getvalue()
                plot_url = base64.b64encode(plot_bytes).decode()
        except Exception:
            logger.exception("Vertical plume image build failed")

    return NumericalModelResult(
        plume_length=plume_length,
        plot_html=f'<img src="data:image/png;base64,{plot_url}" alt="Numerical plume plot" style="width:100%;height:auto;border-radius:12px;" />',
        concentration=conc_slice,
        x_grid=x_grid,
        z_grid=z_grid,
        plot_png=plot_bytes,
        domain_length=Lx,
        aquifer_thickness=Lz,
        peclet=peclet,
        courant=5.0,
        perlen=perlen,
        k_warning=_k_range_warning(hk),
        head_file=head_file,
        concentration_file=concentration_file,
    )
