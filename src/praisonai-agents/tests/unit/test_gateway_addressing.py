"""Tests for the canonical session-address grammar (Issue #5383)."""

import pytest

from praisonaiagents.gateway import (
    GATEWAY_METHODS,
    RESERVED_NAMES,
    SHORT_ID_LEN,
    OperatorScope,
    SessionRef,
    build_session_path,
    derive_short_id,
    parse_session_path,
    resolve_required_scope,
    slugify,
)


def test_derive_short_id_from_uuid_tail():
    key = "agent:assistant:a3f9c2e1-7b04-4c8e-9f21-1234abcd5678"
    short = derive_short_id(key)
    assert short == "1234abcd5678"[-SHORT_ID_LEN:]
    assert len(short) == SHORT_ID_LEN


def test_derive_short_id_none_without_hex_tail():
    assert derive_short_id("report.js") is None
    assert derive_short_id("") is None
    assert derive_short_id("main") is None


def test_derive_short_id_none_when_hex_not_at_end():
    # A hex run followed by non-hex chars (a file-like key) must NOT be
    # shortened, so it can round-trip losslessly via the literal escape hatch.
    assert derive_short_id("report-deadbeef.js") is None
    assert derive_short_id("deadbeef.txt") is None


def test_file_like_key_with_hex_run_roundtrips():
    # Regression: ``report-deadbeef.js`` must not collapse to ``deadbeef``.
    key = "report-deadbeef.js"
    path = build_session_path("bot", key)
    assert path == "chat/bot/!report-deadbeef.js"
    ref = parse_session_path(path)
    assert ref == SessionRef(agent_id="bot", literal_key=key)


def test_slugify():
    assert slugify("Quarterly Report") == "quarterly-report"
    assert slugify("  Hello,  World!! ") == "hello-world"
    assert slugify("") is None
    assert slugify("   ") is None
    assert slugify("---") is None


def test_slugify_truncates():
    long = "a" * 100
    out = slugify(long, max_len=10)
    assert out is not None and len(out) <= 10


def test_build_path_hides_whole_uuid():
    key = "agent:assistant:a3f9c2e1-7b04-4c8e-9f21-000000000000"
    path = build_session_path("assistant", key, "Quarterly report")
    assert path is not None
    assert path.startswith("chat/assistant/quarterly-report-")
    # The whole UUID never appears whole in the URL.
    assert "a3f9c2e1-7b04-4c8e-9f21-000000000000" not in path


def test_build_path_without_display_name():
    key = "agent:bot:aaaabbbbcccc"
    path = build_session_path("bot", key)
    assert path == "chat/bot/aaaabbbb"[: len("chat/bot/")] + derive_short_id(key)


def test_build_path_custom_namespace():
    path = build_session_path("bot", "x-11112222", namespace="thread")
    assert path is not None and path.startswith("thread/bot/")


def test_build_path_empty_inputs():
    assert build_session_path("", "key") is None
    assert build_session_path("agent", "") is None


def test_roundtrip_slug_short():
    key = "agent:assistant:a3f9c2e1-7b04-4c8e-9f21-1234abcd5678"
    path = build_session_path("assistant", key, "Quarterly report")
    ref = parse_session_path(path)
    assert ref == SessionRef(
        agent_id="assistant",
        short_id=derive_short_id(key),
        slug_hint="quarterly-report",
    )


def test_parse_no_namespace():
    ref = parse_session_path("assistant/quarterly-report-1234abcd")
    assert ref.agent_id == "assistant"
    assert ref.short_id == "1234abcd"
    assert ref.slug_hint == "quarterly-report"


def test_parse_reserved_sentinel():
    for name in RESERVED_NAMES:
        ref = parse_session_path(f"chat/assistant/{name}")
        assert ref == SessionRef(agent_id="assistant", slug_hint=name)


def test_parse_short_id_only():
    ref = parse_session_path("chat/assistant/deadbeef")
    assert ref.short_id == "deadbeef"
    assert ref.slug_hint is None


def test_literal_key_escape_hatch_roundtrips():
    path = build_session_path("bot", "report.js")
    assert path == "chat/bot/!report.js"
    ref = parse_session_path(path)
    assert ref == SessionRef(agent_id="bot", literal_key="report.js")


def test_file_like_key_not_a_static_asset():
    # A key that looks like an asset is escaped behind the ``!`` hatch, so a
    # router never mistakes the final segment for ``report.js`` on disk.
    path = build_session_path("bot", "weird/key.js")
    ref = parse_session_path(path)
    assert ref.literal_key == "weird/key.js"


def test_slug_hint_only_when_no_short_id():
    ref = parse_session_path("chat/assistant/my-label")
    # "my-label" has no 8-hex short id, so it becomes a slug hint the resolver
    # matches against session labels.
    assert ref.short_id is None
    assert ref.slug_hint == "my-label"


def test_parse_invalid():
    assert parse_session_path("") is None
    assert parse_session_path("just-one-segment") is None
    assert parse_session_path("/") is None


def test_parse_rejects_surplus_segments():
    # A canonical address is at most ``<ns>/<agent>/<ref>``; a longer path is
    # malformed and must be rejected rather than silently using its last two
    # segments (which would resolve to the wrong agent).
    assert parse_session_path("chat/other/assistant/deadbeef") is None
    assert parse_session_path("a/b/c/d/e") is None


def test_agent_id_with_special_chars_roundtrips():
    path = build_session_path("team/assistant", "x-11112222")
    ref = parse_session_path(path)
    assert ref.agent_id == "team/assistant"


def test_session_resolve_registered_read():
    assert "session.resolve" in GATEWAY_METHODS
    assert resolve_required_scope("session.resolve") == OperatorScope.READ
