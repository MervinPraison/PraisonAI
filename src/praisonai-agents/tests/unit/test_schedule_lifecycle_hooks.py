"""Tests for SCHEDULE_ADD / SCHEDULE_REMOVE hook emission.

``HookEvent.SCHEDULE_ADD`` and ``HookEvent.SCHEDULE_REMOVE`` were declared in
``praisonaiagents/hooks/types.py`` but never emitted by any production code
path, so a plugin registering on them was silent forever. (The *strings*
``"schedule_add"``/``"schedule_remove"`` do appear in production, but only as
agent tool names in TOOL_MAPPINGS / profiles / tool_search — not emissions.)

These tests pin the emission to the canonical schedule mutation point: the
schedule store, which every author path funnels through — the agent-callable
``schedule_add``/``schedule_remove`` tools, the ``praisonai schedule
add/remove/delete`` CLI, the gateway config reconciler, and the one-shot
``delete_after_run`` cleanup.
"""

import asyncio
import time

import pytest

from praisonaiagents.hooks import HookEvent, HookRegistry, HookResult
from praisonaiagents.hooks.registry import get_default_registry, set_default_registry


# ── helpers ──────────────────────────────────────────────────────────────────

class _Recorder:
    """Install a fresh default registry recording the events under test."""

    def __init__(self, *events):
        self.events = events
        self.fired = []
        self.payloads = []
        self._saved = None

    def __enter__(self):
        self._saved = get_default_registry()
        reg = HookRegistry()

        def _make(name):
            def _h(ev):
                self.fired.append(name)
                self.payloads.append(ev.to_dict())
                return HookResult.allow()
            return _h

        for evt in self.events:
            reg.on(evt)(_make(evt.value))
        set_default_registry(reg)
        return self

    def __exit__(self, *exc):
        set_default_registry(self._saved)
        return False


@pytest.fixture
def tool_store(tmp_path):
    """A temp FileScheduleStore wired into the schedule tools + core default."""
    from praisonaiagents.tools import schedule_tools
    from praisonaiagents import scheduler as _scheduler
    from praisonaiagents.scheduler.store import FileScheduleStore

    saved_tool_store = schedule_tools._store_instance
    try:
        saved_default = _scheduler.get_default_store()
    except Exception:
        saved_default = None

    store = FileScheduleStore(store_dir=str(tmp_path))
    schedule_tools.set_store(store)
    try:
        yield store
    finally:
        schedule_tools._store_instance = saved_tool_store
        try:
            _scheduler.set_default_store(saved_default)
        except Exception:
            pass


def _job(name="nightly", seconds=3600, **kw):
    from praisonaiagents.scheduler.models import Schedule, ScheduleJob

    return ScheduleJob(
        name=name,
        schedule=Schedule(kind="every", every_seconds=seconds),
        message="do the thing",
        **kw,
    )


# ── event input types ────────────────────────────────────────────────────────

class TestScheduleMutationInputTypes:
    def test_input_types_importable(self):
        from praisonaiagents.hooks import ScheduleAddInput, ScheduleRemoveInput

        assert ScheduleAddInput is not None
        assert ScheduleRemoveInput is not None

    def test_schedule_add_to_dict(self):
        from praisonaiagents.hooks import ScheduleAddInput

        ev = ScheduleAddInput(
            session_id="",
            cwd=".",
            event_name=HookEvent.SCHEDULE_ADD.value,
            timestamp="0",
            job_name="nightly",
            job_id="42",
            schedule="every 3600s",
            message="do the thing",
            principal="alice",
        )
        d = ev.to_dict()
        assert d["job_name"] == "nightly"
        assert d["job_id"] == "42"
        assert d["schedule"] == "every 3600s"
        assert d["message"] == "do the thing"
        assert d["principal"] == "alice"

    def test_schedule_remove_to_dict(self):
        from praisonaiagents.hooks import ScheduleRemoveInput

        ev = ScheduleRemoveInput(
            session_id="",
            cwd=".",
            event_name=HookEvent.SCHEDULE_REMOVE.value,
            timestamp="0",
            job_name="nightly",
            job_id="42",
            principal="alice",
        )
        d = ev.to_dict()
        assert d["job_name"] == "nightly"
        assert d["job_id"] == "42"
        assert d["principal"] == "alice"


