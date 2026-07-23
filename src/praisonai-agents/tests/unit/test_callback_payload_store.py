"""Tests for the durable interactive callback-payload store.

Long ``reply``/``select`` values that overflow a channel's callback byte-cap
must round-trip losslessly via a short, stored reference instead of being
replaced by an unrecoverable hash (issue #3312).
"""

import asyncio

import pytest

from praisonaiagents.bots import (
    InMemoryCallbackPayloadStore,
    CallbackPayloadStoreProtocol,
    InteractiveRegistry,
    InteractiveContext,
    MessagePresentation,
    PresentationBlock,
    PresentationButton,
    PresentationAction,
    PresentationLimits,
    SelectOption,
    ActionType,
    BlockType,
    adapt_presentation,
)
from praisonaiagents.bots.presentation import (
    _encode_reply_callback,
    _encode_select_callback,
    _MAX_CALLBACK_LEN,
)

LONG = "https://example.com/docs/" + "a" * 80  # > 64 bytes


def _run(coro):
    return asyncio.run(coro)


def test_inmemory_store_satisfies_protocol():
    store = InMemoryCallbackPayloadStore()
    assert isinstance(store, CallbackPayloadStoreProtocol)


def test_store_put_get_roundtrip_and_expiry():
    store = InMemoryCallbackPayloadStore()
    store.put("r1", "value-1", expires_at=1e18)
    assert store.get("r1") == "value-1"
    assert store.get("missing") is None
    store.put("r2", "value-2", expires_at=0.0)  # already expired
    assert store.get("r2") is None


def test_store_evicts_oldest_beyond_capacity():
    store = InMemoryCallbackPayloadStore(max_entries=2)
    store.put("a", "1", expires_at=1e18)
    store.put("b", "2", expires_at=1e18)
    store.put("c", "3", expires_at=1e18)
    assert store.get("a") is None  # oldest evicted
    assert store.get("b") == "2"
    assert store.get("c") == "3"


def test_reply_encode_uses_ref_when_store_present():
    store = InMemoryCallbackPayloadStore()
    cb = _encode_reply_callback(LONG, store)
    assert cb.startswith("reply:@")
    assert len(cb.encode("utf-8")) <= _MAX_CALLBACK_LEN
    ref = cb[len("reply:@"):]
    assert store.get(ref) == LONG


def test_reply_encode_hash_fallback_without_store():
    cb = _encode_reply_callback(LONG)
    assert cb.startswith("reply:#")
    assert len(cb.encode("utf-8")) <= _MAX_CALLBACK_LEN


def test_reply_short_value_stays_inline():
    store = InMemoryCallbackPayloadStore()
    assert _encode_reply_callback("hi", store) == "reply:hi"


def test_select_encode_uses_ref_when_store_present():
    store = InMemoryCallbackPayloadStore()
    cb = _encode_select_callback("act1", LONG, store)
    assert cb.startswith("select:act1:@")
    assert len(cb.encode("utf-8")) <= _MAX_CALLBACK_LEN


def test_select_encode_stays_within_cap_for_long_action_id():
    store = InMemoryCallbackPayloadStore()
    cb = _encode_select_callback("A" * 100, LONG, store)
    assert "@" in cb
    assert len(cb.encode("utf-8")) <= _MAX_CALLBACK_LEN


def test_select_short_value_stays_inline():
    store = InMemoryCallbackPayloadStore()
    assert _encode_select_callback("act1", "a", store) == "select:act1:a"


def test_adapt_presentation_persists_and_references_select_value():
    sel = PresentationBlock.make_select(
        [SelectOption(label="Doc", value=LONG)], action_id="act1"
    )
    store = InMemoryCallbackPayloadStore()
    adapted = adapt_presentation(
        MessagePresentation([sel]),
        PresentationLimits.telegram(),
        callback_store=store,
    )
    value = adapted.blocks[0].buttons[0].action.value
    assert value.startswith("select:act1:@")


def test_dispatch_resolves_select_reference_to_exact_value():
    store = InMemoryCallbackPayloadStore()
    cb = _encode_select_callback("act1", LONG, store)
    registry = InteractiveRegistry(store=store)
    seen = {}

    async def handler(ctx):
        seen["value"] = ctx.platform_data["decoded_payload"]["value"]
        return "ok"

    registry.register("select", handler)
    ok = _run(registry.dispatch(InteractiveContext(callback_data=cb, user_id="u")))
    assert ok is True
    # action_id prefix is preserved; the trailing ref is restored to the value.
    assert seen["value"] == f"act1:{LONG}"


def test_dispatch_resolves_reply_reference_to_exact_value():
    store = InMemoryCallbackPayloadStore()
    cb = _encode_reply_callback(LONG, store)
    registry = InteractiveRegistry(store=store)
    seen = {}

    async def handler(ctx):
        seen["value"] = ctx.platform_data["decoded_payload"]["value"]
        return "ok"

    registry.register("reply", handler)
    ok = _run(registry.dispatch(InteractiveContext(callback_data=cb, user_id="u")))
    assert ok is True
    assert seen["value"] == LONG


def test_dispatch_drops_unknown_reference():
    registry = InteractiveRegistry(store=InMemoryCallbackPayloadStore())

    async def handler(ctx):
        return "ok"

    registry.register("select", handler)
    ok = _run(
        registry.dispatch(
            InteractiveContext(callback_data="select:act1:@deadbeef", user_id="u")
        )
    )
    assert ok is False


def test_dispatch_without_store_drops_reference():
    registry = InteractiveRegistry()  # no store

    async def handler(ctx):
        return "ok"

    registry.register("reply", handler)
    ok = _run(
        registry.dispatch(
            InteractiveContext(callback_data="reply:@abc123", user_id="u")
        )
    )
    assert ok is False


def test_ordinary_value_with_at_sign_not_treated_as_reference():
    registry = InteractiveRegistry(store=InMemoryCallbackPayloadStore())
    seen = {}

    async def handler(ctx):
        seen["value"] = ctx.platform_data["decoded_payload"]["value"]
        return "ok"

    registry.register("reply", handler)
    ok = _run(
        registry.dispatch(
            InteractiveContext(callback_data="reply:user@example.com", user_id="u")
        )
    )
    assert ok is True
    assert seen["value"] == "user@example.com"


def test_backward_compat_registry_without_store_routes_inline_values():
    registry = InteractiveRegistry()
    seen = {}

    async def handler(ctx):
        seen["value"] = ctx.platform_data["decoded_payload"]["value"]
        return "ok"

    registry.register("reply", handler)
    ok = _run(
        registry.dispatch(InteractiveContext(callback_data="reply:yes", user_id="u"))
    )
    assert ok is True
    assert seen["value"] == "yes"
