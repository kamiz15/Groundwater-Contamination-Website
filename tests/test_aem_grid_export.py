"""
Unit tests for aem/at_grid_export.py — the CSV and NPZ export of a solved
concentration grid — plus the concentration_output config validation.

These exercise only the array-to-file formats and config parsing, so they need
no solve and run instantly.

Vendored verbatim from the upstream AEM_Transport tree
(src/tests/test_grid_export.py); the only edit is the import prefix, because
here at_grid_export lives inside the ``aem`` package. Keep it that way so the
next upstream drop diffs cleanly.

Covers the producer side of the .npz contract; test_data_analysis_npz.py covers
the workbench's consumer side (datasets.load_npz).
"""
import csv
import io
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from aem import at_grid_export as gx
from aem.at_grid_export import GRID_COLUMNS
from aem.at_config import ATConfiguration


# ── Fixtures ─────────────────────────────────────────────────────────────

# A 3-row (y) by 4-column (x) grid. result[j][i] is the concentration at
# (xaxis[i], yaxis[j]); the value encodes its own coordinate index as j*10 + i
# so every cell's placement is checkable.
XAXIS = np.array([0.0, 1.0, 2.0, 3.0])
YAXIS = np.array([-5.0, 0.0, 5.0])
RESULT = np.array([
    [0.0, 1.0, 2.0, 3.0],      # y = -5
    [10.0, 11.0, 12.0, 13.0],  # y =  0
    [20.0, 21.0, 22.0, 23.0],  # y =  5
])


def _read_csv(data: bytes):
    reader = csv.reader(io.StringIO(data.decode("utf-8")))
    rows = list(reader)
    return rows[0], rows[1:]


def _load_npz(data: bytes):
    d = np.load(io.BytesIO(data))
    return d["x_m"], d["y_m"], d["concentration_mgL"]


# ── CSV: row generation ──────────────────────────────────────────────────

def test_rows_cover_every_cell_in_y_major_order():
    rows = list(gx.grid_to_rows(XAXIS, YAXIS, RESULT))
    assert len(rows) == XAXIS.size * YAXIS.size

    expected = []
    for j, y in enumerate(YAXIS):
        for i, x in enumerate(XAXIS):
            expected.append((x, y, RESULT[j][i]))
    assert rows == expected


def test_first_and_last_rows_have_the_right_coordinates():
    rows = list(gx.grid_to_rows(XAXIS, YAXIS, RESULT))
    assert rows[0] == (0.0, -5.0, 0.0)
    assert rows[-1] == (3.0, 5.0, 23.0)


# ── CSV: bytes ───────────────────────────────────────────────────────────

def test_csv_header_is_exactly_grid_columns():
    header, _ = _read_csv(gx.grid_csv_bytes(XAXIS, YAXIS, RESULT))
    assert tuple(header) == GRID_COLUMNS


def test_csv_row_count_matches_grid_size():
    _, body = _read_csv(gx.grid_csv_bytes(XAXIS, YAXIS, RESULT))
    assert len(body) == XAXIS.size * YAXIS.size


def test_csv_preserves_full_float_precision():
    xaxis = np.array([0.0, 1.0 / 3.0])
    yaxis = np.array([0.0])
    result = np.array([[0.1 + 0.2, 42.0]])
    _, body = _read_csv(gx.grid_csv_bytes(xaxis, yaxis, result))
    assert float(body[0][0]) == 0.0
    assert float(body[0][2]) == 0.1 + 0.2
    assert float(body[1][0]) == 1.0 / 3.0


# ── CSV: coarsening ──────────────────────────────────────────────────────

def test_step_selects_every_nth_point_on_both_axes():
    rows = list(gx.grid_to_rows(XAXIS, YAXIS, RESULT, step=2))
    assert rows == [
        (0.0, -5.0, 0.0), (2.0, -5.0, 2.0),
        (0.0, 5.0, 20.0), (2.0, 5.0, 22.0),
    ]


