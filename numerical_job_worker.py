from __future__ import annotations

import sys
import traceback

from numerical_jobs import load_job_payload, mark_done, mark_failed
from numerical_models import run_numerical_model, run_numerical_model_horizontal


def run_payload(kind: str, params: dict):
    if kind == "horizontal_single":
        return run_numerical_model_horizontal(**params)
    if kind == "vertical_single":
        return run_numerical_model(**params)
    raise ValueError(f"Unsupported numerical job kind: {kind}")


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 1:
        print("Usage: python -m numerical_job_worker <job_id>", file=sys.stderr)
        return 2
    job_id = argv[0]
    try:
        kind, params = load_job_payload(job_id)
        result = run_payload(kind, params)
        mark_done(job_id, result)
        return 0
    except Exception as exc:
        mark_failed(job_id, f"{exc}\n{traceback.format_exc()}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
