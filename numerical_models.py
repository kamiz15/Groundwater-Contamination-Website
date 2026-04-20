from __future__ import annotations

import base64
import io
import os
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

try:
    import flopy
except Exception:  # pragma: no cover - dependency may not be installed locally
    flopy = None


@dataclass(frozen=True)
class NumericalModelResult:
    plume_length: float
    plot_html: str
    concentration: np.ndarray
    x_grid: np.ndarray
    z_grid: np.ndarray


@dataclass(frozen=True)
class HorizontalModelResult:
    plume_length: float
    concentration: np.ndarray
    x_grid: np.ndarray
    y_grid: np.ndarray


def _read_fortran_record(handle) -> bytes | None:
    """Read one sequential-unformatted Fortran record."""
    size_bytes = handle.read(4)
    if not size_bytes:
        return None
    if len(size_bytes) != 4:
        raise RuntimeError("Unexpected end of file while reading Fortran record length.")

    (record_size,) = struct.unpack("<i", size_bytes)
    payload = handle.read(record_size)
    if len(payload) != record_size:
        raise RuntimeError("Unexpected end of file while reading Fortran record payload.")

    end_size_bytes = handle.read(4)
    if len(end_size_bytes) != 4:
        raise RuntimeError("Unexpected end of file while reading Fortran record terminator.")

    (end_record_size,) = struct.unpack("<i", end_size_bytes)
    if end_record_size != record_size:
        raise RuntimeError("Corrupt Fortran record: length prefix/suffix mismatch.")

    return payload


def _parse_mt3d_header(header_payload: bytes) -> tuple[float, str, int, int, int, np.dtype]:
    if len(header_payload) == 44:
        ntrans, kstp, kper, totim = struct.unpack("<3if", header_payload[:16])
        text = header_payload[16:32].decode("ascii", "ignore").strip()
        ncol_hdr, nrow_hdr, ilay_hdr = struct.unpack("<3i", header_payload[32:44])
        precision = np.dtype(np.float32)
    elif len(header_payload) == 48:
        ntrans, kstp, kper = struct.unpack("<3i", header_payload[:12])
        (totim,) = struct.unpack("<d", header_payload[12:20])
        text = header_payload[20:36].decode("ascii", "ignore").strip()
        ncol_hdr, nrow_hdr, ilay_hdr = struct.unpack("<3i", header_payload[36:48])
        precision = np.dtype(np.float64)
    else:
        raise RuntimeError(f"Unsupported MT3DMS concentration header size {len(header_payload)} bytes.")

    return float(totim), text, int(ncol_hdr), int(nrow_hdr), int(ilay_hdr), precision


