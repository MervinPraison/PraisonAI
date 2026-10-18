"""Regressions for issue #5880: adapter YAML parity, jobs reconcile, agent_file trust."""

import asyncio
import os
import subprocess
import sys

import pytest

from praisonai.jobs.models import Job, JobStatus


# --- Gap 1c: per-agent base_url/api_key win over shared llm_config ----------

def test_resolve_llm_prefers_spec_base_url_and_key(monkeypatch):
    import praisonai.inc as inc
    from praisonai.framework_adapters.crewai_adapter import CrewAIAdapter

    seen = {}

    class FakeModel:
        def __init__(self, model, base_url, api_key):
            seen.update(model=model, base_url=base_url, api_key=api_key)

        def get_model(self):
            return seen

    monkeypatch.setattr(inc, "PraisonAIModel", FakeModel)
    shared = [{"model": "gpt-4o", "base_url": "https://shared", "api_key": "sk-shared"}]

    CrewAIAdapter()._resolve_llm(
        {"model": "m", "base_url": "https://tenant", "api_key": "sk-tenant"}, shared
    )
    assert seen == {"model": "m", "base_url": "https://tenant", "api_key": "sk-tenant"}

    CrewAIAdapter()._resolve_llm({"model": "m"}, shared)
    assert seen["base_url"] == "https://shared" and seen["api_key"] == "sk-shared"


def test_autogen_no_longer_claims_function_calling_llm():
    from praisonai.framework_adapters.autogen_adapter import AutoGenAdapter

    assert "function_calling_llm" not in AutoGenAdapter.SUPPORTED_YAML_FIELDS
    assert "llm" in AutoGenAdapter.SUPPORTED_YAML_FIELDS


# --- Gap 2: reconcile must not fail another live process's jobs -------------

def _insert(path, job, owner):
    import sqlite3

    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO jobs (id, status, data, owner) VALUES (?, ?, ?, ?)",
        (job.id, job.status.value, job.model_dump_json(), owner),
    )
    conn.commit()
    conn.close()


def test_reconcile_skips_live_owner_and_fails_dead_owner(tmp_path):
    from praisonai.jobs.store import SqliteJobStore

    db = str(tmp_path / "jobs.db")
    SqliteJobStore(db)  # create schema

    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    try:
        live_job = Job(prompt="live", status=JobStatus.RUNNING)
        dead_job = Job(prompt="dead", status=JobStatus.RUNNING)
        legacy_job = Job(prompt="legacy", status=JobStatus.QUEUED)
        _insert(db, live_job, f"{live.pid}:tok")
        _insert(db, dead_job, f"{dead.pid}:tok")
        _insert(db, legacy_job, None)

        store = SqliteJobStore(db)
        get = lambda j: asyncio.run(store.get(j.id)).status

        if os.name == "posix":
            assert get(live_job) == JobStatus.RUNNING
        assert get(dead_job) == JobStatus.FAILED
        assert get(legacy_job) == JobStatus.FAILED
    finally:
        live.kill()
        live.wait()


# --- Gap 3: agent_file confined to cwd by default ---------------------------

def test_agent_file_defaults_to_cwd_root(tmp_path, monkeypatch):
    from praisonai.jobs.path_validation import validate_agent_file_path

    monkeypatch.delenv("PRAISONAI_JOBS_AGENT_ROOT", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "agents.yaml").write_text("agents: []")

    assert validate_agent_file_path("agents.yaml") == "agents.yaml"
    with pytest.raises(ValueError):
        validate_agent_file_path("/etc/passwd")
    with pytest.raises(ValueError):
        validate_agent_file_path("../outside.yaml")
