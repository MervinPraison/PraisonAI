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
    assert cfg.schedules["morning-brief"].agent == "personal"


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
        self.jobs[job.id] = job


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
