"""Unit tests for data_analysis.modflow — MODFLOW 6 binary output to CSV.

Builds real MODFLOW-format binary head files with flopy's BinaryHeader so the
reader is exercised against the actual on-disk layout, not a mock.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

flopy = pytest.importorskip("flopy", reason="flopy is required to read MODFLOW output")

from data_analysis import modflow


def _write_hds(path, data: np.ndarray) -> str:
    """Write a 3-D array as a single-time-step MODFLOW head file."""
    from flopy.utils.binaryfile import BinaryHeader

    nlay, nrow, ncol = data.shape
    with open(path, "wb") as fh:
        for lay in range(nlay):
            BinaryHeader.create(
                bintype="HEAD", text="            HEAD",
                nrow=nrow, ncol=ncol, ilay=lay + 1,
                pertim=1.0, totim=1.0, kstp=1, kper=1,
            ).tofile(fh)
            np.asarray(data[lay], dtype=np.float32).tofile(fh)
    return str(path)


@pytest.fixture
def cross_section_hds(tmp_path):
    # nrow == 1 -> a vertical cross-section (3 layers x 5 columns)
    data = np.arange(15, dtype=np.float32).reshape(3, 1, 5) + 10.0
    return _write_hds(tmp_path / "cross.hds", data), data


@pytest.fixture
def plan_hds(tmp_path):
    data = np.arange(40, dtype=np.float32).reshape(2, 4, 5) + 1.0
    return _write_hds(tmp_path / "plan.hds", data), data


def test_list_records(cross_section_hds):
    path, _ = cross_section_hds
    assert len(modflow.list_records(path, "head")) == 1


def test_read_array_shape_and_values(cross_section_hds):
    path, data = cross_section_hds
    arr = modflow.read_array(path, "head")
    assert arr.shape == (3, 1, 5)
    np.testing.assert_allclose(arr, data)


def test_cross_section_long_form_has_metre_coordinates(cross_section_hds):
    path, data = cross_section_hds
    df = modflow.to_long_form(modflow.read_array(path, "head"), "head", lx=100.0, ly=20.0)
    assert list(df.columns) == ["x_m", "z_m", "head_m"]
    assert len(df) == 15
    # linspace(0, length, count) matches numerical_models._grid_points
    assert df["x_m"].min() == 0.0 and df["x_m"].max() == 100.0
    assert df["z_m"].min() == 0.0 and df["z_m"].max() == 20.0


def test_plan_view_uses_y_axis(plan_hds):
    path, _ = plan_hds
    df = modflow.to_long_form(modflow.read_array(path, "head"), "head",
                              layer=0, lx=50.0, ly=8.0)
    assert list(df.columns) == ["x_m", "y_m", "head_m"]
    assert len(df) == 20  # 4 rows x 5 cols


def test_falls_back_to_indices_without_extents(cross_section_hds):
    path, _ = cross_section_hds
    df = modflow.to_long_form(modflow.read_array(path, "head"), "head")
    assert list(df.columns) == ["col", "layer", "head_m"]


def test_dry_cells_are_dropped(tmp_path):
    data = np.full((1, 3, 3), 1e30, dtype=np.float32)
    data[0, 1, 1] = 5.0
    path = _write_hds(tmp_path / "dry.hds", data)
    df = modflow.to_long_form(modflow.read_array(path, "head"), "head", lx=10.0, ly=10.0)
    assert len(df) == 1
    assert df["head_m"].iloc[0] == pytest.approx(5.0)


def test_layer_out_of_range_raises(plan_hds):
    path, _ = plan_hds
    with pytest.raises(ValueError, match="outside"):
        modflow.to_long_form(modflow.read_array(path, "head"), "head", layer=9)


def test_unknown_kind_raises(cross_section_hds):
    path, _ = cross_section_hds
    with pytest.raises(ValueError, match="Unknown kind"):
        modflow.read_array(path, "velocity")


def test_missing_file_raises():
    with pytest.raises(ValueError, match="not found"):
        modflow.read_array("does_not_exist.hds", "head")


def test_convert_writes_csv_round_trip(cross_section_hds, tmp_path):
    path, _ = cross_section_hds
    out = tmp_path / "head.csv"
    modflow.convert(path, out, "head", lx=100.0, ly=20.0)
    restored = pd.read_csv(out)
    assert list(restored.columns) == ["x_m", "z_m", "head_m"]
    assert len(restored) == 15


def test_cli_reports_success(cross_section_hds, tmp_path, capsys):
    path, _ = cross_section_hds
    out = tmp_path / "cli.csv"
    rc = modflow.main([path, "-o", str(out), "--lx", "100", "--ly", "20"])
    assert rc == 0
    assert "Wrote 15 rows" in capsys.readouterr().out


def test_cli_reports_error_for_missing_file(capsys):
    assert modflow.main(["nope.hds"]) == 1
    assert "Error:" in capsys.readouterr().out
