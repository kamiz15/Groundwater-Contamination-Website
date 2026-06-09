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


@dataclass(frozen=True)
class HorizontalModelResult:
    plume_length: float
    concentration: np.ndarray
    x_grid: np.ndarray
    y_grid: np.ndarray
    plot_png: bytes = b""


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
    return float(os.getenv("NUMERICAL_SOLVER_TIMEOUT_S", os.getenv("SOLVER_TIMEOUT_SECONDS", "120")))


def _check_grid_size(ncol: int, nrow: int) -> None:
    total = ncol * nrow
    max_cells = _numerical_max_cells()
    if total > max_cells:
        raise ValueError(
            f"Grid too large: {ncol} x {nrow} = {total:,} cells exceeds the "
            f"{max_cells:,}-cell limit. Increase Delta X / Delta Z "
            "(or Delta Y for horizontal runs) to coarsen the grid."
        )


def _grid_points(length: float, count: int) -> np.ndarray:
    return np.linspace(0.0, float(length), int(count))


def _horizontal_plume_length_from_flopy(gwf, concentration: np.ndarray, c0: float) -> float:
    finite = concentration[np.isfinite(concentration)]
    if not finite.size or not (float(np.nanmin(finite)) < c0 < float(np.nanmax(finite))):
        return 0.0
    fig, ax = plt.subplots()
    try:
        pmv = flopy.plot.PlotMapView(model=gwf, layer=0, ax=ax)
        cs = pmv.contour_array(concentration, levels=[c0], colors="k")
        xs = [pt[0] for seg in cs.allsegs[0] for pt in seg]
        return float(max(xs)) if xs else 0.0
    finally:
        plt.close(fig)


