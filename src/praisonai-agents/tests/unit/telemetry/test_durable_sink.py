"""Unit tests for the durable per-identity token-usage sink (Issue #4894)."""

import os

import pytest

from praisonaiagents.telemetry.durable_sink import SqliteTokenUsageSink
from praisonaiagents.telemetry.protocols import TokenUsageSinkProtocol


class _Metrics:
    def __init__(self, i=0, o=0, t=None):
        self.input_tokens = i
        self.output_tokens = o
        if t is not None:
            self.total_tokens = t


def test_protocol_conformance():
    sink = SqliteTokenUsageSink()
    assert isinstance(sink, TokenUsageSinkProtocol)


def test_record_and_spent():
    sink = SqliteTokenUsageSink()
    sink.record(identity="u1", scope="tg", cost_usd=0.5, ts=10.0)
    sink.record(identity="u1", scope="tg", cost_usd=0.25, ts=20.0)
    sink.record(identity="u2", scope="tg", cost_usd=1.0, ts=15.0)

    assert sink.spent(identity="u1", scope="tg", since=0.0) == pytest.approx(0.75)
    assert sink.spent(identity="u2", scope="tg", since=0.0) == pytest.approx(1.0)


def test_spent_respects_window_since():
    sink = SqliteTokenUsageSink()
    sink.record(identity="u1", scope="tg", cost_usd=1.0, ts=5.0)
    sink.record(identity="u1", scope="tg", cost_usd=2.0, ts=50.0)
    # window starts at 10 -> only the ts=50 record counts
    assert sink.spent(identity="u1", scope="tg", since=10.0) == pytest.approx(2.0)


def test_spent_across_scopes_when_scope_none():
    sink = SqliteTokenUsageSink()
    sink.record(identity="u1", scope="tg", cost_usd=1.0, ts=1.0)
    sink.record(identity="u1", scope="slack", cost_usd=2.0, ts=1.0)
    assert sink.spent(identity="u1", since=0.0) == pytest.approx(3.0)
    assert sink.spent(identity="u1", scope="tg", since=0.0) == pytest.approx(1.0)


def test_spent_unknown_identity_zero():
    sink = SqliteTokenUsageSink()
    assert sink.spent(identity="nobody", since=0.0) == 0.0


def test_usage_aggregate():
    sink = SqliteTokenUsageSink()
    sink.record(
        identity="u1", scope="tg", cost_usd=0.5,
        input_tokens=100, output_tokens=50, ts=1.0,
    )
    sink.record(
        identity="u1", scope="tg", cost_usd=0.5,
        input_tokens=10, output_tokens=5, ts=2.0,
    )
    u = sink.usage(identity="u1", scope="tg", since=0.0)
    assert u["cost_usd"] == pytest.approx(1.0)
    assert u["input_tokens"] == 110
    assert u["output_tokens"] == 55
    assert u["total_tokens"] == 165
    assert u["records"] == 2


def test_persist_reads_identity_from_metadata():
    sink = SqliteTokenUsageSink()
    sink.persist(
        task_id="t1",
        agent_name="bot",
        model="gpt-4o",
        metrics=_Metrics(i=10, o=5),
        metadata={"identity": "tg:42", "scope": "telegram", "cost_usd": 0.3},
    )
    assert sink.spent(identity="tg:42", scope="telegram", since=0.0) == pytest.approx(0.3)


def test_persist_falls_back_to_agent_name():
    sink = SqliteTokenUsageSink()
    sink.persist(
        task_id="t1",
        agent_name="bot",
        model="gpt-4o",
        metrics=_Metrics(i=10, o=5),
        metadata=None,
    )
    u = sink.usage(identity="bot", since=0.0)
    assert u["records"] == 1
    assert u["total_tokens"] == 15


def test_durability_survives_reopen(tmp_path):
    db = os.path.join(str(tmp_path), "usage.db")
    sink = SqliteTokenUsageSink(db)
    sink.record(identity="u1", scope="tg", cost_usd=1.5, ts=1.0)
    sink.close()

    reopened = SqliteTokenUsageSink(db)
    assert reopened.spent(identity="u1", scope="tg", since=0.0) == pytest.approx(1.5)
    reopened.close()


def test_context_manager(tmp_path):
    db = os.path.join(str(tmp_path), "usage.db")
    with SqliteTokenUsageSink(db) as sink:
        sink.record(identity="u1", cost_usd=1.0, ts=1.0)
    with SqliteTokenUsageSink(db) as sink:
        assert sink.spent(identity="u1", since=0.0) == pytest.approx(1.0)


def test_creates_parent_directory(tmp_path):
    db = os.path.join(str(tmp_path), "nested", "dir", "usage.db")
    sink = SqliteTokenUsageSink(db)
    sink.record(identity="u1", cost_usd=1.0)
    assert os.path.exists(db)
    sink.close()
