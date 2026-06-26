"""Per-route toolset scoping on the bot inbound path (Issue #2298).

Verifies that ``BotSessionManager.chat()`` scopes ``agent.tools`` per a
supplied tool policy for the duration of a turn and restores the agent's
original toolset afterwards, so an untrusted inbound route never advertises
dangerous tools while attended/trusted uses of the same shared agent are
unaffected.
"""

from __future__ import annotations

import pytest

from praisonai.bots._session import BotSessionManager
from praisonaiagents.gateway import RouteBinding


def _named(name):
    def _tool():  # pragma: no cover - never invoked
        return None
    _tool.__name__ = name
    return _tool


class FakeAgent:
    def __init__(self, tools):
        self.chat_history = []
        self.tools = tools
        self.tools_seen_during_chat = None

    def chat(self, prompt):
        # Snapshot the toolset the model would have been offered this turn.
        self.tools_seen_during_chat = list(self.tools)
        return f"reply to {prompt}"


@pytest.mark.asyncio
async def test_untrusted_policy_scopes_then_restores():
    tools = [_named("run_shell"), _named("web_search"), _named("write_file")]
    agent = FakeAgent(tools)
    original = list(agent.tools)

    policy = RouteBinding(agent="a", trust="untrusted").tool_policy()
    assert policy is not None

    mgr = BotSessionManager(platform="telegram")
    await mgr.chat(agent, "stranger", "hello", tool_policy=policy)

    # During the turn the dangerous tools were not advertised.
    seen = [t.__name__ for t in agent.tools_seen_during_chat]
    assert "web_search" in seen
    assert "run_shell" not in seen
    assert "write_file" not in seen

    # After the turn the agent's original toolset is restored intact.
    assert agent.tools == original


@pytest.mark.asyncio
async def test_no_policy_leaves_tools_untouched():
    tools = [_named("run_shell"), _named("web_search")]
    agent = FakeAgent(tools)

    mgr = BotSessionManager(platform="telegram")
    await mgr.chat(agent, "user", "hi", tool_policy=None)

    seen = [t.__name__ for t in agent.tools_seen_during_chat]
    assert seen == ["run_shell", "web_search"]
    assert agent.tools == tools


@pytest.mark.asyncio
async def test_trusted_route_gets_full_toolset():
    tools = [_named("run_shell"), _named("web_search")]
    agent = FakeAgent(tools)

    # A trusted binding yields no policy => full tools.
    policy = RouteBinding(agent="a", trust="trusted").tool_policy()
    assert policy is None

    mgr = BotSessionManager(platform="telegram")
    await mgr.chat(agent, "operator", "do it", tool_policy=policy)

    seen = [t.__name__ for t in agent.tools_seen_during_chat]
    assert "run_shell" in seen


@pytest.mark.asyncio
async def test_tools_restored_even_when_chat_raises():
    class BoomAgent(FakeAgent):
        def chat(self, prompt):
            raise RuntimeError("boom")

    tools = [_named("run_shell"), _named("web_search")]
    agent = BoomAgent(tools)
    original = list(agent.tools)

    policy = RouteBinding(agent="a", trust="untrusted").tool_policy()
    mgr = BotSessionManager(platform="telegram")

    with pytest.raises(RuntimeError):
        await mgr.chat(agent, "stranger", "hello", tool_policy=policy)

    # Original tools restored despite the failure mid-turn.
    assert agent.tools == original
