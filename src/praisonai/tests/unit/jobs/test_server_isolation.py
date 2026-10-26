"""Each create_app() owns its store/executor; building one never rewires another."""

import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from praisonai.jobs import server
from praisonai.jobs.store import InMemoryJobStore


def test_second_app_does_not_clobber_first():
    a, b = InMemoryJobStore(), InMemoryJobStore()
    default_store = server._store
    app_a = server.create_app(store=a)
    app_b = server.create_app(store=b)

    assert app_a.state.job_store is a
    assert app_b.state.job_store is b
    assert app_a.state.job_executor.store is a
    assert app_b.state.job_executor.store is b
    assert app_a.state.job_executor is not app_b.state.job_executor
    # Injected stores must not leak into the process defaults.
    assert server._store is default_store

    with TestClient(app_a) as client:
        job_id = client.post("/api/v1/runs", json={"prompt": "hi"}).json()["job_id"]
    assert len(a._jobs) == 1 and job_id in a._jobs
    assert len(b._jobs) == 0
