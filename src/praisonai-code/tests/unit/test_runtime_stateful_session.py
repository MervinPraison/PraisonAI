"""Warm runtime hosts stateful, per-session agents (Issue #3463).

A `--continue`/`--session` run must attach to a warm, per-session agent whose
history is retained across turns, while the anonymous (no-session) path stays
isolated by clearing history each call.
"""

from __future__ import annotations

from unittest.mock import patch

from praisonai_code.runtime.server import WarmRuntime


class _FakeAgent:
    """Minimal Agent stand-in recording history and start() calls."""

    def __init__(self, **kwargs):
        self.chat_history = []
        self.calls = []

    def start(self, prompt):
        self.calls.append(prompt)
        # Emulate an agent appending a user turn + assistant reply.
        self.chat_history.append({"role": "user", "content": prompt})
        self.chat_history.append({"role": "assistant", "content": f"re: {prompt}"})
        return f"re: {prompt}"

    def _replace_chat_history(self, new_history):
        self.chat_history = list(new_history)


def test_session_run_reuses_same_warm_agent_and_retains_history():
    runtime = WarmRuntime(model="test-model")

    with patch("praisonaiagents.Agent", _FakeAgent), patch(
        "praisonai_code.cli.state.project_sessions.apply_cli_session_continuity",
        lambda *a, **k: None,
    ):
        runtime.run("first", session_id="s1")
        runtime.run("second", session_id="s1")

    agent = runtime._session_agents["s1"]
    assert agent.calls == ["first", "second"]
    # History is retained across turns (stateful), not cleared.
    assert {"role": "user", "content": "first"} in agent.chat_history
    assert {"role": "user", "content": "second"} in agent.chat_history


def test_distinct_sessions_do_not_share_agents():
    runtime = WarmRuntime(model="test-model")

    with patch("praisonaiagents.Agent", _FakeAgent), patch(
        "praisonai_code.cli.state.project_sessions.apply_cli_session_continuity",
        lambda *a, **k: None,
    ):
        runtime.run("a", session_id="s1")
        runtime.run("b", session_id="s2")

    assert runtime._session_agents["s1"] is not runtime._session_agents["s2"]
    assert runtime._session_agents["s1"].calls == ["a"]
    assert runtime._session_agents["s2"].calls == ["b"]


def test_anonymous_path_clears_history_each_call():
    runtime = WarmRuntime(model="test-model")

    with patch("praisonaiagents.Agent", _FakeAgent):
        runtime.run("first")
        runtime.run("second")

    agent = runtime._agents[runtime._agent_key(None)]
    # Anonymous agent is stateless: history cleared after each call.
    assert agent.chat_history == []
    assert agent.calls == ["first", "second"]


def test_failed_session_turn_evicts_warm_agent():
    runtime = WarmRuntime(model="test-model")

    class _BoomAgent(_FakeAgent):
        def start(self, prompt):
            raise RuntimeError("boom")

    with patch("praisonaiagents.Agent", _BoomAgent), patch(
        "praisonai_code.cli.state.project_sessions.apply_cli_session_continuity",
        lambda *a, **k: None,
    ):
        try:
            runtime.run("x", session_id="s1")
        except RuntimeError:
            pass

    assert "s1" not in runtime._session_agents
