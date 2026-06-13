"""Regression tests for CLI run session continuity."""

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from praisonaiagents import Agent, MemoryConfig


def test_agent_rejects_resume_session_kwarg():
    """Agent must not accept the invalid resume_session parameter."""
    with pytest.raises(TypeError, match="resume_session"):
        Agent(name="RunAgent", resume_session="abc123")


def test_apply_cli_session_continuity_restores_project_history():
    """Project-scoped history must be restored into the agent chat_history."""
    from praisonai.cli.state.project_sessions import (
        apply_cli_session_continuity,
        get_project_session_store,
    )

    with tempfile.TemporaryDirectory() as tmp:
        project_path = Path(tmp)
        store = get_project_session_store(str(project_path))
        session_id = "continuity-test-session"
        store.add_user_message(session_id, "remember the code is 42")
        store.add_assistant_message(session_id, "Got it, the code is 42.")

        agent = Agent(name="RunAgent")

        apply_cli_session_continuity(agent, session_id, project_path=str(project_path))

        assert agent._session_store.session_dir == store.session_dir
        assert agent._session_id == session_id
        assert len(agent.chat_history) == 2
        assert agent.chat_history[0]["content"] == "remember the code is 42"
        assert agent._auto_save_last_index == 2


def test_handle_direct_prompt_wires_project_session(monkeypatch):
    """handle_direct_prompt must wire resume_session to the project store."""
    from praisonai.cli.main import PraisonAI

    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            self.chat_history = []
            self._session_store = None
            self._session_id = None
            self.auto_save = None
            self._auto_save_last_index = 0
            captured["agent_config"] = kwargs

        def start(self, prompt):
            captured["prompt"] = prompt
            return "ok"

    monkeypatch.setattr("praisonaiagents.Agent", FakeAgent)
    monkeypatch.setattr(
        "praisonai.cli.state.project_sessions.apply_cli_session_continuity",
        lambda agent, session_id, project_path=None: captured.setdefault(
            "continuity", session_id
        ),
    )
    monkeypatch.setattr(
        "praisonai.cli.main.PraisonAI._execute_agent_with_budget_handling",
        lambda self, agent, method, prompt: agent.start(prompt),
    )
    monkeypatch.setattr(
        "praisonai.cli.main.PraisonAI._resolve_display_mode",
        lambda self: "quiet",
    )
    monkeypatch.setattr(
        "praisonai.cli.main.PraisonAI._rewrite_query_if_enabled",
        lambda self, prompt: prompt,
    )
    monkeypatch.setattr(
        "praisonai.cli.main.PraisonAI._expand_prompt_if_enabled",
        lambda self, prompt: prompt,
    )
    monkeypatch.setattr("praisonai.cli.main.PRAISONAI_AVAILABLE", True)

    praison = PraisonAI()
    args = SimpleNamespace(
        profile=False,
        workflow=None,
        no_rules=True,
        verbose=0,
        llm=None,
        memory=False,
        auto_save="saved-session",
        resume_session="saved-session",
        history=None,
        tools=None,
        toolset=None,
        no_tools=True,
        web_search=False,
        web_fetch=False,
        prompt_caching=False,
        autonomy=None,
        approval=None,
        router=False,
        metrics=False,
        telemetry=False,
        mcp=None,
        auto_rag=False,
        image=None,
        image_generate=False,
        cli_backend=None,
        flow_display=False,
        planning=False,
        query_rewrite=False,
        expand_prompt=False,
        tool_timeout=None,
        tool_retry_attempts=1,
        rewrite_tools=None,
        expand_tools=None,
        planning_tools=None,
    )
    praison.args = args

    result = praison.handle_direct_prompt("follow up question")

    assert result == "ok"
    memory = captured["agent_config"]["memory"]
    assert isinstance(memory, MemoryConfig)
    assert memory.session_id == "saved-session"
    assert memory.history is True
    assert captured["continuity"] == "saved-session"
