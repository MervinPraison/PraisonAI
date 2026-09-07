"""Tests for declarative gateway schedules (Issue #4913).

Covers the three parity arms:
- YAML/schema validation (``ScheduleConfigSchema``)
- config→store coercion + idempotent upsert (``load_schedules_into_store``)
- the CLI mutation surface (``GatewayHandler.schedules``)
"""

from types import SimpleNamespace

import pytest
import yaml


def _spec(**overrides):
    # Default to an interval trigger so coercion tests don't require the
    # optional ``croniter`` engine (cron parsing is covered separately).
    base = {
        "agent": "personal",
        "prompt": "Summarise my day",
        "every": "24h",
        "deliver": {"channel": "telegram", "channel_id": "12345"},
    }
    base.update(overrides)
    return base


# ── schema validation ────────────────────────────────────────────────────

def test_schedule_schema_accepts_cron():
    from praisonai_bot.bots._config_schema import ScheduleConfigSchema

    s = ScheduleConfigSchema(**_spec(every=None, cron="0 8 * * *"))
    assert s.agent == "personal"
    assert s.cron == "0 8 * * *"
    assert s.deliver.channel == "telegram"
    assert s.deliver.channel_id == "12345"


def test_schedule_schema_requires_one_trigger():
    from praisonai_bot.bots._config_schema import ScheduleConfigSchema

    with pytest.raises(Exception):
        ScheduleConfigSchema(agent="a", prompt="p")  # no cron/every/at


def test_schedule_schema_rejects_multiple_triggers():
    from praisonai_bot.bots._config_schema import ScheduleConfigSchema

    with pytest.raises(Exception):
        ScheduleConfigSchema(agent="a", prompt="p", cron="0 8 * * *", every="24h")


def test_gateway_schema_carries_schedules():
    from praisonai_bot.bots._config_schema import GatewayConfigSchema

    cfg = GatewayConfigSchema(
        channels={"telegram": {"token": "x"}},
        schedules={"morning-brief": _spec()},
    )
    assert "morning-brief" in cfg.schedules
    # Schedules are kept as raw dicts on the gateway schema (best-effort,
    # per-entry validation happens in the loader) so a malformed entry cannot
    # reject the whole config.
    assert cfg.schedules["morning-brief"]["agent"] == "personal"


def test_gateway_schema_does_not_abort_on_malformed_schedule():
    """A malformed schedule entry must NOT block the whole gateway (#4913)."""
    from praisonai_bot.bots._config_schema import GatewayConfigSchema

    # "bad" has no trigger — invalid per ScheduleConfigSchema — but the gateway
    # config must still validate so the gateway can start and skip it at load.
    cfg = GatewayConfigSchema(
        channels={"telegram": {"token": "x"}},
        schedules={"good": _spec(), "bad": {"agent": "x", "prompt": "p"}},
    )
    assert set(cfg.schedules) == {"good", "bad"}


# ── config → store coercion ──────────────────────────────────────────────

class _FakeStore:
    def __init__(self):
        self.jobs = {}

    def get(self, job_id):
        return self.jobs.get(job_id)

    def add(self, job):
        if job.id in self.jobs:
            raise ValueError("exists")
        self.jobs[job.id] = job

    def update(self, job):
        # Mirror the real store: ``update`` preserves only the lease, not
        # ``last_run_at`` — the loader is responsible for carrying that over.
        self.jobs[job.id] = job

    def list(self, agent_id=None, principal=None):
        return list(self.jobs.values())

    def remove(self, job_id):
        return self.jobs.pop(job_id, None) is not None


def test_job_from_config_delivery():
    from praisonai_bot.scheduler import schedule_job_from_config

    job = schedule_job_from_config("morning-brief", _spec())
    assert job.name == "morning-brief"
    assert job.agent_id == "personal"
    assert job.message == "Summarise my day"
    assert job.delivery is not None
    assert job.delivery.channel == "telegram"
    assert job.delivery.channel_id == "12345"


def test_job_from_config_every_interval():
    from praisonai_bot.scheduler import schedule_job_from_config

    job = schedule_job_from_config("hb", _spec(every="24h"))
    assert job.schedule.kind == "every"
    assert job.schedule.every_seconds == 24 * 3600


def test_load_into_store_is_idempotent():
    from praisonai_bot.scheduler import load_schedules_into_store

    store = _FakeStore()
    config = {"schedules": {"morning-brief": _spec()}}

    n1 = load_schedules_into_store(config, store)
    n2 = load_schedules_into_store(config, store)

    assert n1 == 1
    assert n2 == 1
    # Idempotent on a stable id: re-loading must not duplicate.
    assert len(store.jobs) == 1


def test_load_skips_malformed_entry():
    from praisonai_bot.scheduler import load_schedules_into_store

    store = _FakeStore()
    config = {"schedules": {"good": _spec(), "bad": {"agent": "x"}}}  # bad: no trigger

    loaded = load_schedules_into_store(config, store)
    assert loaded == 1
    assert len(store.jobs) == 1


def test_load_no_schedules_is_noop():
    from praisonai_bot.scheduler import load_schedules_into_store

    store = _FakeStore()
    assert load_schedules_into_store({}, store) == 0
    assert store.jobs == {}


