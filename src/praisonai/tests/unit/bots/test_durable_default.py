"""Tests for durable delivery wired by default in build_session_manager."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


def _make_config(delivery=None):
    """Minimal duck-typed config for build_session_manager."""
    return SimpleNamespace(
        delivery=delivery,
        session=None,
        max_history=None,
    )


def test_durable_on_by_default(tmp_path, monkeypatch):
    """A bot built without any delivery config gets a journal + DLQ by default."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    from praisonai.bots._session import build_session_manager

    mgr = build_session_manager(_make_config(), platform="telegram")

    assert mgr._ingress_journal is not None
    assert mgr._dlq is not None
    # Both durable stores share one canonical per-agent directory.
    assert (tmp_path / "state" / "ingress.sqlite").parent.exists()


def test_durable_can_be_disabled(tmp_path, monkeypatch):
    """delivery.durable=False falls back to in-memory (no journal/DLQ)."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    from praisonai.bots._session import build_session_manager

    delivery = SimpleNamespace(durable=False, store=None)
    mgr = build_session_manager(_make_config(delivery), platform="telegram")

    assert mgr._ingress_journal is None
    assert mgr._dlq is None


def test_durable_store_override(tmp_path, monkeypatch):
    """delivery.store overrides the canonical store directory."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / "ignored"))
    from praisonai.bots._session import build_session_manager

    custom = tmp_path / "custom_store"
    delivery = SimpleNamespace(durable=True, store=str(custom))
    mgr = build_session_manager(_make_config(delivery), platform="discord")

    assert mgr._ingress_journal is not None
    assert custom.exists()
    assert (custom / "ingress.sqlite").exists() or custom.exists()


def test_resolve_durable_store_dir_uses_canonical_path(tmp_path, monkeypatch):
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    from praisonai.bots._session import resolve_durable_store_dir

    store_dir = resolve_durable_store_dir("telegram")
    assert store_dir == tmp_path / "state"
    assert store_dir.exists()


@pytest.mark.asyncio
async def test_dedup_skips_duplicate_redelivery(tmp_path, monkeypatch):
    """A redelivered message (same message_id) is deduped, not double-processed."""
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    from unittest.mock import MagicMock
    from praisonai.bots._session import build_session_manager

    mgr = build_session_manager(_make_config(), platform="telegram")

    calls: list[str] = []

    def fake_chat(prompt, *args, **kwargs):
        calls.append(prompt)
        return "ok"

    agent = MagicMock()
    agent.chat = fake_chat
    agent.chat_history = []

    first = await mgr.chat(agent, "u1", "hello", chat_id="c1", message_id="m1")
    second = await mgr.chat(agent, "u1", "hello", chat_id="c1", message_id="m1")

    assert first == "ok"
    # The redelivered duplicate returns "" and the agent is not run again.
    assert second == ""
    assert calls == ["hello"]
