# Written by Alvin Yadav

"""
Export a solved concentration grid as tidy long-form CSV.

The simulation stores its field as three arrays — xaxis, yaxis and a 2D result
of shape (len(yaxis), len(xaxis)) — which is convenient for plotting and
useless to anything that expects one row per sample point. This module is the
bridge: it emits one (x, y, concentration) row per grid point, the layout the
project's data-analysis workbench consumes.

Two on-disk formats, one column contract (GRID_COLUMNS):

  * CSV  — long-form, one (x, y, concentration) row per grid point. Human- and
           spreadsheet-readable; the interoperability export.
  * NPZ  — the native grid (1D x axis, 1D y axis, 2D concentration array).
           Compact and lossless; the format the data-analysis workbench uses
           for round-tripping a run. Pure-numpy, no extra dependency.

Entry points, per format:
  * grid_to_rows    — CSV rows, for a caller that wants to reshape
  * grid_csv_bytes  — CSV in memory, for a download that should leave no file
  * write_grid_csv  — CSV on disk, replacing whatever was there atomically
  * grid_npz_bytes  — NPZ in memory
  * write_grid_npz  — NPZ on disk, atomic replace

The CSV path is deliberately stdlib-only (no pandas): pyproject.toml declares
numpy and matplotlib, and pulling in pandas to avoid one csv.writer would be a
bad trade. NPZ uses numpy, which is already a dependency.
"""

# Python std library:
import csv
import io
import logging
import os

# External imports:
import numpy as np

logger = logging.getLogger(__name__)

# The column names are a contract with the consuming data-analysis workbench,
# not a preference. Its notation module maps "concentration_mgL" to a typeset
# C [mg/L] axis label by stripping the trailing "mgl" unit token; rename these
# and the labels silently degrade to the raw column string. Keep them in sync
# with the workbench's sample_grid.csv.
GRID_COLUMNS = ("x_m", "y_m", "concentration_mgL")


def _validated(xaxis, yaxis, result, step):
    """
    Coerce the three arrays to float and apply ``step``, or raise ValueError.

    Returns (xs, ys, values) already decimated, with values still shaped
    (len(ys), len(xs)).
    """
    if not isinstance(step, (int, np.integer)) or isinstance(step, bool):
        raise ValueError(f"step must be an integer, got {step!r}.")
    if step < 1:
        raise ValueError(f"step must be at least 1 (1 = every point), got {step}.")

    xs = np.asarray(xaxis, dtype=float).ravel()
    ys = np.asarray(yaxis, dtype=float).ravel()
    values = np.asarray(result, dtype=float)

    if values.shape != (ys.size, xs.size):
        raise ValueError(
            f"Concentration grid has shape {values.shape}, but the axes imply "
            f"{(ys.size, xs.size)} (rows = y, columns = x)."
        )

    return xs[::step], ys[::step], values[::step, ::step]


def grid_to_rows(xaxis, yaxis, result, *, step=1):
    """
    Yield (x, y, concentration) tuples for every point of the grid.

    Rows are y-major: every x at the first y, then every x at the second y,
    and so on. That is the order the arrays already have — result[j][i] is the
    concentration at (xaxis[i], yaxis[j]) — so nothing is transposed here or
    downstream.

    :param xaxis: 1D array of x coordinates, as produced by conc_array.
    :param yaxis: 1D array of y coordinates.
    :param result: 2D array of shape (len(yaxis), len(xaxis)).
    :param step: keep every step-th point on both axes; 1 keeps everything.
                 Decimating both axes by the same factor keeps the sample
                 points on a regular lattice, which the workbench requires.
    :return: generator of (float, float, float) tuples.
    """
    xs, ys, values = _validated(xaxis, yaxis, result, step)

    # .tolist() converts to native Python floats in one pass. Their str() is
    # the shortest representation that round-trips, so the CSV keeps full
    # precision without us choosing a format string.
    x_values = xs.tolist()
    for y_value, row in zip(ys.tolist(), values.tolist()):
        for x_value, concentration in zip(x_values, row):
            yield (x_value, y_value, concentration)


