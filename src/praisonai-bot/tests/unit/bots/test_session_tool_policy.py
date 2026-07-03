"""Per-route toolset scoping on the bot inbound path (Issue #2298).

Verifies that ``BotSessionManager.chat()`` scopes ``agent.tools`` per a
supplied tool policy for the duration of a turn and restores the agent's
original toolset afterwards, so an untrusted inbound route never advertises
dangerous tools while attended/trusted uses of the same shared agent are
unaffected.
"""

from __future__ import annotations

import pytest

from praisonai_bot.bots._session import BotSessionManager
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
async def test_staged_policy_scopes_when_chat_arg_absent():
    # Discord/Slack routed handlers can't thread tool_policy through the
    # adapter's own chat() call, so they stage it on the session instead.
    tools = [_named("run_shell"), _named("web_search"), _named("delete_file")]
    agent = FakeAgent(tools)
    original = list(agent.tools)

    policy = RouteBinding(agent="a", trust="untrusted").tool_policy()
    mgr = BotSessionManager(platform="discord")
    mgr.set_pending_tool_policy(agent, policy)

    # No explicit tool_policy arg — the staged policy must apply.
    await mgr.chat(agent, "stranger", "hello")

    seen = [t.__name__ for t in agent.tools_seen_during_chat]
    assert "web_search" in seen
    assert "run_shell" not in seen
    assert "delete_file" not in seen
    assert agent.tools == original


@pytest.mark.asyncio
async def test_staged_policy_consumed_once_then_cleared():
    tools = [_named("run_shell"), _named("web_search")]
    agent = FakeAgent(tools)

    policy = RouteBinding(agent="a", trust="untrusted").tool_policy()
    mgr = BotSessionManager(platform="discord")
    mgr.set_pending_tool_policy(agent, policy)

    # First turn: staged untrusted scope applies.
    await mgr.chat(agent, "stranger", "hi")
    assert "run_shell" not in [t.__name__ for t in agent.tools_seen_during_chat]

    # Second turn with nothing staged: full toolset, no stale leak.
    await mgr.chat(agent, "stranger", "again")
    assert "run_shell" in [t.__name__ for t in agent.tools_seen_during_chat]


@pytest.mark.asyncio
async def test_explicit_policy_wins_over_staged_policy():
    # An explicit (non-None) tool_policy argument takes precedence over a
    # staged one; the staged policy is still consumed so it can't leak later.
    tools = [_named("run_shell"), _named("web_search"), _named("delete_file")]
    agent = FakeAgent(tools)

    # Stage an allow-only "web_search" policy, but pass an explicit untrusted
    # one — the explicit argument must win for this turn.
    staged = RouteBinding(agent="a", allow_tools=["web_search"]).tool_policy()
    explicit = RouteBinding(agent="a", trust="untrusted").tool_policy()
    mgr = BotSessionManager(platform="discord")
    mgr.set_pending_tool_policy(agent, staged)

    await mgr.chat(agent, "operator", "do it", tool_policy=explicit)
    seen = [t.__name__ for t in agent.tools_seen_during_chat]
    # Explicit untrusted scope removed run_shell/delete_file but kept web_search.
    assert seen == ["web_search"]

    # Staged policy was consumed (not left dangling), so a later unstaged turn
    # with no explicit policy is the full toolset.
    await mgr.chat(agent, "operator", "more")
    assert "run_shell" in [t.__name__ for t in agent.tools_seen_during_chat]


@pytest.mark.asyncio
async def test_staged_untrusted_not_bypassed_by_implicit_none():
    # Fail-closed: a routed turn that stages an untrusted policy must NOT fall
    # through to the full toolset just because no explicit policy is passed.
    tools = [_named("run_shell"), _named("web_search")]
    agent = FakeAgent(tools)

    untrusted = RouteBinding(agent="a", trust="untrusted").tool_policy()
    mgr = BotSessionManager(platform="discord")
    mgr.set_pending_tool_policy(agent, untrusted)

    await mgr.chat(agent, "stranger", "do it")
    assert "run_shell" not in [t.__name__ for t in agent.tools_seen_during_chat]


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
