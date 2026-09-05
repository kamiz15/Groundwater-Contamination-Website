from pathlib import Path
import subprocess

import numpy as np
import pandas as pd
import pytest

from numerical_models import (
    COURANT_TARGET,
    MAX_TIMESTEPS,
    _check_grid_size,
    _checked_run_sim,
    _mf6_exe,
    _resolve_executable,
    _solver_timeout_seconds,
    balanced_source_buffers,
    horizontal_source_rows,
    run_numerical_model,
    run_numerical_model_horizontal,
    vertical_source_layers,
)
from numerical_input_validation import UserMessageError
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

    with pytest.raises(RuntimeError, match="engine is unavailable"):
        _resolve_executable("MF6_EXE", ["mf6.exe", "mf6"])


def test_grid_cap_rejects_oversized_run_before_solver(monkeypatch):
    monkeypatch.setenv("NUMERICAL_MAX_CELLS", "100")

    with pytest.raises(ValueError, match="^Increase the grid size and run it again.$"):
        _check_grid_size(11, 10)


def test_only_our_own_messages_reach_the_reader():
    from numerical_input_validation import NUMERICAL_FAILED, UserMessageError, user_instruction

    assert user_instruction(UserMessageError("Reduce the grid size and run it again.")) == "Reduce the grid size and run it again."
    assert user_instruction(ValueError("Pick at least one site.")) == "Pick at least one site."
    assert user_instruction("The simulation stopped unexpectedly.") == "The simulation stopped unexpectedly."
    # A crash, a traceback or an empty message never reaches the screen.
    assert user_instruction(KeyError("C:/app/.numerical_runs/tmp7/mf6.nam")) == NUMERICAL_FAILED
    assert user_instruction(RuntimeError("Traceback (most recent call last): ...")) == NUMERICAL_FAILED
    assert user_instruction("") == NUMERICAL_FAILED


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

    with pytest.raises(RuntimeError, match="took too long. Increase the grid size"):
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
    # Domain width is HORIZONTAL_WIDTH_FACTOR (5) x Sw = 25 m, so 25 rows.
    assert result.y_grid[-1] == pytest.approx(24.5)
    assert result.domain_width == pytest.approx(25.0)
    # Matches horizontal_W-1.py: contour over extent=[0, ncol*delr, 0, nrow*delc].
    # 116.63, not the 118.31 of the 10xSw domain: halving the width brings the
    # fixed-acceptor top and bottom boundaries twice as close to the plume.
    assert result.plume_length == pytest.approx(116.63, rel=0.03)  # real MODFLOW 6.7.0 run


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


# --- source geometry (pure; no solver needed) ---------------------------------

def test_no_segments_is_the_centred_source_the_page_has_always_run():
    # Sw = 5 m at 1 m cells in a 25 m domain -> the middle five rows.
    assert horizontal_source_rows(25, 1.0, 25.0, 5.0) == [10, 11, 12, 13, 14]


def test_one_segment_covering_the_zone_matches_the_unsegmented_source():
    assert (horizontal_source_rows(25, 1.0, 25.0, 5.0, [(0.0, 5.0)])
            == horizontal_source_rows(25, 1.0, 25.0, 5.0))


def test_segments_carve_the_zone_and_leave_the_gap_between_them_clean():
    assert horizontal_source_rows(25, 1.0, 25.0, 5.0, [(0, 1), (3, 5)]) == [10, 13, 14]


def test_overlapping_segments_name_each_row_once():
    """MF6 rejects a duplicated constant-concentration cell outright."""
    assert horizontal_source_rows(25, 1.0, 25.0, 5.0, [(0, 3), (2, 5)]) == [10, 11, 12, 13, 14]


@pytest.mark.parametrize("segments", [[(0, 9)], [(-1, 3)], [(4, 2)], [(2, 2)], []])
def test_a_segment_outside_the_zone_is_refused(segments):
    with pytest.raises(UserMessageError):
        horizontal_source_rows(25, 1.0, 25.0, 5.0, segments)


def test_more_than_ten_segments_is_refused():
    with pytest.raises(UserMessageError):
        horizontal_source_rows(25, 1.0, 25.0, 5.0, [(i * 0.4, i * 0.4 + 0.2) for i in range(11)])


def test_vertical_default_is_every_layer_but_the_acceptor_boundary():
    assert vertical_source_layers(10) == [1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_vertical_source_sits_where_the_direction_says():
    assert vertical_source_layers(10, "top", 30) == [0, 1, 2]
    assert vertical_source_layers(10, "bottom", 50) == [5, 6, 7, 8, 9]
    # Rounds up, and never past the grid.
    assert vertical_source_layers(10, "top", 5) == [0]
    assert vertical_source_layers(10, "bottom", 100) == list(range(10))


@pytest.mark.parametrize("direction,percentage", [
    ("sideways", 50), ("top", 0), ("top", 101), ("top", None), (" TOP ", 30),
])
def test_a_bad_direction_or_coverage_is_refused(direction, percentage):
    if direction.strip().lower() == "top" and percentage == 30:
        # Whitespace and case are tolerated; this one must succeed.
        assert vertical_source_layers(10, direction, percentage) == [0, 1, 2]
        return
    with pytest.raises(UserMessageError):
        vertical_source_layers(10, direction, percentage)


def test_timestepping_is_capped_so_a_long_domain_buys_longer_steps():
    assert COURANT_TARGET == 2.0
    assert MAX_TIMESTEPS == 50
