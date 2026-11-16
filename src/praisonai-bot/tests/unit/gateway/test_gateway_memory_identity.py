"""Gateway agents get a stable memory identity across boots and clones (Issue #6033)."""

import pytest

from praisonaiagents import Agent
from praisonaiagents.bots import BotConfig

from praisonai_bot.bots._registry import register_platform
from praisonai_bot.gateway.server import (
    WebSocketGateway,
    _gateway_memory_user_id,
    _with_memory_user_id,
)


class _FakeChannelBot:
    def __init__(self, token="", agent=None, config=None, **kwargs):
        self.agent = agent


register_platform("memid_test_6033", _FakeChannelBot)


def _mem_id(agent):
    mem = agent._memory_instance
    return getattr(mem, "user_id", None) or mem.cfg.get("user_id")


def _boot(agents_cfg):
    gw = WebSocketGateway()
    gw._create_agents_from_config(agents_cfg)
    return gw


def _channel_agent(gw, agent_id):
    bot = gw._create_bot(
        "memid_test_6033", "tok", gw.get_agent(agent_id), BotConfig(),
        {"platform": "memid_test_6033"},
    )
    return bot.agent


@pytest.fixture(autouse=True)
def _tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # FileMemory writes under ./.praisonai


def test_memory_true_is_stable_across_boots_and_clones():
    cfg = {"assistant": {"instructions": "x", "model": "gpt-4o-mini", "memory": True}}
    first = _boot(cfg)
    channel = _channel_agent(first, "assistant")
    assert _mem_id(first.get_agent("assistant")) == "gateway-assistant"
    assert _mem_id(channel) == "gateway-assistant"

    channel._memory_instance.store_long_term("The user's favourite colour is teal.")

    second = _boot(cfg)
    restarted = _channel_agent(second, "assistant")
    assert _mem_id(restarted) == "gateway-assistant"
    assert restarted._memory_instance.search("favourite colour", limit=5)


def test_distinct_agents_get_distinct_ids():
    gw = _boot({
        "support-bot": {"instructions": "x", "model": "gpt-4o-mini", "memory": True},
        "sales-bot": {"instructions": "x", "model": "gpt-4o-mini", "memory": {"history": True}},
    })
    assert _mem_id(gw.get_agent("support-bot")) == "gateway-support-bot"
    assert _mem_id(gw.get_agent("sales-bot")) == "gateway-sales-bot"


def test_sanitised_ids_do_not_collide():
    dotted = _gateway_memory_user_id("support.bot")
    underscored = _gateway_memory_user_id("support_bot")
    assert underscored == "gateway-support_bot"
    assert dotted != underscored
    assert dotted == _gateway_memory_user_id("support.bot")
    assert "." not in dotted and "/" not in _gateway_memory_user_id("a/b")


def test_explicit_user_id_wins():
    gw = _boot({"a": {"instructions": "x", "model": "gpt-4o-mini",
                      "memory": {"user_id": "custom"}}})
    assert _mem_id(gw.get_agent("a")) == "custom"
    assert _mem_id(_channel_agent(gw, "a")) == "custom"


def test_no_memory_key_does_not_use_shared_praison_id():
    gw = _boot({"support-bot": {"instructions": "x", "model": "gpt-4o-mini"}})
    assert gw.get_agent("support-bot").user_id == "gateway-support-bot"
    assert _channel_agent(gw, "support-bot").user_id == "gateway-support-bot"


def test_with_memory_user_id_shapes():
    assert _with_memory_user_id(False, "u") is False
    assert _with_memory_user_id(True, "u") == {"user_id": "u"}
    assert _with_memory_user_id("sqlite", "u") == {"backend": "sqlite", "user_id": "u"}
    assert _with_memory_user_id({"user_id": "x"}, "u") == {"user_id": "x"}
    assert _with_memory_user_id("sqlite:///m.db", "u") == "sqlite:///m.db"


def test_plain_agent_outside_gateway_keeps_random_id():
    assert _mem_id(Agent(name="a", instructions="x", memory=True)).startswith("agent-")