# ── the agent-callable tool path ─────────────────────────────────────────────

class TestScheduleToolsEmit:
    def test_schedule_add_tool_fires_hook(self, tool_store):
        from praisonaiagents.tools.schedule_tools import schedule_add

        with _Recorder(HookEvent.SCHEDULE_ADD) as rec:
            out = schedule_add(name="nightly", schedule="*/30m", message="check email")

        assert "added" in out, out
        assert rec.fired == ["schedule_add"]
        payload = rec.payloads[0]
        assert payload["job_name"] == "nightly"
        assert payload["job_id"]
        assert payload["message"] == "check email"

    def test_schedule_remove_tool_fires_hook(self, tool_store):
        from praisonaiagents.tools.schedule_tools import schedule_add, schedule_remove

        schedule_add(name="nightly", schedule="*/30m", message="check email")
        with _Recorder(HookEvent.SCHEDULE_REMOVE) as rec:
            out = schedule_remove(name="nightly")

        assert "removed" in out, out
        assert rec.fired == ["schedule_remove"]
        assert rec.payloads[0]["job_name"] == "nightly"

    def test_failed_add_does_not_fire(self, tool_store):
        """A duplicate-name rejection is not an add — nothing may be emitted."""
        from praisonaiagents.tools.schedule_tools import schedule_add

        schedule_add(name="nightly", schedule="*/30m")
        with _Recorder(HookEvent.SCHEDULE_ADD) as rec:
            out = schedule_add(name="nightly", schedule="*/30m")

        assert "already exists" in out, out
        assert rec.fired == []

    def test_missing_remove_does_not_fire(self, tool_store):
        from praisonaiagents.tools.schedule_tools import schedule_remove

        with _Recorder(HookEvent.SCHEDULE_REMOVE) as rec:
            out = schedule_remove(name="does-not-exist")

        assert "not found" in out, out
        assert rec.fired == []


# ── the store itself (CLI `schedule remove`, gateway reconciler, one-shots) ──

class TestFileScheduleStoreEmits:
    def test_store_add_fires(self, tmp_path):
        from praisonaiagents.scheduler.store import FileScheduleStore

        store = FileScheduleStore(store_dir=str(tmp_path))
        with _Recorder(HookEvent.SCHEDULE_ADD) as rec:
            store.add(_job())
        assert rec.fired == ["schedule_add"]

    def test_store_remove_by_id_fires(self, tmp_path):
        """`praisonai schedule remove/delete` removes by id, not by name."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        store = FileScheduleStore(store_dir=str(tmp_path))
        job = _job()
        store.add(job)
        with _Recorder(HookEvent.SCHEDULE_REMOVE) as rec:
            assert store.remove(job.id) is True
        assert rec.fired == ["schedule_remove"]
        assert rec.payloads[0]["job_id"] == job.id
        assert rec.payloads[0]["job_name"] == "nightly"

    def test_store_remove_by_name_fires(self, tmp_path):
        from praisonaiagents.scheduler.store import FileScheduleStore

        store = FileScheduleStore(store_dir=str(tmp_path))
        store.add(_job(name="weekly"))
        with _Recorder(HookEvent.SCHEDULE_REMOVE) as rec:
            assert store.remove_by_name("weekly") is True
        assert rec.fired == ["schedule_remove"]
        assert rec.payloads[0]["job_name"] == "weekly"

    def test_no_op_remove_does_not_fire(self, tmp_path):
        from praisonaiagents.scheduler.store import FileScheduleStore

        store = FileScheduleStore(store_dir=str(tmp_path))
        with _Recorder(HookEvent.SCHEDULE_REMOVE) as rec:
            assert store.remove("nope") is False
            assert store.remove_by_name("nope") is False
        assert rec.fired == []

    def test_principal_scoped_skip_does_not_fire(self, tmp_path):
        """A cross-tenant remove that legitimately removes nothing is silent."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        store = FileScheduleStore(store_dir=str(tmp_path))
        store.add(_job(name="alices", principal="alice"))
        with _Recorder(HookEvent.SCHEDULE_REMOVE) as rec:
            assert store.remove_by_name("alices", principal="bob") is False
        assert rec.fired == []