def _read_mt3d_concentration(ucn_path: Path, nlay: int, nrow: int, ncol: int) -> np.ndarray:
    """
    Read MT3DMS concentration output written as sequential-unformatted Fortran records.

    FloPy's UcnFile reader can fail against some MT3DMS builds even when the output is
    otherwise valid. This parser handles the standard UCN header/data record pairs and
    returns the latest concentration cube as (nlay, nrow, ncol).
    """
    latest_by_layer: dict[int, np.ndarray] = {}
    latest_totim: float | None = None
    cell_count = nrow * ncol

    def add_record(header_payload: bytes, data_payload: bytes) -> None:
        nonlocal latest_totim, latest_by_layer
        totim, text, ncol_hdr, nrow_hdr, ilay_hdr, precision = _parse_mt3d_header(header_payload)

        if ncol_hdr != ncol or nrow_hdr != nrow:
            raise RuntimeError(
                f"Unexpected MT3DMS concentration shape ({nrow_hdr}, {ncol_hdr}); "
                f"expected ({nrow}, {ncol})."
            )

        if text.upper() != "CONCENTRATION":
            return

        values = np.frombuffer(data_payload, dtype=precision)
        if values.size != cell_count:
            raise RuntimeError(
                f"Unexpected MT3DMS concentration payload size {values.size}; expected {cell_count}."
            )

        current_array = values.reshape((nrow, ncol)).astype(np.float64, copy=False)
        if latest_totim is None or totim > latest_totim:
            latest_totim = totim
            latest_by_layer = {ilay_hdr: current_array}
        elif np.isclose(totim, latest_totim):
            latest_by_layer[ilay_hdr] = current_array

    def read_fortran_stream() -> None:
        with ucn_path.open("rb") as handle:
            while True:
                header_payload = _read_fortran_record(handle)
                if header_payload is None:
                    break
                data_payload = _read_fortran_record(handle)
                if data_payload is None:
                    raise RuntimeError("Incomplete MT3DMS concentration output: missing data record.")
                add_record(header_payload, data_payload)

    def read_raw_stream() -> None:
        data = ucn_path.read_bytes()
        offset = 0
        total = len(data)
        while offset < total:
            parsed = False
            for header_size, precision in ((44, np.dtype(np.float32)), (48, np.dtype(np.float64))):
                data_size = cell_count * precision.itemsize
                if offset + header_size + data_size > total:
                    continue
                header_payload = data[offset:offset + header_size]
                try:
                    _totim, text, ncol_hdr, nrow_hdr, _ilay_hdr, parsed_precision = _parse_mt3d_header(header_payload)
                except RuntimeError:
                    continue
                if parsed_precision != precision:
                    continue
                if text.upper() != "CONCENTRATION" or ncol_hdr != ncol or nrow_hdr != nrow:
                    continue
                data_start = offset + header_size
                data_payload = data[data_start:data_start + data_size]
                add_record(header_payload, data_payload)
                offset = data_start + data_size
                parsed = True
                break
            if not parsed:
                raise RuntimeError(
                    "Unsupported MT3DMS concentration output format. "
                    "Expected raw UCN records or sequential-unformatted Fortran records."
                )

    first_word = struct.unpack("<i", ucn_path.read_bytes()[:4])[0]
    if first_word in {44, 48}:
        try:
            read_fortran_stream()
        except RuntimeError as exc:
            if "length prefix/suffix mismatch" not in str(exc):
                raise
            latest_by_layer = {}
            latest_totim = None
            read_raw_stream()
    else:
        read_raw_stream()

    if latest_totim is None or not latest_by_layer:
        raise RuntimeError("MT3DMS concentration output did not contain any concentration records.")

    concentration = np.zeros((nlay, nrow, ncol), dtype=np.float64)
    for layer_index, layer_data in latest_by_layer.items():
        if 1 <= layer_index <= nlay:
            concentration[layer_index - 1] = layer_data

    return concentration


