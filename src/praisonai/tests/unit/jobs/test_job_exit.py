"""A job whose run calls sys.exit fails that job; it cannot stop the server's event loop.

``PraisonAI.run`` (CLI code) exits the process on some errors, for example a
framework that is not installed. Raised in the job's worker thread, SystemExit
reached the event loop and stopped it, so the server (and the TestClient
portal) hung.
"""
import asyncio

import pytest


def test_job_run_that_exits_raises_a_job_error(monkeypatch):
    import praisonai
    from praisonai.jobs.executor import JobExecutor
    from praisonai.jobs.models import Job
    from praisonai.jobs.store import InMemoryJobStore

    class Exits:
        def __init__(self, **kwargs):
            pass

        def run(self):
            raise SystemExit(1)

    monkeypatch.setattr(praisonai, "PraisonAI", Exits)
    executor = JobExecutor(store=InMemoryJobStore())
    with pytest.raises(RuntimeError, match="exited"):
        asyncio.run(executor._run_legacy_praisonai(Job(prompt="x"), "agents.yaml", "crewai"))
