from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

from numerical_models import (
    _check_grid_size,
    _checked_run_sim,
    _mf6_exe,
    _resolve_executable,
    _solver_timeout_seconds,
    balanced_source_buffers,
    run_numerical_model,
    run_numerical_model_horizontal,
)
from analytical_models import cirpka_2005, cirpka_domain_length


def test_solver_resolution_uses_configured_executable(monkeypatch, tmp_path):
    configured = tmp_path / "configured-mf6"
    configured.touch()
    monkeypatch.setenv("MF6_EXE", str(configured))

    assert _mf6_exe() == str(configured.resolve())


def test_solver_resolution_raises_clear_error_when_executable_is_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "")
    monkeypatch.setenv("MF6_EXE", str(tmp_path / "missing-mf6"))

    with pytest.raises(RuntimeError, match="Executable not found for MF6_EXE.*\\.modflow_bin/.*, solvers/.*, bin/.*, and PATH"):
        _resolve_executable("MF6_EXE", ["mf6.exe", "mf6"])


def test_grid_cap_rejects_oversized_run_before_solver(monkeypatch):
    monkeypatch.setenv("NUMERICAL_MAX_CELLS", "100")

    with pytest.raises(ValueError, match="Grid too large: 11 x 10 = 110 cells.*Increase Delta X / Delta Z"):
        _check_grid_size(11, 10)


def test_solver_timeout_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NUMERICAL_SOLVER_TIMEOUT_S", raising=False)
    monkeypatch.delenv("SOLVER_TIMEOUT_SECONDS", raising=False)

    assert _solver_timeout_seconds() == 0.0


def test_solver_timeout_terminates_external_process(monkeypatch, tmp_path):
    class FakePathManager:
        @staticmethod
        def get_sim_path():
            return str(tmp_path)

    class FakeSimulationData:
        mfpath = FakePathManager()

    class FakeSimulation:
        exe_name = str(tmp_path / "mf6")
        simulation_data = FakeSimulationData()

    class HangingProcess:
        pid = 123
        returncode = None

        def communicate(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired(cmd=[self.pid], timeout=timeout)
            return "partial solver output", ""

        def poll(self):
            return self.returncode

    process = HangingProcess()
    monkeypatch.setenv("NUMERICAL_SOLVER_TIMEOUT_S", "0.01")
    monkeypatch.setattr("numerical_models.subprocess.Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr("numerical_models._terminate_solver_process", lambda proc: setattr(proc, "returncode", -9))

    with pytest.raises(RuntimeError, match="timed out after 0.01 s and was terminated"):
        _checked_run_sim(FakeSimulation(), "MF6 test")


def _mf6_available():
    import numerical_models as _nm
    if _nm.flopy is None:
        return False
    try:
        return Path(_mf6_exe()).exists()
    except Exception:
        return False


mf6_required = pytest.mark.skipif(not _mf6_available(), reason="MODFLOW 6 (mf6) not available")


def test_balanced_source_buffers_fit_a_database_loaded_vertical_domain():
    assert balanced_source_buffers(3.5, 1.0) == pytest.approx((1.25, 1.25))


def test_cirpka_horizontal_analytical_domain_length_matches_orlando():
    # Analytical only (no solver): Orlando's erfinv-based Cirpka L_D for the reference inputs.
    lmax = cirpka_2005(Sw=5.0, Ath=0.2, Ca=8.0, Cd=5.0, Ga=3.5)
    assert cirpka_domain_length(lmax) == pytest.approx(143.66, rel=0.01)


@mf6_required
def test_tiny_horizontal_modflow6_smoke_produces_plume_length_and_concentration():
    result = run_numerical_model_horizontal(
        source_thickness=2.0, grid_size=1.0, al=1.0, at=0.5,
        gamma=3.5, cd=5.0, ca=8.0,
    )
    assert result.plume_length >= 0.0
    assert result.concentration.ndim == 2
    assert np.isfinite(result.concentration).all()
    assert result.domain_length > 0.0
    assert result.peclet > 0.0


@mf6_required
def test_tiny_vertical_modflow6_smoke_produces_plume_length_and_concentration():
    result = run_numerical_model(
        Lz=4.0, grid_size=1.0, al=1.0, atv=0.5,
        gamma=3.5, cd=5.0, ca=8.0,
    )
    assert result.plume_length >= 0.0
    assert result.concentration.ndim == 2
    assert np.isfinite(result.concentration).all()
    assert result.domain_length > 0.0
    assert result.aquifer_thickness == pytest.approx(4.0)


@mf6_required
def test_orlando_horizontal_reference_runs_and_sizes_domain():
    row = pd.read_csv(
        Path("tests/fixtures/orlando_reference/input_horizontal_W.csv"),
        delimiter=";", decimal=".",
    ).iloc[0]
    result = run_numerical_model_horizontal(
        source_thickness=float(row["source_thickness"]),
        grid_size=float(row["grid_size"]),
        al=float(row["al"]), at=float(row["at"]),
        gamma=float(row["gamma"]), cd=float(row["Cd"]), ca=float(row["Ca"]),
    )
    assert result.domain_length == pytest.approx(143.66, rel=0.02)
    assert result.x_grid[0] == pytest.approx(0.5)
    assert result.x_grid[-1] == pytest.approx(142.5)
    assert result.y_grid[0] == pytest.approx(0.5)
    assert result.y_grid[-1] == pytest.approx(49.5)
    # Matches horizontal_W (2).py: contour over extent=[0, ncol*delr, 0, nrow*delc].
    assert result.plume_length == pytest.approx(118.31, rel=0.03)  # real MODFLOW 6.7.0 run


@mf6_required
def test_orlando_vertical_reference_runs_and_sizes_domain():
    row = pd.read_csv(
        Path("tests/fixtures/orlando_reference/input_vertical_W.csv"),
        delimiter=";", decimal=".",
    ).iloc[0]
    result = run_numerical_model(
        Lz=float(row["Lz"]), grid_size=float(row["grid_size"]),
        al=float(row["al"]), atv=float(row["atv"]),
        gamma=float(row["gamma"]), cd=float(row["Cd"]), ca=float(row["Ca"]),
    )
    assert result.domain_length == pytest.approx(688.50, rel=0.02)
    # Cell-centered grid coordinates (matching vertical_W.py's extent mapping):
    # the plume length now agrees with the reference script (513.6 m) instead of
    # the previously stretched 514.21 m.
    assert result.plume_length == pytest.approx(513.6, rel=0.03)  # real MODFLOW 6.7.0 run
