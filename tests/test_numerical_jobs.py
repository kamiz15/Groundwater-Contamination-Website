import numerical_jobs


def test_new_job_queues_behind_running_job_without_cancelling_it(monkeypatch, tmp_path):
    monkeypatch.setenv("NUMERICAL_JOB_ROOT", str(tmp_path / "jobs"))
    monkeypatch.setenv("NUMERICAL_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(numerical_jobs, "_start_worker", lambda _job_id: None)
    terminated = []
    monkeypatch.setattr(numerical_jobs, "_terminate_pid", terminated.append)

    first = numerical_jobs.submit_job("vertical_single", {"case": 1})
    with numerical_jobs._connect() as conn:
        conn.execute("UPDATE numerical_jobs SET pid = 123 WHERE id = ?", (first,))
    second = numerical_jobs.submit_job("vertical_single", {"case": 2})

    # New contract: a new submission never cancels another job; it queues.
    assert numerical_jobs.job_status(first)["status"] == "running"
    assert numerical_jobs.job_status(second)["status"] == "queued"
    assert terminated == []
    assert numerical_jobs.queue_counts()["running"] == 1
    assert numerical_jobs.queue_counts()["queued"] == 1


def test_new_job_keeps_existing_queued_and_completed_jobs(monkeypatch, tmp_path):
    monkeypatch.setenv("NUMERICAL_JOB_ROOT", str(tmp_path / "jobs"))
    monkeypatch.setenv("NUMERICAL_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(numerical_jobs, "_start_worker", lambda _job_id: None)

    completed = numerical_jobs.submit_job("vertical_single", {"case": 1})
    now = numerical_jobs.time.time()
    with numerical_jobs._connect() as conn:
        conn.execute("UPDATE numerical_jobs SET status = 'done' WHERE id = ?", (completed,))
        conn.execute(
            """
            INSERT INTO numerical_jobs (id, kind, params_json, status, created_at, updated_at)
            VALUES ('old-queued', 'vertical_single', '{}', 'queued', ?, ?)
            """,
            (now, now),
        )

    newest = numerical_jobs.submit_job("vertical_single", {"case": 2})

    # New contract: nothing is cancelled. The oldest queued job takes the free slot,
    # the newest waits its turn, and the completed job is untouched.
    assert numerical_jobs.job_status(completed)["status"] == "done"
    assert numerical_jobs.job_status("old-queued")["status"] == "running"
    assert numerical_jobs.job_status(newest)["status"] == "queued"
    assert numerical_jobs.queue_counts()["running"] == 1
    assert numerical_jobs.queue_counts()["queued"] == 1


def test_worker_started_after_cancellation_is_terminated(monkeypatch, tmp_path):
    monkeypatch.setenv("NUMERICAL_JOB_ROOT", str(tmp_path / "jobs"))
    now = numerical_jobs.time.time()
    with numerical_jobs._connect() as conn:
        conn.execute(
            """
            INSERT INTO numerical_jobs (id, kind, params_json, status, created_at, updated_at)
            VALUES ('cancelled-job', 'vertical_single', '{}', 'cancelled', ?, ?)
            """,
            (now, now),
        )

    class Process:
        pid = 456

    monkeypatch.setattr(numerical_jobs.subprocess, "Popen", lambda *args, **kwargs: Process())
    terminated = []
    monkeypatch.setattr(numerical_jobs, "_terminate_pid", terminated.append)

    numerical_jobs._start_worker("cancelled-job")

    assert terminated == [456]
