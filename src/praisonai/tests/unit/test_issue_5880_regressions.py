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


@pytest.mark.skipif(not os.path.exists("/proc/self/stat"), reason="needs /proc")
def test_reconcile_detects_reused_pid(tmp_path):
    from praisonai.jobs.store import SqliteJobStore, _proc_start

    db = str(tmp_path / "jobs.db")
    SqliteJobStore(db)
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        same = Job(prompt="same", status=JobStatus.RUNNING)
        reused = Job(prompt="reused", status=JobStatus.RUNNING)
        _insert(db, same, f"{live.pid}:{_proc_start(live.pid)}:tok")
        _insert(db, reused, f"{live.pid}:1:tok")  # same pid, different start time

        store = SqliteJobStore(db)
        assert asyncio.run(store.get(same.id)).status == JobStatus.RUNNING
        assert asyncio.run(store.get(reused.id)).status == JobStatus.FAILED
    finally:
        live.kill()
        live.wait()


@pytest.mark.skipif(os.name != "posix", reason="needs kill(pid, 0)")
def test_unreadable_start_time_is_unknown_not_dead(tmp_path, monkeypatch):
    import praisonai.jobs.store as store_mod

    db = str(tmp_path / "jobs.db")
    store_mod.SqliteJobStore(db)
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        job = Job(prompt="hidden", status=JobStatus.RUNNING)
        _insert(db, job, f"{live.pid}:12345:tok")
        # e.g. /proc mounted with hidepid: another worker's stat is unreadable
        real = store_mod._proc_start
        monkeypatch.setattr(store_mod, "_proc_start",
                            lambda pid: "" if pid == live.pid else real(pid))
        store = store_mod.SqliteJobStore(db)
        assert asyncio.run(store.get(job.id)).status == JobStatus.RUNNING
    finally:
        live.kill()
        live.wait()


@pytest.mark.skipif(os.name != "posix", reason="needs ps")
def test_reused_pid_detected_without_proc(tmp_path, monkeypatch):
    import praisonai.jobs.store as store_mod

    real_isdir = os.path.isdir
    monkeypatch.setattr(os.path, "isdir", lambda p: False if p == "/proc" else real_isdir(p))
    db = str(tmp_path / "jobs.db")
    store_mod.SqliteJobStore(db)
    live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        start = store_mod._proc_start(live.pid)
        if not start:
            pytest.skip("ps lstart unavailable")
        assert ":" not in start
        same = Job(prompt="same", status=JobStatus.RUNNING)
        reused = Job(prompt="reused", status=JobStatus.RUNNING)
        _insert(db, same, f"{live.pid}:{start}:tok")
        _insert(db, reused, f"{live.pid}:Mon1Jan000000001970:tok")
        store = store_mod.SqliteJobStore(db)
        assert asyncio.run(store.get(same.id)).status == JobStatus.RUNNING
        assert asyncio.run(store.get(reused.id)).status == JobStatus.FAILED
    finally:
        live.kill()
        live.wait()


def test_owner_migration_failure_is_not_swallowed(tmp_path, monkeypatch):
    import sqlite3

    from praisonai.jobs.store import SqliteJobStore

    db = str(tmp_path / "jobs.db")
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, "
                 "session_id TEXT, idempotency_key TEXT, created_at TEXT, "
                 "completed_at TEXT, data TEXT NOT NULL)")
    conn.commit()
    locker = sqlite3.connect(db, timeout=0)
    locker.execute("BEGIN EXCLUSIVE")
    try:
        monkeypatch.setattr(sqlite3, "connect",
                            lambda path, **kw: conn.__class__(path, timeout=0.1, **kw))
        with pytest.raises(sqlite3.OperationalError):
            SqliteJobStore(db)
    finally:
        locker.rollback()
        locker.close()
        conn.close()


def test_manager_llm_settings_keep_model_name():
    from praisonai.framework_adapters.crewai_adapter import CrewAIAdapter

    shared = [{"model": "gpt-4o", "base_url": "https://shared", "api_key": "sk"}]
    assert CrewAIAdapter()._llm_settings("openai/gpt-4o-mini", shared) == (
        "openai/gpt-4o-mini", "https://shared", "sk"
    )


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
