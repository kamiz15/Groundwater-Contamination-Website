from __future__ import annotations

import json
import os
import pickle
import signal
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


STATUSES = {"queued", "running", "done", "failed", "cancelled"}


def _job_root() -> Path:
    root = Path(os.getenv("NUMERICAL_JOB_ROOT", ".numerical_jobs"))
    root.mkdir(exist_ok=True)
    (root / "results").mkdir(exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    return root


def _db_path() -> Path:
    return _job_root() / "jobs.sqlite3"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS numerical_jobs (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            params_json TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL,
            started_at REAL,
            finished_at REAL,
            pid INTEGER,
            result_path TEXT,
            plume_length REAL,
            error TEXT,
            cancel_requested INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    return conn


def max_concurrency() -> int:
    return max(1, int(os.getenv("NUMERICAL_MAX_CONCURRENCY", "2")))


def submit_job(kind: str, params: dict[str, Any]) -> str:
    job_id = uuid.uuid4().hex
    now = time.time()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO numerical_jobs (id, kind, params_json, status, created_at, updated_at)
            VALUES (?, ?, ?, 'queued', ?, ?)
            """,
            (job_id, kind, json.dumps(params), now, now),
        )
    pump_queue()
    return job_id


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    if data["status"] == "queued":
        with _connect() as conn:
            pos = conn.execute(
                """
                SELECT COUNT(*) FROM numerical_jobs
                WHERE status = 'queued'
                  AND (created_at < ? OR (created_at = ? AND id <= ?))
                """,
                (data["created_at"], data["created_at"], data["id"]),
            ).fetchone()[0]
        data["queue_position"] = int(pos)
    return data


def job_status(job_id: str) -> dict[str, Any] | None:
    pump_queue()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM numerical_jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_dict(row)


def queue_counts() -> dict[str, int]:
    pump_queue()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS count FROM numerical_jobs GROUP BY status"
        ).fetchall()
    counts = {status: 0 for status in STATUSES}
    counts.update({row["status"]: int(row["count"]) for row in rows})
    counts["max_concurrency"] = max_concurrency()
    return counts


def fetch_result(job_id: str) -> Any:
    with _connect() as conn:
        row = conn.execute("SELECT result_path FROM numerical_jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None or not row["result_path"]:
        raise KeyError(f"No completed numerical result for job {job_id}")
    with open(row["result_path"], "rb") as handle:
        return pickle.load(handle)


def cancel_job(job_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT status, pid FROM numerical_jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return False
        if row["status"] in {"done", "failed", "cancelled"}:
            return False
        now = time.time()
        conn.execute(
            "UPDATE numerical_jobs SET cancel_requested = 1, status = 'cancelled', updated_at = ?, finished_at = ? WHERE id = ?",
            (now, now, job_id),
        )
        pid = row["pid"]
    if pid:
        _terminate_pid(int(pid))
    pump_queue()
    return True


def mark_done(job_id: str, result: Any) -> None:
    result_path = _job_root() / "results" / f"{job_id}.pickle"
    with open(result_path, "wb") as handle:
        pickle.dump(result, handle)
    plume_length = float(getattr(result, "plume_length", 0.0))
    now = time.time()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE numerical_jobs
            SET status = 'done', updated_at = ?, finished_at = ?, result_path = ?, plume_length = ?
            WHERE id = ? AND status != 'cancelled'
            """,
            (now, now, str(result_path), plume_length, job_id),
        )
    pump_queue()


def mark_failed(job_id: str, error: str) -> None:
    now = time.time()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE numerical_jobs
            SET status = 'failed', updated_at = ?, finished_at = ?, error = ?
            WHERE id = ? AND status != 'cancelled'
            """,
            (now, now, error, job_id),
        )
    pump_queue()


def load_job_payload(job_id: str) -> tuple[str, dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT kind, params_json FROM numerical_jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise KeyError(f"Unknown numerical job {job_id}")
    return row["kind"], json.loads(row["params_json"])


def pump_queue() -> None:
    while True:
        with _connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            running = conn.execute(
                "SELECT COUNT(*) FROM numerical_jobs WHERE status = 'running'"
            ).fetchone()[0]
            if running >= max_concurrency():
                conn.commit()
                return
            row = conn.execute(
                "SELECT id FROM numerical_jobs WHERE status = 'queued' ORDER BY created_at, id LIMIT 1"
            ).fetchone()
            if row is None:
                conn.commit()
                return
            job_id = row["id"]
            now = time.time()
            conn.execute(
                "UPDATE numerical_jobs SET status = 'running', started_at = ?, updated_at = ? WHERE id = ?",
                (now, now, job_id),
            )
            conn.commit()
        _start_worker(job_id)


def _start_worker(job_id: str) -> None:
    logs = _job_root() / "logs"
    stdout_path = logs / f"{job_id}.out.log"
    stderr_path = logs / f"{job_id}.err.log"
    stdout = open(stdout_path, "ab")
    stderr = open(stderr_path, "ab")
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "numerical_job_worker", job_id],
            cwd=Path.cwd(),
            stdout=stdout,
            stderr=stderr,
            start_new_session=(os.name != "nt"),
        )
    except Exception as exc:
        stdout.close()
        stderr.close()
        mark_failed(job_id, f"Unable to start numerical worker: {exc}")
        return
    with _connect() as conn:
        conn.execute("UPDATE numerical_jobs SET pid = ?, updated_at = ? WHERE id = ?", (proc.pid, time.time(), job_id))


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except ProcessLookupError:
        return