def _resolve_executable(env_name: str, fallback_names: list[str]) -> str:
    configured = os.getenv(env_name)
    if configured and Path(configured).exists():
        configured_path = Path(configured)
        if os.name != "nt" and configured_path.suffix.lower() == ".exe":
            raise RuntimeError(
                f"{env_name} points to a Windows executable ({configured_path.name}), "
                "which cannot run inside Docker/Linux. Provide a Linux binary instead."
            )
        return configured

    local_dirs = [
        Path.cwd(),
        Path.cwd() / ".modflow_bin",
        Path.cwd() / "solvers",
        Path.cwd() / "bin",
    ]

    windows_only_candidates: list[str] = []

    for name in fallback_names:
        found = shutil.which(name)
        if found:
            found_path = Path(found)
            if os.name != "nt" and found_path.suffix.lower() == ".exe":
                windows_only_candidates.append(str(found_path))
                continue
            return found
        for directory in local_dirs:
            local = directory / name
            if local.exists():
                if os.name != "nt" and local.suffix.lower() == ".exe":
                    windows_only_candidates.append(str(local))
                    continue
                return str(local)

    if os.name != "nt" and windows_only_candidates:
        raise RuntimeError(
            f"Only Windows solver binaries were found for {env_name}: {windows_only_candidates}. "
            "Docker numerical runs require Linux solver binaries in solvers/ or on PATH."
        )

    raise RuntimeError(
        f"Missing required executable for {env_name}. "
        f"Set {env_name} or place one of {fallback_names} on PATH."
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
) -> NumericalModelResult:
    if flopy is None:
        raise RuntimeError("flopy is not installed. Install flopy to run the numerical model.")

    if min(Lx, Ly, prsity, al, hk) <= 0:
        raise ValueError("Lx, Ly, prsity, al, and hk must be positive.")
    if ncol < 2 or nrow < 2:
        raise ValueError("ncol and nrow must both be at least 2.")

    mf_exe = _resolve_executable("MF2005_EXE", ["mf2005.exe", "mf2005"])
    mt_exe = _resolve_executable("MT3DMS_EXE", ["mt3dms.exe", "mt3dms"])

    run_root = Path.cwd() / ".numerical_runs"
    run_root.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(dir=run_root) as tmpdir:
        workdir = Path(tmpdir)

        ztop = 0.0
        zbot = -1.0
        nlay = 1
        delx = Lx / ncol
        dely = Ly / nrow
        delv = (ztop - zbot) / nlay
        perlen = 6000.0

        model_id = workdir.name.replace("-", "_")

        t0_mf = f"T02_mf_{model_id}"
        mf = flopy.modflow.Modflow(modelname=t0_mf, exe_name=mf_exe, model_ws=str(workdir))
        flopy.modflow.ModflowDis(
            mf,
            nlay=nlay,
            nrow=nrow,
            ncol=ncol,
            delr=delx,
            delc=dely,
            top=ztop,
            botm=[ztop - delv],
            perlen=perlen,
        )

        ibound = np.ones((nlay, nrow, ncol), dtype=np.int32)
        ibound[:, :, 0] = -1
        ibound[:, :, -1] = -1
        strt = np.ones((nlay, nrow, ncol), dtype=np.float32)
        strt[:, :, 0] = h1
        strt[:, :, -1] = h2

        flopy.modflow.ModflowBas(mf, ibound=ibound, strt=strt)
        flopy.modflow.ModflowLpf(mf, hk=hk, laytyp=0)
        flopy.modflow.ModflowGmg(mf)
        flopy.modflow.ModflowLmt(mf, output_file_format="formatted")

        mf.write_input()
        success, _ = mf.run_model(silent=True)
        if not success:
            raise RuntimeError("MODFLOW execution failed.")

        t0_mt = f"T02_mt_{model_id}"
        mt = flopy.mt3d.Mt3dms(
            modelname=t0_mt,
            exe_name=mt_exe,
            modflowmodel=mf,
            ftlfree=True,
            model_ws=str(workdir),
        )

        icbund = np.ones((nlay, nrow, ncol), dtype=np.int32)
        icbund[:, 0, :] = -1
        icbund[:, :, 0] = -1
        icbund[:, :, -1] = -1

        sconc = np.zeros((nlay, nrow, ncol), dtype=np.float32)
        sconc[:, 0, :] = ca
        sconc[:, :, 0] = (gamma * cd) + (2 * ca)
        sconc[:, :, -1] = ca

        flopy.mt3d.Mt3dBtn(mt, icbund=icbund, prsity=prsity, sconc=sconc)
        flopy.mt3d.Mt3dAdv(mt, mixelm=-1)
        trpt = av / al if al > 0 else 0.1
        flopy.mt3d.Mt3dDsp(mt, al=al, trpt=trpt)
        flopy.mt3d.Mt3dGcg(mt)
        flopy.mt3d.Mt3dSsm(mt)

        mt.write_input()
        success, buff = mt.run_model(silent=True, report=True)
        if (not success) and not any("Program completed" in str(line) for line in buff):
            raise RuntimeError("MT3DMS execution failed.")

        ucn_path = workdir / "MT3D001.UCN"
        if not ucn_path.exists():
            raise RuntimeError("MT3DMS did not produce MT3D001.UCN concentration output.")

        conc = _read_mt3d_concentration(ucn_path, nlay=nlay, nrow=nrow, ncol=ncol)
        conc_slice = conc[0]
        x_grid = np.linspace(0.0, Lx, ncol)
        z_grid = np.linspace(0.0, Ly, nrow)

        c0 = 2 * ca
        fig = plt.figure(figsize=(11, 5))
        ax = plt.axes()
        mm = flopy.plot.map.PlotMapView(ax=ax, model=mf)
        cs = mm.contour_array(conc_slice, levels=[c0], colors=["#163c66"], linewidths=2.0)
        plt.xlabel("Distance Lx [m]")
        plt.ylabel("Aquifer Thickness [m]")
        plt.title("Contaminant Plume")

        img = io.BytesIO()
        plt.savefig(img, format="png", bbox_inches="tight", dpi=300)
        plt.close(fig)
        img.seek(0)

        plot_url = base64.b64encode(img.getvalue()).decode()

        segments = cs.allsegs[0] if getattr(cs, "allsegs", None) else []
        if not segments or len(segments[0]) == 0:
            plume_length = 0.0
        else:
            plume_length = float(np.max(np.asarray(segments[0])[:, 0]))

    return NumericalModelResult(
        plume_length=plume_length,
        plot_html=f'<img src="data:image/png;base64,{plot_url}" alt="Numerical plume plot" style="width:100%;height:auto;border-radius:12px;" />',
        concentration=conc_slice,
        x_grid=x_grid,
        z_grid=z_grid,
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
) -> Tuple[float, str]:
    result = run_numerical_model(Lx, Ly, ncol, nrow, prsity, al, av, gamma, cd, ca, h1, h2, hk)
    return result.plume_length, result.plot_html


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
) -> HorizontalModelResult:
    """
    Plan-view (horizontal) 2-D reactive transport model using MODFLOW/MT3DMS.

    Grid orientation:
      - Columns (ncol): flow direction x (left=inflow h1, right=outflow h2)
      - Rows (nrow):    horizontal transverse direction y (0=bottom, nrow-1=top)

    Source: strip of width Sw centred in y at the left (x=0) boundary.
    Ambient reactant at concentration ca enters at top/bottom y-boundaries.
    """
    if flopy is None:
        raise RuntimeError("flopy is not installed. Install flopy to run the numerical model.")
    if min(Lx, A_W, prsity, al, hk) <= 0:
        raise ValueError("Lx, A_W, prsity, al, hk must all be positive.")
    if ncol < 2 or nrow < 2:
        raise ValueError("ncol and nrow must both be at least 2.")
    if Sw <= 0 or Sw >= A_W:
        raise ValueError("Source width Sw must be positive and less than domain width A_W.")

    mf_exe = _resolve_executable("MF2005_EXE", ["mf2005.exe", "mf2005"])
    mt_exe = _resolve_executable("MT3DMS_EXE", ["mt3dms.exe", "mt3dms"])

    run_root = Path.cwd() / ".numerical_runs"
    run_root.mkdir(exist_ok=True)

    with tempfile.TemporaryDirectory(dir=run_root) as tmpdir:
        workdir = Path(tmpdir)

        ztop = 0.0
        zbot = -1.0
        nlay = 1
        delx = Lx / ncol
        dely = A_W / nrow
        delv = ztop - zbot
        perlen = 6000.0

        model_id = workdir.name.replace("-", "_")

        t0_mf = f"T03_mf_{model_id}"
        mf = flopy.modflow.Modflow(modelname=t0_mf, exe_name=mf_exe, model_ws=str(workdir))
        flopy.modflow.ModflowDis(
            mf, nlay=nlay, nrow=nrow, ncol=ncol,
            delr=delx, delc=dely,
            top=ztop, botm=[ztop - delv],
            perlen=perlen,
        )

        # Left/right columns = specified head; top/bottom rows = active (no-flow)
        ibound = np.ones((nlay, nrow, ncol), dtype=np.int32)
        ibound[:, :, 0] = -1
        ibound[:, :, -1] = -1

        strt = np.full((nlay, nrow, ncol), (h1 + h2) / 2.0, dtype=np.float32)
        strt[:, :, 0] = h1
        strt[:, :, -1] = h2

        flopy.modflow.ModflowBas(mf, ibound=ibound, strt=strt)
        flopy.modflow.ModflowLpf(mf, hk=hk, laytyp=0)
        flopy.modflow.ModflowGmg(mf)
        flopy.modflow.ModflowLmt(mf, output_file_format="formatted")

        mf.write_input()
        success, _ = mf.run_model(silent=True)
        if not success:
            raise RuntimeError("MODFLOW (horizontal) execution failed.")

        # --- MT3DMS ---
        t0_mt = f"T03_mt_{model_id}"
        mt = flopy.mt3d.Mt3dms(
            modelname=t0_mt, exe_name=mt_exe,
            modflowmodel=mf, ftlfree=True,
            model_ws=str(workdir),
        )

        # Source strip centred in the y-domain
        source_row_start = max(0, int(np.floor((A_W - Sw) / 2.0 / dely)))
        source_row_end = min(nrow - 1, int(np.ceil((A_W + Sw) / 2.0 / dely)))

        icbund = np.ones((nlay, nrow, ncol), dtype=np.int32)
        icbund[:, :, 0] = -1
        icbund[:, :, -1] = -1
        icbund[:, 0, :] = -1
        icbund[:, -1, :] = -1

        sconc = np.full((nlay, nrow, ncol), ca, dtype=np.float32)
        sconc[:, source_row_start:source_row_end + 1, 0] = float(gamma * cd) + 2.0 * float(ca)
        sconc[:, :, -1] = ca
        sconc[:, 0, :] = ca
        sconc[:, -1, :] = ca

        flopy.mt3d.Mt3dBtn(mt, icbund=icbund, prsity=prsity, sconc=sconc)
        flopy.mt3d.Mt3dAdv(mt, mixelm=-1)
        trpt = alpha_Th / al if al > 0 else 0.1
        flopy.mt3d.Mt3dDsp(mt, al=al, trpt=trpt)
        flopy.mt3d.Mt3dGcg(mt)
        flopy.mt3d.Mt3dSsm(mt)

        mt.write_input()
        success, buff = mt.run_model(silent=True, report=True)
        if (not success) and not any("Program completed" in str(line) for line in buff):
            raise RuntimeError("MT3DMS (horizontal) execution failed.")

        ucn_path = workdir / "MT3D001.UCN"
        if not ucn_path.exists():
            raise RuntimeError("MT3DMS (horizontal) did not produce MT3D001.UCN.")

        conc = _read_mt3d_concentration(ucn_path, nlay=nlay, nrow=nrow, ncol=ncol)
        conc_slice = conc[0]
        x_grid = np.linspace(0.0, Lx, ncol)
        y_grid = np.linspace(0.0, A_W, nrow)

        # Extract plume length from the c0 = 2*ca contour
        c0 = 2.0 * ca
        plume_length = 0.0
        try:
            fig_tmp, ax_tmp = plt.subplots()
            cs = ax_tmp.contour(x_grid, y_grid, conc_slice, levels=[c0])
            segs = cs.allsegs[0] if getattr(cs, "allsegs", None) else []
            if segs and len(segs[0]):
                plume_length = float(np.max(np.asarray(segs[0])[:, 0]))
            plt.close(fig_tmp)
        except Exception:
            plume_length = 0.0

    return HorizontalModelResult(
        plume_length=plume_length,
        concentration=conc_slice,
        x_grid=x_grid,
        y_grid=y_grid,
    )
