"""Tests for task-local SessionContextVars.

W1 — Concurrent message handlers must NOT clobber each other's
session metadata. Use ``contextvars.ContextVar`` so each asyncio task
has its own copy.
"""

from __future__ import annotations

import asyncio

import pytest

from praisonaiagents.session.context import (
    SessionContext,
    clear_session_context,
    get_session_context,
    set_session_context,
)


class TestSetGet:
    def test_set_and_get_roundtrips(self):
        token = set_session_context(
            platform="telegram",
            chat_id="100",
            user_id="alice",
        )
        try:
            ctx = get_session_context()
            assert ctx.platform == "telegram"
            assert ctx.chat_id == "100"
            assert ctx.user_id == "alice"
        finally:
            clear_session_context(token)

    def test_default_context_is_empty(self):
        ctx = get_session_context()
        assert ctx.platform == ""
        assert ctx.chat_id == ""
        assert ctx.user_id == ""

    def test_clear_restores_previous(self):
        token = set_session_context(platform="telegram", user_id="alice")
        clear_session_context(token)
        assert get_session_context().platform == ""


class TestAsyncTaskIsolation:
    @pytest.mark.asyncio
    async def test_concurrent_tasks_dont_clobber(self):
        seen = []

        async def handler(name, delay):
            token = set_session_context(platform=name, user_id=name)
            try:
                await asyncio.sleep(delay)
                seen.append(get_session_context().platform)
            finally:
                clear_session_context(token)

        await asyncio.gather(
            handler("telegram", 0.02),
            handler("discord", 0.01),
            handler("slack", 0.03),
        )
        assert sorted(seen) == ["discord", "slack", "telegram"]


class TestSessionContextDataclass:
    def test_context_has_all_fields(self):
        ctx = SessionContext(
            platform="telegram",
            chat_id="100",
            chat_name="DM",
            thread_id="t1",
            user_id="alice",
            user_name="Alice",
            unified_user_id="alice-global",
        )
        assert ctx.unified_user_id == "alice-global"

    def test_context_dict_roundtrip(self):
        ctx = SessionContext(platform="telegram", user_id="alice")
        d = ctx.to_dict()
        ctx2 = SessionContext.from_dict(d)
        assert ctx2.platform == "telegram"
        assert ctx2.user_id == "alice"