def test_load_preserves_last_run_at_on_upsert():
    """Re-loading must not reset run-state and re-fire the job (#4913)."""
    from praisonai_bot.scheduler import load_schedules_into_store

    store = _FakeStore()
    config = {"schedules": {"morning-brief": _spec()}}
    load_schedules_into_store(config, store)

    # Simulate the job having already run once.
    (job_id,) = list(store.jobs)
    store.jobs[job_id].last_run_at = 1_000_000.0

    # Re-load the same config (e.g. gateway restart / hot-reload).
    load_schedules_into_store(config, store)
    assert store.jobs[job_id].last_run_at == 1_000_000.0


def test_load_prunes_removed_config_job():
    """A schedule removed from YAML must stop firing after reconcile (#4913)."""
    from praisonai_bot.scheduler import load_schedules_into_store

    store = _FakeStore()
    load_schedules_into_store(
        {"schedules": {"a": _spec(), "b": _spec()}}, store
    )
    assert len(store.jobs) == 2

    # "b" removed from config → pruned on next load.
    load_schedules_into_store({"schedules": {"a": _spec()}}, store)
    assert len(store.jobs) == 1


def test_prune_leaves_chat_created_jobs_untouched():
    """Reconciliation only prunes config-owned (cfg-*) jobs (#4913)."""
    from praisonai_bot.scheduler import load_schedules_into_store
    from praisonaiagents.scheduler.models import ScheduleJob
    from praisonaiagents.scheduler.parser import parse_schedule

    store = _FakeStore()
    chat_job = ScheduleJob(
        id="chat-random-xyz",
        name="chat-job",
        schedule=parse_schedule("*/24h"),
        message="from chat",
    )
    store.add(chat_job)

    # Load an empty schedules block: config-owned jobs would be pruned, but the
    # chat-created job (non ``cfg-`` id) must survive.
    load_schedules_into_store({"schedules": {}}, store)
    assert "chat-random-xyz" in store.jobs


# ── CLI mutation surface ─────────────────────────────────────────────────

def test_cli_schedule_add_list_remove(tmp_path):
    from praisonai_bot.cli.features.gateway import GatewayHandler

    config_path = str(tmp_path / "gateway.yaml")
    handler = GatewayHandler()

    # add
    code = handler.schedules(SimpleNamespace(
        schedules_command="add", name="morning-brief", agent="personal",
        prompt="Summarise my day", cron="0 8 * * *", every=None, at=None,
        channel="telegram", channel_id="12345", pre_run=None,
        config_file=config_path,
    ))
    assert code == 0

    with open(config_path) as f:
        data = yaml.safe_load(f)
    assert data["schedules"]["morning-brief"]["agent"] == "personal"
    assert data["schedules"]["morning-brief"]["cron"] == "0 8 * * *"  # noqa
    assert data["schedules"]["morning-brief"]["deliver"]["channel"] == "telegram"

    # list (should not error)
    assert handler.schedules(SimpleNamespace(
        schedules_command="list", config_file=config_path,
    )) == 0

    # remove
    assert handler.schedules(SimpleNamespace(
        schedules_command="remove", name="morning-brief", config_file=config_path,
    )) == 0
    with open(config_path) as f:
        data = yaml.safe_load(f)
    assert "morning-brief" not in (data.get("schedules") or {})


def test_cli_schedule_add_requires_single_trigger(tmp_path):
    from praisonai_bot.cli.features.gateway import GatewayHandler

    config_path = str(tmp_path / "gateway.yaml")
    code = GatewayHandler().schedules(SimpleNamespace(
        schedules_command="add", name="x", agent="a", prompt="p",
        cron="0 8 * * *", every="24h", at=None,
        channel=None, channel_id=None, pre_run=None, config_file=config_path,
    ))
    assert code == 1


def test_cli_schedule_add_refuses_to_clobber_broken_config(tmp_path):
    """`schedule add` must not overwrite an unreadable config (#4913)."""
    from praisonai_bot.cli.features.gateway import GatewayHandler

    config_path = tmp_path / "gateway.yaml"
    # A file that exists but is not a YAML mapping (a list at the root).
    config_path.write_text("- not\n- a\n- mapping\n")

    code = GatewayHandler().schedules(SimpleNamespace(
        schedules_command="add", name="x", agent="a", prompt="p",
        cron="0 8 * * *", every=None, at=None,
        channel=None, channel_id=None, pre_run=None, config_file=str(config_path),
    ))
    assert code == 1
    # The original (non-mapping) content must be preserved, not clobbered.
    assert config_path.read_text() == "- not\n- a\n- mapping\n"


def test_cli_schedule_remove_refuses_to_clobber_broken_config(tmp_path):
    """`schedule remove` must not overwrite an unreadable config (#4913)."""
    from praisonai_bot.cli.features.gateway import GatewayHandler

    config_path = tmp_path / "gateway.yaml"
    config_path.write_text("- broken\n")

    code = GatewayHandler().schedules(SimpleNamespace(
        schedules_command="remove", name="x", config_file=str(config_path),
    ))
    assert code == 1
    assert config_path.read_text() == "- broken\n"
