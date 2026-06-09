import numerical_jobs


def test_queue_respects_concurrency_and_queues_excess(monkeypatch, tmp_path):
    monkeypatch.setenv("NUMERICAL_JOB_ROOT", str(tmp_path / "jobs"))
    monkeypatch.setenv("NUMERICAL_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(numerical_jobs, "_start_worker", lambda _job_id: None)

    first = numerical_jobs.submit_job("vertical_single", {"case": 1})
    second = numerical_jobs.submit_job("vertical_single", {"case": 2})

    assert numerical_jobs.job_status(first)["status"] == "running"
    second_status = numerical_jobs.job_status(second)
    assert second_status["status"] == "queued"
    assert second_status["queue_position"] == 1
    assert numerical_jobs.queue_counts()["running"] == 1
    assert numerical_jobs.queue_counts()["queued"] == 1


def test_cancel_running_job_frees_slot_for_next_queued_job(monkeypatch, tmp_path):
    monkeypatch.setenv("NUMERICAL_JOB_ROOT", str(tmp_path / "jobs"))
    monkeypatch.setenv("NUMERICAL_MAX_CONCURRENCY", "1")
    monkeypatch.setattr(numerical_jobs, "_start_worker", lambda _job_id: None)
    monkeypatch.setattr(numerical_jobs, "_terminate_pid", lambda _pid: None)

    first = numerical_jobs.submit_job("vertical_single", {"case": 1})
    second = numerical_jobs.submit_job("vertical_single", {"case": 2})

    assert numerical_jobs.cancel_job(first) is True

    assert numerical_jobs.job_status(first)["status"] == "cancelled"
    assert numerical_jobs.job_status(second)["status"] == "running"
    assert numerical_jobs.queue_counts()["running"] == 1
    assert numerical_jobs.queue_counts()["queued"] == 0