def _vertical_plume_length_by_mask(concentration: np.ndarray, delr: float, c0: float) -> float:
    mask = concentration >= c0
    if not np.any(mask):
        return 0.0
    return float(np.max(np.where(mask)[2]) * delr)


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
    Lx: float,
    A_W: float,
    Sw: float,
    ncol: int,
    nrow: int,
    prsity: float,
    al: float,
    alpha_Th: float,
    gamma: float,
    cd: float,
    ca: float,
    h1: float,
    h2: float,
    hk: float,
    perlen: float = 100.0,
    plume_threshold: float | None = None,
    source_col_index: int = 5,
) -> HorizontalModelResult:
    """Plan-view (horizontal) 2-D reactive transport using MODFLOW 6 / GWT.

    Grid: nlay=1, nrow=y-transverse, ncol=x-flow.
    Source: strip of width Sw centred in y at column source_col_index.
    Top and bottom rows: ambient reactant (Ca) fixed along full domain.
    """
    if flopy is None:
        raise RuntimeError("flopy is not installed.")
    if min(Lx, A_W, Sw, prsity, al, alpha_Th, hk, perlen) <= 0:
        raise ValueError("Lx, A_W, Sw, prsity, al, alpha_Th, hk, and perlen must be positive.")
    if ncol < 2 or nrow < 2:
        raise ValueError("ncol and nrow must be at least 2.")
    _log_grid("Horizontal", Lx, A_W, ncol, nrow)
    _check_grid_size(ncol, nrow)
    if Sw >= A_W:
        raise ValueError("Source width Sw must be less than domain width A_W.")

    with _timed_stage("Horizontal executable resolution"):
        mf6 = _mf6_exe()
    nlay = 1
    delr = Lx / ncol        # x cell size
    delc = A_W / nrow       # y cell size
    nts = _nstp(Lx, ncol, prsity, al, h1, h2, hk, perlen)
    c0 = plume_threshold if plume_threshold is not None else 8.0

    run_root = Path.cwd() / ".numerical_runs"
    run_root.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(dir=run_root) as tmpdir:
        workdir = Path(tmpdir)
        mid = workdir.name.replace("-", "_")[:6]
        flow_name = f"gwf{mid}"
        gwf_ws = workdir / "gwf_base"

        # ── Flow model ──────────────────────────────────────────────────────────
        sim = flopy.mf6.MFSimulation(sim_name=flow_name, sim_ws=str(gwf_ws), exe_name=mf6)
        flopy.mf6.ModflowTdis(sim, perioddata=[[perlen, nts, 1.0]])
        flopy.mf6.ModflowIms(
            sim, print_option="SUMMARY", complexity="SIMPLE",
            outer_dvclose=1e-3, inner_dvclose=1e-3,
            outer_maximum=100, inner_maximum=200, relaxation_factor=0.97,
        )
        gwf = flopy.mf6.ModflowGwf(sim, modelname=flow_name)
        flopy.mf6.ModflowGwfdis(
            gwf, nlay=nlay, nrow=nrow, ncol=ncol,
            delr=delr, delc=delc, top=0.0, botm=-1.0,
        )
        chd_cells = [[(0, row, 0), h1] for row in range(nrow)] + \
                    [[(0, row, ncol - 1), h2] for row in range(nrow)]
        flopy.mf6.ModflowGwfchd(gwf, stress_period_data={0: chd_cells})
        strt = np.full((nlay, nrow, ncol), (h1 + h2) / 2.0, dtype=np.float32)
        strt[:, :, 0] = h1
        strt[:, :, -1] = h2
        flopy.mf6.ModflowGwfic(gwf, strt=strt)
        flopy.mf6.ModflowGwfnpf(
            gwf, save_specific_discharge=True, save_saturation=True, icelltype=0, k=hk,
        )
        flopy.mf6.ModflowGwfoc(
            gwf,
            budget_filerecord=f"{flow_name}.cbc",
            head_filerecord=f"{flow_name}.hds",
            saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
        )
        gwf.name_file.save_flows = True
        with _timed_stage("MF6 horizontal flow write_input"):
            sim.write_simulation()
        _checked_run_sim(sim, "MF6 horizontal flow")

        # ── Transport model ─────────────────────────────────────────────────────
        sim_name = f"gwt{mid}"
        run_name = f"tr{mid}"
        run_dir = workdir / "transport"
        simf = flopy.mf6.MFSimulation(sim_name=sim_name, sim_ws=str(run_dir), exe_name=mf6)
        flopy.mf6.ModflowTdis(simf, perioddata=[[perlen, nts, 1.0]])
        gwt = flopy.mf6.ModflowGwt(simf, modelname=run_name, save_flows=True)
        flopy.mf6.ModflowIms(simf, linear_acceleration="bicgstab")
        flopy.mf6.ModflowGwtdis(
            gwt, nlay=nlay, nrow=nrow, ncol=ncol,
            delr=delr, delc=delc, top=0.0, botm=-1.0,
        )
        flopy.mf6.ModflowGwtic(gwt, strt=np.full((nlay, nrow, ncol), ca, dtype=np.float32))
        flopy.mf6.ModflowGwtmst(gwt, porosity=prsity)
        flopy.mf6.ModflowGwtadv(gwt, scheme="TVD")
        flopy.mf6.ModflowGwtdsp(gwt, alh=np.full((nlay, nrow, ncol), al), ath1=alpha_Th)
        flopy.mf6.ModflowGwtssm(gwt)

        n_src = int(np.round(Sw / delc))
        if n_src < 1:
            raise ValueError("Horizontal source width is smaller than one row.")
        ci = nrow // 2
        half = n_src // 2
        if n_src % 2 == 0:
            s_start = ci - half
            s_end = ci + half
        else:
            s_start = ci - half
            s_end = ci + half + 1
        if s_start < 0 or s_end > nrow:
            raise ValueError("Horizontal source width must fit within Ly.")
        src_col = int(source_col_index)
        if src_col < 0 or src_col >= ncol:
            raise ValueError("Horizontal source column index must fit within ncol.")
        source_conc = (gamma * cd) + (2.0 * ca)

        cnc_cells = []
        for row in range(s_start, s_end):
            cnc_cells.append(((0, row, src_col), source_conc))
        for col in range(ncol):
            cnc_cells.append(((0, 0, col), ca))
        for col in range(ncol):
            cnc_cells.append(((0, nrow - 1, col), ca))

        flopy.mf6.ModflowGwtcnc(gwt, stress_period_data={0: cnc_cells}, filename=f"{run_name}.cnc")
        flopy.mf6.ModflowGwtfmi(
            gwt,
            packagedata=[
                ("GWFHEAD", str(gwf_ws / f"{flow_name}.hds")),
                ("GWFBUDGET", str(gwf_ws / f"{flow_name}.cbc")),
            ],
        )
        flopy.mf6.ModflowGwtoc(
            gwt,
            budget_filerecord=f"{sim_name}_gwt.cbc",
            concentration_filerecord=f"{sim_name}.ucn",
            saverecord=[("CONCENTRATION", "ALL"), ("BUDGET", "ALL")],
        )
        with _timed_stage("MF6 horizontal transport write_input"):
            simf.write_simulation()
        _checked_run_sim(simf, "MF6 horizontal transport")

        ucn_path = run_dir / f"{sim_name}.ucn"
        with _timed_stage("MF6 horizontal UCN read"):
            logger.info("MF6 horizontal UCN output: %s (exists=%s)", ucn_path.resolve(), ucn_path.exists())
            conc_slice = np.asarray(gwt.output.concentration().get_data()[0], dtype=float)
        x_grid = _grid_points(Lx, ncol)
        y_grid = _grid_points(A_W, nrow)
        with _timed_stage("MF6 horizontal plume-length extraction"):
            plume_length = _horizontal_plume_length_from_flopy(gwf, conc_slice, c0)
            logger.info("MF6 horizontal plume_length=%.6f m", plume_length)

        # Matplotlib figure for PDF export
        plot_png = b""
        try:
            with _timed_stage("MF6 horizontal contour build"):
                fig, ax = plt.subplots(figsize=(11, 4))
                mesh = ax.pcolormesh(x_grid, y_grid, conc_slice, shading="auto", cmap="jet")
                fin = conc_slice[np.isfinite(conc_slice)]
                if fin.size and float(np.nanmin(fin)) < c0 < float(np.nanmax(fin)):
                    ax.contour(x_grid, y_grid, conc_slice, levels=[c0], colors=["#163c66"], linewidths=2.0)
                fig.colorbar(mesh, ax=ax, label="Concentration [mg/L]")
                if plume_length > 0:
                    ax.axvline(plume_length, color="navy", linestyle="--", linewidth=1.5,
                               label=f"Lmax = {plume_length:.1f} m")
                    ax.legend(fontsize=8)
                ax.set_xlabel("Distance Lx [m]")
                ax.set_ylabel("Horizontal Width [m]")
                ax.set_title("Contaminant Plume — Horizontal Model (Plan View)")
                plt.tight_layout()
                buf = io.BytesIO()
                plt.savefig(buf, format="png", bbox_inches="tight", dpi=150)
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
    )


