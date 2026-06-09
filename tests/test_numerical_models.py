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
    balanced_source_buffers,
    run_numerical_model,
    run_numerical_model_horizontal,
)


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


def test_tiny_horizontal_modflow6_smoke_produces_plume_length_and_concentration():
    solver = Path(_mf6_exe())
    assert solver.exists(), f"Resolved MODFLOW 6 executable does not exist: {solver}"

    result = run_numerical_model_horizontal(
        Lx=6.0,
        A_W=4.0,
        Sw=1.0,
        ncol=6,
        nrow=4,
        prsity=0.3,
        al=1.0,
        alpha_Th=0.1,
        gamma=3.5,
        cd=0.2,
        ca=8.0,
        h1=10.0,
        h2=9.0,
        hk=1.0,
        perlen=1.0,
        plume_threshold=8.1,
        source_col_index=1,
    )

    assert result.plume_length >= 0.0
    assert result.concentration.shape == (4, 6)
    assert np.isfinite(result.concentration).all()


def test_balanced_source_buffers_fit_a_database_loaded_vertical_domain():
    assert balanced_source_buffers(3.5, 1.0) == pytest.approx((1.25, 1.25))


def test_tiny_vertical_modflow6_smoke_produces_plume_length_and_concentration():
    solver = Path(_mf6_exe())
    assert solver.exists(), f"Resolved MODFLOW 6 executable does not exist: {solver}"

    result = run_numerical_model(
        Lx=6.0,
        Ly=4.0,
        ncol=6,
        nrow=4,
        prsity=0.3,
        al=1.0,
        av=0.1,
        gamma=3.5,
        cd=0.2,
        ca=8.0,
        h1=10.0,
        h2=9.0,
        hk=1.0,
        vk=1.0,
        source_thickness=1.0,
        source_bottom_buffer=1.5,
        perlen=1.0,
        plume_threshold=8.1,
    )

    assert result.plume_length >= 0.0
    assert result.concentration.shape == (4, 6)
    assert np.isfinite(result.concentration).all()


def test_orlando_vertical_reference_fixture_matches_expected_plume_length():
    row = pd.read_csv(
        Path("tests/fixtures/orlando_reference/input_vertical.csv"),
        delimiter=";",
        decimal=".",
    ).iloc[0]

    result = run_numerical_model(
        Lx=float(row["Lx"]),
        Ly=float(row["Lz"]),
        ncol=int(row["ncol"]),
        nrow=int(row["nlay"]),
        prsity=float(row["prsity"]),
        al=float(row["al"]),
        av=float(row["atv"]),
        gamma=float(row["gamma"]),
        cd=float(row["Cd"]),
        ca=float(row["Ca"]),
        h1=float(row["h1"]),
        h2=float(row["h2"]),
        hk=float(row["hk"]),
        perlen=100.0,
        plume_threshold=8.0,
        ath=float(row["at"]),
    )

    assert result.plume_length == pytest.approx(42.0, rel=0.01)


def test_orlando_horizontal_reference_fixture_matches_expected_plume_length():
    row = pd.read_csv(
        Path("tests/fixtures/orlando_reference/input2.csv"),
        delimiter=";",
        decimal=".",
    ).iloc[0]

    result = run_numerical_model_horizontal(
        Lx=float(row["Lx"]),
        A_W=float(row["Ly"]),
        Sw=float(row["source"]),
        ncol=int(row["ncol"]),
        nrow=int(row["nrow"]),
        prsity=float(row["prsity"]),
        al=float(row["al"]),
        alpha_Th=float(row["at"]),
        gamma=float(row["gamma"]),
        cd=float(row["Cd"]),
        ca=float(row["Ca"]),
        h1=float(row["h1"]),
        h2=float(row["h2"]),
        hk=float(row["hk"]),
        perlen=100.0,
        plume_threshold=8.0,
    )

    assert result.plume_length == pytest.approx(36.1, rel=0.01)