def grid_csv_bytes(xaxis, yaxis, result, *, step=1) -> bytes:
    """
    Return the grid as UTF-8 encoded CSV, header included.

    For callers that want to hand the data straight to a download or an HTTP
    response without leaving a file behind. See grid_to_rows for the arguments.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(GRID_COLUMNS)
    writer.writerows(grid_to_rows(xaxis, yaxis, result, step=step))
    return buffer.getvalue().encode("utf-8")


def _atomic_write(path, write_fn) -> str:
    """
    Run ``write_fn(tmp_path)`` then atomically move the result onto ``path``.

    The payload is written to a sibling .tmp file and os.replace()d into
    position. Two things follow, both of which matter when a caller points
    every run at one fixed path (a "latest run" slot): a reader never observes
    a half-written file, and a run that dies mid-write leaves the previous
    complete file intact instead of a truncated one. Missing parent
    directories are created.

    :return: the path written to.
    """
    path = os.fspath(path)
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)

    # Same directory as the target, so os.replace() stays within one filesystem.
    tmp_path = path + ".tmp"
    try:
        write_fn(tmp_path)
        os.replace(tmp_path, path)
    except BaseException:
        # Leave the previous file (if any) untouched and don't strand the temp
        # file. Errors from the cleanup itself must not mask the real failure.
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    return path


def write_grid_csv(path, xaxis, yaxis, result, *, step=1) -> str:
    """
    Write the grid to ``path`` as long-form CSV, replacing any existing file
    atomically (see _atomic_write). Missing parent directories are created.

    :return: the path written to.
    """
    def _write(tmp_path):
        with open(tmp_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(GRID_COLUMNS)
            writer.writerows(grid_to_rows(xaxis, yaxis, result, step=step))

    written = _atomic_write(path, _write)
    logger.debug(f"Wrote concentration grid CSV to {written} (step={step}).")
    return written


def grid_npz_bytes(xaxis, yaxis, result, *, step=1, float32=False) -> bytes:
    """
    Return the grid as a compressed .npz archive, in memory.

    Unlike the CSV, this stores the *native* grid, not one row per point: the
    two 1D axes and the 2D concentration array, under the keys in GRID_COLUMNS
    (``x_m``, ``y_m`` are 1D; ``concentration_mgL`` is 2D, shape
    ``(len(y_m), len(x_m))``). A consumer rebuilds long-form with a meshgrid.

    :param float32: store the arrays as float32 (~7 significant figures, about
                    half the bytes). Default keeps full float64 precision.
    :return: the bytes of an .npz archive.
    """
    xs, ys, values = _validated(xaxis, yaxis, result, step)
    if float32:
        xs = xs.astype("float32")
        ys = ys.astype("float32")
        values = values.astype("float32")

    x_key, y_key, v_key = GRID_COLUMNS
    buffer = io.BytesIO()
    np.savez_compressed(buffer, **{x_key: xs, y_key: ys, v_key: values})
    return buffer.getvalue()


def write_grid_npz(path, xaxis, yaxis, result, *, step=1, float32=False) -> str:
    """
    Write the grid to ``path`` as a compressed .npz, replacing any existing
    file atomically (see _atomic_write). See grid_npz_bytes for the layout and
    the ``float32`` option. Missing parent directories are created.

    :return: the path written to.
    """
    payload = grid_npz_bytes(xaxis, yaxis, result, step=step, float32=float32)

    def _write(tmp_path):
        with open(tmp_path, "wb") as f:
            f.write(payload)

    written = _atomic_write(path, _write)
    logger.debug(f"Wrote concentration grid NPZ to {written} "
                 f"(step={step}, float32={float32}).")
    return written
