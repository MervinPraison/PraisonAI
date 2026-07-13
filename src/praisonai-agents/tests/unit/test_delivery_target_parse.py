"""Tests for ``DeliveryTarget.parse`` — token → target parsing."""

from praisonaiagents.scheduler import DeliveryTarget


def test_parse_empty_returns_none():
    assert DeliveryTarget.parse("") is None
    assert DeliveryTarget.parse(None) is None
    assert DeliveryTarget.parse("   ") is None


def test_parse_platform_and_channel():
    t = DeliveryTarget.parse("telegram:123456")
    assert t is not None
    assert t.channel == "telegram"
    assert t.channel_id == "123456"
    assert t.thread_id is None
    assert t.deliver == "telegram:123456"


def test_parse_platform_channel_thread():
    t = DeliveryTarget.parse("telegram:123:789")
    assert t.channel == "telegram"
    assert t.channel_id == "123"
    assert t.thread_id == "789"


def test_parse_bare_platform():
    t = DeliveryTarget.parse("telegram")
    assert t.channel == "telegram"
    assert t.channel_id == ""
    assert t.deliver == "telegram"


def test_parse_symbolic_tokens():
    for token in ("origin", "all", "ORIGIN"):
        t = DeliveryTarget.parse(token)
        assert t is not None
        assert t.channel == ""
        assert t.deliver == token.lower()


def test_parse_strips_whitespace():
    t = DeliveryTarget.parse("  telegram : 123  ")
    assert t.channel == "telegram"
    assert t.channel_id == "123"
