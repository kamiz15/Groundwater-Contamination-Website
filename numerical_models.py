from __future__ import annotations

import base64
import io
import os
import shutil
import struct
import tempfile
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

    with ucn_path.open("rb") as handle:
        while True:
            header_payload = _read_fortran_record(handle)
            if header_payload is None:
                break
            data_payload = _read_fortran_record(handle)
            if data_payload is None:
                raise RuntimeError("Incomplete MT3DMS concentration output: missing data record.")

            if len(header_payload) == 44:
                ntrans, kstp, kper, totim = struct.unpack("<3if", header_payload[:16])
                text = header_payload[16:32].decode("ascii", "ignore").strip()
                ncol_hdr, nrow_hdr, ilay_hdr = struct.unpack("<3i", header_payload[32:44])
                precision = np.float32
            elif len(header_payload) == 48:
                ntrans, kstp, kper = struct.unpack("<3i", header_payload[:12])
                (totim,) = struct.unpack("<d", header_payload[12:20])
                text = header_payload[20:36].decode("ascii", "ignore").strip()
                ncol_hdr, nrow_hdr, ilay_hdr = struct.unpack("<3i", header_payload[36:48])
                precision = np.float64
            else:
                raise RuntimeError(
                    f"Unsupported MT3DMS concentration header size {len(header_payload)} bytes."
                )

            if ncol_hdr != ncol or nrow_hdr != nrow:
                raise RuntimeError(
                    f"Unexpected MT3DMS concentration shape ({nrow_hdr}, {ncol_hdr}); "
                    f"expected ({nrow}, {ncol})."
                )

            if text.upper() != "CONCENTRATION":
                continue

            values = np.frombuffer(data_payload, dtype=precision)
            if values.size != cell_count:
                raise RuntimeError(
                    f"Unexpected MT3DMS concentration payload size {values.size}; expected {cell_count}."
                )

            current_totim = float(totim)
            current_layer = int(ilay_hdr)
            current_array = values.reshape((nrow, ncol)).astype(np.float64, copy=False)

            if latest_totim is None or current_totim > latest_totim:
                latest_totim = current_totim
                latest_by_layer = {current_layer: current_array}
            elif np.isclose(current_totim, latest_totim):
                latest_by_layer[current_layer] = current_array

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

        c0 = 2 * ca
        fig = plt.figure(figsize=(11, 5))
        ax = plt.axes()
        mm = flopy.plot.map.PlotMapView(ax=ax, model=mf)
        mm.plot_grid(color=".5", alpha=0.2)
        conc_slice = conc[0]
        cs = mm.contour_array(conc_slice, levels=[c0], colors=["#163c66"], linewidths=2.0)
        mm.plot_ibound()
        plt.xlabel("Distance Lx [m]")
        plt.ylabel("Aquifer Thickness [m]")
        plt.title("Contaminant Plume")

        img = io.BytesIO()
        plt.savefig(img, format="png", bbox_inches="tight", dpi=140)
        plt.close(fig)
        img.seek(0)

        plot_url = base64.b64encode(img.getvalue()).decode()

        segments = cs.allsegs[0] if getattr(cs, "allsegs", None) else []
        if not segments or len(segments[0]) == 0:
            plume_length = 0.0
        else:
            plume_length = float(np.max(np.asarray(segments[0])[:, 0]))

    return plume_length, f'<img src="data:image/png;base64,{plot_url}" alt="Numerical plume plot" style="width:100%;height:auto;border-radius:12px;" />'