class TestOneShotAutoDelete:
    """A spent ``delete_after_run`` job is deleted inside ``claim_due``,
    bypassing ``remove()`` entirely — it must still announce itself, exactly
    once (the runner's later ``remove(job.id)`` finds nothing)."""

    def test_claim_due_auto_delete_fires_once(self, tmp_path):
        from praisonaiagents.scheduler.store import FileScheduleStore
        from praisonaiagents.scheduler.runner import ScheduleRunner

        store = FileScheduleStore(store_dir=str(tmp_path))
        job = _job(name="one-shot", seconds=1)
        job.delete_after_run = True
        job.last_run_at = None
        store.add(job)

        with _Recorder(HookEvent.SCHEDULE_REMOVE) as rec:
            claimed = store.claim_due(now=time.time() + 5, owner_id="w1")
            assert [j.id for j in claimed] == [job.id]
            # The runner's post-run cleanup must not double-announce it.
            assert store.remove(job.id) is False

        assert rec.fired == ["schedule_remove"]
        assert rec.payloads[0]["job_name"] == "one-shot"
        assert ScheduleRunner is not None  # cleanup path lives here

    def test_recurring_claim_does_not_fire(self, tmp_path):
        from praisonaiagents.scheduler.store import FileScheduleStore

        store = FileScheduleStore(store_dir=str(tmp_path))
        job = _job(name="recurring", seconds=1)
        store.add(job)
        with _Recorder(HookEvent.SCHEDULE_REMOVE) as rec:
            assert store.claim_due(now=time.time() + 5, owner_id="w1")
        assert rec.fired == []


class TestConfigYamlScheduleStoreEmits:
    def test_config_store_add_and_remove_fire(self, tmp_path):
        from praisonaiagents.scheduler.config_store import ConfigYamlScheduleStore

        store = ConfigYamlScheduleStore(config_path=str(tmp_path / "config.yaml"))
        job = _job(name="from-config")
        with _Recorder(HookEvent.SCHEDULE_ADD, HookEvent.SCHEDULE_REMOVE) as rec:
            store.add(job)
            assert store.remove(job.id) is True
        assert rec.fired == ["schedule_add", "schedule_remove"]


# ── async safety and zero-overhead ───────────────────────────────────────────

class TestEmissionSafety:
    def test_fires_inside_a_running_event_loop(self, tmp_path):
        """`HookRunner.execute_sync` raises in a running loop — emission must not."""
        from praisonaiagents.scheduler.store import FileScheduleStore

        store = FileScheduleStore(store_dir=str(tmp_path))

        async def _run():
            with _Recorder(HookEvent.SCHEDULE_ADD) as rec:
                store.add(_job())
                # fire-and-forget task scheduled on the running loop
                current = asyncio.current_task()
                pending = [
                    t for t in asyncio.all_tasks() if t is not current and not t.done()
                ]
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                return list(rec.fired)

        assert asyncio.run(_run()) == ["schedule_add"]

    def test_no_hooks_registered_is_a_silent_noop(self, tmp_path):
        from praisonaiagents.scheduler.store import FileScheduleStore

        saved = get_default_registry()
        set_default_registry(HookRegistry())
        try:
            store = FileScheduleStore(store_dir=str(tmp_path))
            job = _job()
            store.add(job)  # must not raise
            assert store.remove(job.id) is True
        finally:
            set_default_registry(saved)

    def test_a_raising_hook_never_breaks_the_mutation(self, tmp_path):
        from praisonaiagents.scheduler.store import FileScheduleStore

        saved = get_default_registry()
        reg = HookRegistry()

        @reg.on(HookEvent.SCHEDULE_ADD)
        def _boom(_ev):
            raise RuntimeError("plugin exploded")

        set_default_registry(reg)
        try:
            store = FileScheduleStore(store_dir=str(tmp_path))
            job = _job()
            store.add(job)
            assert store.get(job.id) is not None
        finally:
            set_default_registry(saved)
