"""Convert MODFLOW 6 binary output into workbench-ready long-form CSV.

The site's numerical models run MODFLOW 6, which writes its results as binary
files rather than anything a spreadsheet can open:

  * ``*.hds``  hydraulic head      (one array per layer, per time step)
  * ``*.ucn``  solute concentration
  * ``*.cbc``  cell budgets / specific discharge

This module turns a chosen array into the same tidy ``x, y, value`` layout the
workbench's Scientific tab already consumes, so a head field can be contoured
exactly like a concentration field.

Note on geometry: MODFLOW's binary output stores only the value arrays, not the
cell sizes. Pass the domain extents (``--lx`` / ``--ly``) to get real metres —
matching ``numerical_models._grid_points`` (``linspace(0, length, count)``).
Without them the coordinates fall back to cell indices.

Command line::

    python -m data_analysis.modflow run.hds -o head.csv --lx 100 --ly 20
    python -m data_analysis.modflow run.ucn --kind concentration -o conc.csv
    python -m data_analysis.modflow run.hds --list      # show available times
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

# Which binary reader and value column each output kind maps to.
KINDS = {
    "head": {"text": "head", "column": "head_m"},
    "concentration": {"text": "concentration", "column": "concentration_mg_L"},
}


def _import_flopy():
    try:
        from flopy.utils import binaryfile
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ValueError(
            "Reading MODFLOW output requires the 'flopy' package. "
            "Install it with: pip install flopy"
        ) from exc
    return binaryfile


def _open(path: Path, kind: str):
    binaryfile = _import_flopy()
    if kind not in KINDS:
        raise ValueError(f"Unknown kind '{kind}'. Choose one of: {', '.join(KINDS)}.")
    if not Path(path).exists():
        raise ValueError(f"File not found: {path}")
    text = KINDS[kind]["text"]
    # MODFLOW 6 writes concentration in the same binary layout as head, so
    # HeadFile reads both provided the record text matches. MT3D-style UCN
    # files need the dedicated reader, so fall back to it.
    try:
        return binaryfile.HeadFile(str(path), text=text)
    except Exception:
        if kind == "concentration":
            return binaryfile.UcnFile(str(path))
        raise


def list_records(path, kind: str = "head") -> list:
    """Available (kstp, kper) time steps in the file."""
    f = _open(Path(path), kind)
    try:
        return list(f.get_kstpkper())
    finally:
        f.close()


def read_array(path, kind: str = "head", *, kstpkper=None, totim=None) -> np.ndarray:
    """Read one 3-D array ``(nlay, nrow, ncol)`` from a MODFLOW binary file.

    Defaults to the final time step, which is what the site's steady-state and
    end-of-simulation plots use.
    """
    f = _open(Path(path), kind)
    try:
        if totim is not None:
            data = f.get_data(totim=totim)
        elif kstpkper is not None:
            data = f.get_data(kstpkper=tuple(kstpkper))
        else:
            steps = f.get_kstpkper()
            if not steps:
                raise ValueError("The file contains no time steps.")
            data = f.get_data(kstpkper=steps[-1])
        return np.asarray(data, dtype=float)
    finally:
        f.close()


def _axis(length, count):
    """Coordinates along one axis: metres when a length is given, else indices."""
    if length is None:
        return np.arange(int(count), dtype=float)
    return np.linspace(0.0, float(length), int(count))


def to_long_form(
    array: np.ndarray,
    kind: str = "head",
    *,
    layer: int | None = None,
    row: int | None = None,
    lx: float | None = None,
    ly: float | None = None,
    drop_dry: bool = True,
) -> pd.DataFrame:
    """Flatten a MODFLOW array into ``x, y|z, value`` rows.

    Selects a 2-D slice first:
      * ``row`` given (or nrow == 1) -> vertical cross-section, axes x and z
      * otherwise a single ``layer`` -> plan view, axes x and y
    """
    arr = np.asarray(array, dtype=float)
    if arr.ndim == 2:
        arr = arr[np.newaxis, :, :]
    if arr.ndim != 3:
        raise ValueError(f"Expected a 2-D or 3-D array, got shape {arr.shape}.")
    nlay, nrow, ncol = arr.shape
    value_col = KINDS[kind]["column"]

    if row is not None or nrow == 1:
        # Cross-section down the layers: rows = z, columns = x.
        r = 0 if nrow == 1 else int(row)
        if not 0 <= r < nrow:
            raise ValueError(f"row {r} is outside 0..{nrow - 1}.")
        grid = arr[:, r, :]
        x = _axis(lx, ncol)
        cross = _axis(ly, nlay)
        cross_name = "z_m" if ly is not None else "layer"
    else:
        lay = 0 if layer is None else int(layer)
        if not 0 <= lay < nlay:
            raise ValueError(f"layer {lay} is outside 0..{nlay - 1}.")
        grid = arr[lay, :, :]
        x = _axis(lx, ncol)
        cross = _axis(ly, nrow)
        cross_name = "y_m" if ly is not None else "row"

    xx, cc = np.meshgrid(x, cross)
    df = pd.DataFrame({
        "x_m" if lx is not None else "col": xx.ravel(),
        cross_name: cc.ravel(),
        value_col: grid.ravel(),
    })
    if drop_dry:
        # MODFLOW marks dry/inactive cells with large sentinels (±1e30).
        df = df[np.abs(df[value_col]) < 1e29]
        df = df[np.isfinite(df[value_col])]
    return df.reset_index(drop=True)


def convert(
    path,
    output,
    kind: str = "head",
    *,
    layer: int | None = None,
    row: int | None = None,
    lx: float | None = None,
    ly: float | None = None,
    kstpkper=None,
    totim=None,
) -> pd.DataFrame:
    """Read a MODFLOW binary file and write long-form CSV to ``output``."""
    array = read_array(path, kind, kstpkper=kstpkper, totim=totim)
    df = to_long_form(array, kind, layer=layer, row=row, lx=lx, ly=ly)
    if df.empty:
        raise ValueError("No active cells to export (all cells were dry or inactive).")
    df.to_csv(output, index=False)
    return df


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m data_analysis.modflow",
        description="Convert MODFLOW 6 binary output (.hds/.ucn) to long-form CSV "
                    "for the Data Analysis Workbench.",
    )
    p.add_argument("input", help="MODFLOW binary file (.hds or .ucn)")
    p.add_argument("-o", "--output", help="Destination CSV (default: alongside the input)")
    p.add_argument("--kind", choices=sorted(KINDS), default="head",
                   help="Which quantity the file holds (default: head)")
    p.add_argument("--layer", type=int, help="Layer index for a plan view (default: 0)")
    p.add_argument("--row", type=int, help="Row index for a vertical cross-section")
    p.add_argument("--lx", type=float, help="Domain length in x (metres) for real coordinates")
    p.add_argument("--ly", type=float, help="Domain length in y/z (metres) for real coordinates")
    p.add_argument("--list", action="store_true", help="List available time steps and exit")
    args = p.parse_args(argv)

    try:
        if args.list:
            for step in list_records(args.input, args.kind):
                print(f"kstpkper={step}")
            return 0
        out = args.output or str(Path(args.input).with_suffix(f".{args.kind}.csv"))
        df = convert(args.input, out, args.kind, layer=args.layer, row=args.row,
                     lx=args.lx, ly=args.ly)
        print(f"Wrote {len(df)} rows to {out}")
        print(f"Columns: {', '.join(df.columns)}")
        return 0
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