def test_step_keeps_axes_evenly_spaced():
    xaxis = np.arange(0.0, 10.0)
    yaxis = np.arange(0.0, 6.0)
    result = np.zeros((yaxis.size, xaxis.size))
    rows = list(gx.grid_to_rows(xaxis, yaxis, result, step=3))
    xs = sorted({r[0] for r in rows})
    ys = sorted({r[1] for r in rows})
    assert np.allclose(np.diff(xs), 3.0)
    assert np.allclose(np.diff(ys), 3.0)


# ── Validation (shared _validated path) ──────────────────────────────────

def test_shape_mismatch_raises():
    bad = np.zeros((YAXIS.size, XAXIS.size + 1))
    with pytest.raises(ValueError, match="grid has shape"):
        list(gx.grid_to_rows(XAXIS, YAXIS, bad))


@pytest.mark.parametrize("step", [0, -1])
def test_step_below_one_raises(step):
    with pytest.raises(ValueError, match="at least 1"):
        list(gx.grid_to_rows(XAXIS, YAXIS, RESULT, step=step))


def test_non_integer_step_raises():
    with pytest.raises(ValueError, match="integer"):
        list(gx.grid_to_rows(XAXIS, YAXIS, RESULT, step=1.5))


# ── CSV: atomic file write ───────────────────────────────────────────────

def test_write_creates_file_with_expected_contents(tmp_path):
    path = tmp_path / "grid.csv"
    returned = gx.write_grid_csv(path, XAXIS, YAXIS, RESULT)
    assert returned == str(path)
    header, body = _read_csv(path.read_bytes())
    assert tuple(header) == GRID_COLUMNS
    assert len(body) == XAXIS.size * YAXIS.size


def test_write_creates_missing_parent_directories(tmp_path):
    path = tmp_path / "nested" / "dir" / "grid.csv"
    gx.write_grid_csv(path, XAXIS, YAXIS, RESULT)
    assert path.exists()


def test_write_replaces_a_longer_previous_file_completely(tmp_path):
    path = tmp_path / "latest.csv"
    gx.write_grid_csv(path, XAXIS, YAXIS, RESULT)
    first_len = len(path.read_bytes())

    small_x = np.array([0.0, 1.0])
    small_y = np.array([0.0])
    small_result = np.array([[7.0, 8.0]])
    gx.write_grid_csv(path, small_x, small_y, small_result)

    _, body = _read_csv(path.read_bytes())
    assert len(body) == 2
    assert len(path.read_bytes()) < first_len


def test_write_leaves_no_tmp_file_behind(tmp_path):
    path = tmp_path / "grid.csv"
    gx.write_grid_csv(path, XAXIS, YAXIS, RESULT)
    assert not (tmp_path / "grid.csv.tmp").exists()
    assert list(tmp_path.iterdir()) == [path]


def test_failed_write_preserves_the_previous_file(tmp_path):
    path = tmp_path / "latest.csv"
    gx.write_grid_csv(path, XAXIS, YAXIS, RESULT)
    good = path.read_bytes()

    bad = np.zeros((YAXIS.size, XAXIS.size + 1))
    with pytest.raises(ValueError):
        gx.write_grid_csv(path, XAXIS, YAXIS, bad)

    assert path.read_bytes() == good
    assert not (tmp_path / "latest.csv.tmp").exists()


# ── NPZ format ───────────────────────────────────────────────────────────

def test_npz_stores_native_grid_not_long_form():
    x, y, c = _load_npz(gx.grid_npz_bytes(XAXIS, YAXIS, RESULT))
    # 1D axes and a 2D array of shape (len(y), len(x)) — not one row per point.
    assert x.ndim == 1 and y.ndim == 1
    assert c.shape == (YAXIS.size, XAXIS.size)


def test_npz_round_trips_values_exactly_at_float64():
    x, y, c = _load_npz(gx.grid_npz_bytes(XAXIS, YAXIS, RESULT))
    assert np.array_equal(x, XAXIS)
    assert np.array_equal(y, YAXIS)
    assert np.array_equal(c, RESULT)
    assert c.dtype == np.float64


