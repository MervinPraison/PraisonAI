"""Tests for actor-authorization enforcement in the interactive registry."""

import asyncio

import pytest

from praisonaiagents.bots.interactive import (
    InteractiveContext,
    InteractiveRegistry,
)


def _ctx(user_id: str, callback_data: str = "approval:1a2b3c:allow") -> InteractiveContext:
    return InteractiveContext(callback_data=callback_data, user_id=user_id)


def test_dispatch_without_authorizer_allows_any_actor():
    registry = InteractiveRegistry()
    seen = []

    async def handler(ctx):
        seen.append(ctx.user_id)
        return "ok"

    registry.register("approval", handler)
    handled = asyncio.run(registry.dispatch(_ctx("999")))

    assert handled is True
    assert seen == ["999"]


def test_dispatch_rejects_unauthorized_actor():
    registry = InteractiveRegistry()
    allowed = {"requester", "admin"}
    seen = []

    async def handler(ctx):
        seen.append(ctx.user_id)
        return "ok"

    registry.register(
        "approval", handler, authorize=lambda ctx: ctx.user_id in allowed
    )

    handled = asyncio.run(registry.dispatch(_ctx("999")))

    assert handled is False
    assert seen == []  # handler must never run for unauthorized actor


def test_dispatch_allows_authorized_actor():
    registry = InteractiveRegistry()
    allowed = {"requester", "admin"}
    seen = []

    async def handler(ctx):
        seen.append(ctx.user_id)
        return "ok"

    registry.register(
        "approval", handler, authorize=lambda ctx: ctx.user_id in allowed
    )

    handled = asyncio.run(registry.dispatch(_ctx("admin")))

    assert handled is True
    assert seen == ["admin"]


def test_authorizer_exception_denies():
    registry = InteractiveRegistry()
    seen = []

    async def handler(ctx):
        seen.append(ctx.user_id)
        return "ok"

    def boom(ctx):
        raise RuntimeError("authorizer failure")

    registry.register("approval", handler, authorize=boom)

    handled = asyncio.run(registry.dispatch(_ctx("admin")))

    assert handled is False
    assert seen == []


def test_unregister_clears_authorizer():
    registry = InteractiveRegistry()

    async def handler(ctx):
        return "ok"

    registry.register("approval", handler, authorize=lambda ctx: False)
    registry.unregister("approval")
    # Re-register with no authorizer -> should allow again
    registry.register("approval", handler)

    handled = asyncio.run(registry.dispatch(_ctx("999")))
    assert handled is True