def run_numerical_model(
    Lx: float,
    Ly: float,
    ncol: int,
    nrow: int,
    prsity: float,
    al: float,
    av: float,
    gamma: float,
    cd: float,
    ca: float,
    h1: float,
    h2: float,
    hk: float,
    vk: float | None = None,
    source_thickness: float | None = None,
    source_bottom_buffer: float = 0.0,
    perlen: float = 100.0,
    plume_threshold: float | None = None,
    ath: float | None = None,
    source_col_index: int = 5,
) -> NumericalModelResult:
    """Vertical cross-section reactive transport using MODFLOW 6 / GWT.

    Grid: nlay=nrow (vertical layers), model_nrow=1, ncol=x-columns.  The
    source and plume-length calculation intentionally match Orlando's
    validated vertical script.
    """
    if flopy is None:
        raise RuntimeError("flopy is not installed.")
    if ath is None:
        ath = av
    if min(Lx, Ly, prsity, al, ath, hk, perlen) <= 0:
        raise ValueError("All positive parameters must be > 0.")
    if ncol < 2 or nrow < 2:
        raise ValueError("ncol and nrow must be at least 2.")
    if int(source_col_index) < 0 or int(source_col_index) >= ncol:
        raise ValueError("Vertical source column index must fit within ncol.")
    _log_grid("Vertical", Lx, Ly, ncol, nrow)
    _check_grid_size(ncol, nrow)

    with _timed_stage("Vertical executable resolution"):
        mf6 = _mf6_exe()
    nlay = int(nrow)
    model_nrow = 1
    delr = Lx / ncol
    delv = Ly / nlay
    botm = np.linspace(-delv, -Ly, nlay)
    nts = _nstp(Lx, ncol, prsity, al, h1, h2, hk, perlen)
    c0 = plume_threshold if plume_threshold is not None else 8.0

    run_root = Path.cwd() / ".numerical_runs"
    run_root.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(dir=run_root) as tmpdir:
        workdir = Path(tmpdir)
        mid = workdir.name.replace("-", "_")[:6]
        flow_name = f"gwf{mid}"
        gwf_ws = workdir / "gwf_base"

        # ── Flow model ──────────────────────────────────────────────────────────
        sim = flopy.mf6.MFSimulation(sim_name=flow_name, sim_ws=str(gwf_ws), exe_name=mf6)
        flopy.mf6.ModflowTdis(sim, perioddata=[[perlen, nts, 1.0]])
        flopy.mf6.ModflowIms(
            sim, print_option="SUMMARY", complexity="SIMPLE",
            outer_dvclose=1e-3, inner_dvclose=1e-3,
            outer_maximum=100, inner_maximum=200, relaxation_factor=0.97,
        )
        gwf = flopy.mf6.ModflowGwf(sim, modelname=flow_name)
        flopy.mf6.ModflowGwfdis(
            gwf, nlay=nlay, nrow=model_nrow, ncol=ncol,
            delr=delr, delc=1.0, top=0.0, botm=botm,
        )
        chd_cells = [[(lay, 0, 0), h1] for lay in range(nlay)] + \
                    [[(lay, 0, ncol - 1), h2] for lay in range(nlay)]
        flopy.mf6.ModflowGwfchd(gwf, stress_period_data={0: chd_cells})
        strt = np.full((nlay, model_nrow, ncol), (h1 + h2) / 2.0, dtype=np.float32)
        strt[:, :, 0] = h1
        strt[:, :, -1] = h2
        flopy.mf6.ModflowGwfic(gwf, strt=strt)
        flopy.mf6.ModflowGwfnpf(
            gwf, save_specific_discharge=True, save_saturation=True,
            icelltype=0, k=hk,
        )
        flopy.mf6.ModflowGwfoc(
            gwf,
            budget_filerecord=f"{flow_name}.cbc",
            head_filerecord=f"{flow_name}.hds",
            saverecord=[("HEAD", "ALL"), ("BUDGET", "ALL")],
        )
        gwf.name_file.save_flows = True
        with _timed_stage("MF6 vertical flow write_input"):
            sim.write_simulation()
        _checked_run_sim(sim, "MF6 vertical flow")

        # ── Transport model ─────────────────────────────────────────────────────
        sim_name = f"gwt{mid}"
        run_name = f"tr{mid}"
        run_dir = workdir / "transport"
        simf = flopy.mf6.MFSimulation(sim_name=sim_name, sim_ws=str(run_dir), exe_name=mf6)
        flopy.mf6.ModflowTdis(simf, perioddata=[[perlen, nts, 1.0]])
        gwt = flopy.mf6.ModflowGwt(simf, modelname=run_name, save_flows=True)
        flopy.mf6.ModflowIms(simf, linear_acceleration="bicgstab")
        flopy.mf6.ModflowGwtdis(
            gwt, nlay=nlay, nrow=model_nrow, ncol=ncol,
            delr=delr, delc=1.0, top=0.0, botm=botm,
        )
        flopy.mf6.ModflowGwtic(gwt, strt=np.full((nlay, model_nrow, ncol), ca, dtype=np.float32))
        flopy.mf6.ModflowGwtmst(gwt, porosity=prsity)
        flopy.mf6.ModflowGwtadv(gwt, scheme="TVD")
        flopy.mf6.ModflowGwtdsp(
            gwt,
            alh=np.full((nlay, model_nrow, ncol), al),
            ath1=ath,
        )
        flopy.mf6.ModflowGwtssm(gwt)

        source_conc = (gamma * cd) + ca
        src_col = int(source_col_index)
        cnc_cells = []
        for lay in range(1, nlay):
            cnc_cells.append(((lay, 0, src_col), source_conc))
        for col in range(ncol):
            cnc_cells.append(((0, 0, col), ca))

        flopy.mf6.ModflowGwtcnc(gwt, stress_period_data={0: cnc_cells}, filename=f"{run_name}.cnc")
        flopy.mf6.ModflowGwtfmi(
            gwt,
            packagedata=[
                ("GWFHEAD", str(gwf_ws / f"{flow_name}.hds")),
                ("GWFBUDGET", str(gwf_ws / f"{flow_name}.cbc")),
            ],
        )
        flopy.mf6.ModflowGwtoc(
            gwt,
            budget_filerecord=f"{sim_name}_gwt.cbc",
            concentration_filerecord=f"{sim_name}.ucn",
            saverecord=[("CONCENTRATION", "ALL"), ("BUDGET", "ALL")],
        )
        with _timed_stage("MF6 vertical transport write_input"):
            simf.write_simulation()
        _checked_run_sim(simf, "MF6 vertical transport")

        ucn_path = run_dir / f"{sim_name}.ucn"
        with _timed_stage("MF6 vertical UCN read"):
            logger.info("MF6 vertical UCN output: %s (exists=%s)", ucn_path.resolve(), ucn_path.exists())
            conc = np.asarray(gwt.output.concentration().get_data(), dtype=float)
            conc_slice = conc[:, 0, :]
        x_grid = _grid_points(Lx, ncol)
        z_grid = _grid_points(Ly, nlay)
        with _timed_stage("MF6 vertical plume-length extraction"):
            plume_length = _vertical_plume_length_by_mask(conc, delr, c0)
            logger.info("MF6 vertical plume_length=%.6f m", plume_length)

        with _timed_stage("MF6 vertical contour build"):
            fig, ax = plt.subplots(figsize=(11, 5))
            mesh = ax.pcolormesh(x_grid, z_grid, conc_slice, shading="auto", cmap="jet")
            fin = conc_slice[np.isfinite(conc_slice)]
            if fin.size and float(np.nanmin(fin)) < c0 < float(np.nanmax(fin)):
                ax.contour(x_grid, z_grid, conc_slice, levels=[c0], colors=["#163c66"], linewidths=2.0)
            fig.colorbar(mesh, ax=ax, label="Concentration [mg/L]")
            ax.set_xlabel("Distance Lx [m]")
            ax.set_ylabel("Aquifer Thickness [m]")
            ax.set_title("Contaminant Plume — Vertical Model")
            plt.tight_layout()
            img = io.BytesIO()
            fig.savefig(img, format="png", bbox_inches="tight", dpi=150)
            plt.close(fig)
            plot_bytes = img.getvalue()
            plot_url = base64.b64encode(plot_bytes).decode()

    return NumericalModelResult(
        plume_length=plume_length,
        plot_html=f'<img src="data:image/png;base64,{plot_url}" alt="Numerical plume plot" style="width:100%;height:auto;border-radius:12px;" />',
        concentration=conc_slice,
        x_grid=x_grid,
        z_grid=z_grid,
        plot_png=plot_bytes,
    )


def numerical_model(
    Lx: float,
    Ly: float,
    ncol: int,
    nrow: int,
    prsity: float,
    al: float,
    av: float,
    gamma: float,
    cd: float,
    ca: float,
    h1: float,
    h2: float,
    hk: float,
) -> tuple[float, str]:
    result = run_numerical_model(Lx, Ly, ncol, nrow, prsity, al, av, gamma, cd, ca, h1, h2, hk)
    return result.plume_length, result.plot_html