def test_npz_keys_match_grid_columns():
    d = np.load(io.BytesIO(gx.grid_npz_bytes(XAXIS, YAXIS, RESULT)))
    assert tuple(d.files) == GRID_COLUMNS


def test_npz_float32_reduces_precision_and_size():
    full = gx.grid_npz_bytes(XAXIS, YAXIS, RESULT, float32=False)
    small = gx.grid_npz_bytes(XAXIS, YAXIS, RESULT, float32=True)
    _, _, c = _load_npz(small)
    assert c.dtype == np.float32
    assert len(small) < len(full)


def test_npz_step_decimates_like_csv():
    x, y, c = _load_npz(gx.grid_npz_bytes(XAXIS, YAXIS, RESULT, step=2))
    assert np.array_equal(x, XAXIS[::2])
    assert np.array_equal(y, YAXIS[::2])
    assert np.array_equal(c, RESULT[::2, ::2])


def test_npz_shape_mismatch_raises():
    bad = np.zeros((YAXIS.size, XAXIS.size + 1))
    with pytest.raises(ValueError, match="grid has shape"):
        gx.grid_npz_bytes(XAXIS, YAXIS, bad)


@pytest.mark.parametrize("step", [0, -1])
def test_npz_step_below_one_raises(step):
    with pytest.raises(ValueError, match="at least 1"):
        gx.grid_npz_bytes(XAXIS, YAXIS, RESULT, step=step)


def test_write_npz_round_trips_from_disk(tmp_path):
    path = tmp_path / "grid.npz"
    returned = gx.write_grid_npz(path, XAXIS, YAXIS, RESULT)
    assert returned == str(path)
    d = np.load(path)
    assert np.array_equal(d["concentration_mgL"], RESULT)


def test_write_npz_replaces_atomically_and_leaves_no_tmp(tmp_path):
    path = tmp_path / "latest.npz"
    gx.write_grid_npz(path, XAXIS, YAXIS, RESULT)

    small_x, small_y = np.array([0.0, 1.0]), np.array([0.0])
    small = np.array([[7.0, 8.0]])
    gx.write_grid_npz(path, small_x, small_y, small)

    d = np.load(path)
    assert d["concentration_mgL"].shape == (1, 2)
    assert not (tmp_path / "latest.npz.tmp").exists()
    assert list(tmp_path.iterdir()) == [path]


def test_failed_npz_write_preserves_previous_file(tmp_path):
    path = tmp_path / "latest.npz"
    gx.write_grid_npz(path, XAXIS, YAXIS, RESULT)
    good = path.read_bytes()

    bad = np.zeros((YAXIS.size, XAXIS.size + 1))
    with pytest.raises(ValueError):
        gx.write_grid_npz(path, XAXIS, YAXIS, bad)

    assert path.read_bytes() == good
    assert not (tmp_path / "latest.npz.tmp").exists()


# ── Config: concentration_output enum ────────────────────────────────────

def _base_config(**overrides):
    data = {
        "alpha_l": 2.0, "alpha_t": 0.2, "ca": 8.0, "gamma": 3.5,
        "elements": [{"kind": "circle", "x": 10.0, "y": 0.0, "c": 5.0, "r": 1.0}],
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("value", ["none", "csv", "npz", "both"])
def test_valid_concentration_output_accepted(value):
    cfg = ATConfiguration.from_dict(_base_config(concentration_output=value))
    assert cfg.concentration_output == value


def test_invalid_concentration_output_raises():
    with pytest.raises(ValueError, match="concentration_output"):
        ATConfiguration.from_dict(_base_config(concentration_output="csvv"))


def test_export_defaults_are_neutral():
    cfg = ATConfiguration.from_dict(_base_config())
    assert cfg.concentration_output == "none"
    assert cfg.export_step == 1
    assert cfg.export_path == ""
    assert cfg.export_npz_float32 is False
