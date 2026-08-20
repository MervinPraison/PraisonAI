"""
Unit tests for the external CLI-backend action on scheduled jobs.

A job carrying a ``backend`` runs its message as one headless turn through the
named backend from the registry — no native agent resolved, no in-process
model turn. Covers:

- success: backend content delivered, status ``succeeded``
- backend error result: status ``failed`` with the backend's error
- praisonai-code unavailable: recorded ``failed`` with remediation, no crash
- options plumbing: ``cwd`` and ``model`` reach ``backend.execute``,
  remaining ``backend_options`` become config overrides
- empty message: recorded ``skipped`` before the backend is resolved
- serialisation: ``backend``/``backend_options`` round-trip ``to_dict``;
  jobs without a backend stay byte-for-byte unchanged
"""

import asyncio
import sys
import types
from typing import List

import pytest

from praisonaiagents.scheduler.models import (
    ScheduleJob,
    Schedule,
    DeliveryTarget,
)
from praisonai.scheduler.executor import ScheduledAgentExecutor


class FakeRunner:
    def __init__(self):
        self.runs: List[dict] = []

    def mark_run(self, job, **kwargs):
        self.runs.append({"job": job, **kwargs})


class FakeResult:
    def __init__(self, content="", error=None):
        self.content = content
        self.error = error
        self.metadata = {}
        self.session_id = None


class FakeBackend:
    def __init__(self):
        self.calls: List[dict] = []
        self.result = FakeResult(content="done")
        self.config = types.SimpleNamespace(timeout_ms=300_000)

    async def execute(self, prompt, **kwargs):
        self.calls.append({"prompt": prompt, **kwargs})
        return self.result


def _run(coro):
    return asyncio.run(coro)


def _executor(delivered):
    async def deliver(target, text):
        delivered.append((target, text))

    return ScheduledAgentExecutor(
        runner=FakeRunner(),
        agent_resolver=lambda aid: None,
        delivery_handler=deliver,
    )


def _backend_job(message="do the thing", backend="claude-code", options=None,
                 deliver="telegram:-100"):
    return ScheduleJob(
        name="backend-job",
        schedule=Schedule(kind="every", every_seconds=1),
        message=message,
        backend=backend,
        backend_options=options or {},
        delivery=DeliveryTarget.parse(deliver),
    )


@pytest.fixture
def fake_backend(monkeypatch):
    """Route the executor's bridge import at a fake backends module."""
    backend = FakeBackend()
    fake_module = types.SimpleNamespace()
    fake_module.resolved_specs = []

    def resolve_cli_backend_config(spec):
        fake_module.resolved_specs.append(spec)
        return backend

    fake_module.resolve_cli_backend_config = resolve_cli_backend_config

    import praisonai_bot._code_bridge as bridge

    def fake_import(name):
        assert name == "praisonai_code.cli_backends"
        return fake_module

    monkeypatch.setattr(bridge, "import_code_module", fake_import)
    return backend, fake_module


def test_backend_success_delivered(fake_backend):
    backend, _ = fake_backend
    delivered: list = []
    ex = _executor(delivered)
    result = _run(ex._execute_one(_backend_job()))
    assert result.status == "succeeded"
    assert result.result == "done"
    assert result.delivered is True
    assert delivered[-1][1] == "done"
    assert backend.calls[0]["prompt"] == "do the thing"


def test_backend_error_result_failed(fake_backend):
    backend, _ = fake_backend
    backend.result = FakeResult(error="Claude CLI failed: boom")
    delivered: list = []
    ex = _executor(delivered)
    result = _run(ex._execute_one(_backend_job()))
    assert result.status == "failed"
    assert "boom" in result.error
    assert result.delivered is False
    runs = ex._runner.runs
    assert runs[-1]["status"] == "failed"


def test_backend_unavailable_records_failed(monkeypatch):
    import praisonai_bot._code_bridge as bridge

    def broken_import(name):
        raise ImportError("praisonai-code not installed")

    monkeypatch.setattr(bridge, "import_code_module", broken_import)
    delivered: list = []
    ex = _executor(delivered)
    result = _run(ex._execute_one(_backend_job()))
    assert result.status == "failed"
    assert "praisonai-code" in result.error


def test_backend_options_plumbing(fake_backend):
    backend, fake_module = fake_backend
    delivered: list = []
    ex = _executor(delivered)
    job = _backend_job(options={"cwd": "/tmp/ws", "timeout_ms": 120_000})
    job.model = "claude-sonnet-4-5"
    result = _run(ex._execute_one(job))
    assert result.status == "succeeded"
    call = backend.calls[0]
    assert call["cwd"] == "/tmp/ws"
    assert call["model"] == "claude-sonnet-4-5"
    # cwd is consumed by the executor; only config overrides reach resolution
    assert fake_module.resolved_specs == [
        {"id": "claude-code", "overrides": {"timeout_ms": 120_000}}
    ]


def test_backend_empty_message_skipped(fake_backend):
    backend, _ = fake_backend
    delivered: list = []
    ex = _executor(delivered)
    result = _run(ex._execute_one(_backend_job(message="")))
    assert result.status == "skipped"
    assert backend.calls == []


def test_backend_fields_round_trip():
    job = _backend_job(options={"cwd": "/tmp/ws"})
    data = job.to_dict()
    assert data["backend"] == "claude-code"
    assert data["backend_options"] == {"cwd": "/tmp/ws"}
    restored = ScheduleJob.from_dict(data)
    assert restored.backend == "claude-code"
    assert restored.backend_options == {"cwd": "/tmp/ws"}


def test_backendless_job_payload_unchanged():
    job = ScheduleJob(
        name="plain",
        schedule=Schedule(kind="every", every_seconds=1),
        message="hello",
    )
    data = job.to_dict()
    assert "backend" not in data
    assert "backend_options" not in data
    restored = ScheduleJob.from_dict(data)
    assert restored.backend is None
    assert restored.backend_options == {}
