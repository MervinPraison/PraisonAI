"""T-08, agent/agent.py: swallowed failures are logged at debug and the result
is unchanged. Two blocks stay silent: one in __init__ (inside the LLM-selection
code that T-05 moves next) and _cleanup_server_registrations' fallback for a
failed log call, which runs from finalizers (_release_approval_scope).
"""
import ast
import logging
from pathlib import Path

import pytest

import praisonaiagents.agent.agent as agent_mod
from praisonaiagents import Agent


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return Agent(name="a", instructions="hi")


def _records(caplog, text):
    return [r for r in caplog.records if text in r.getMessage() and r.exc_info]


def test_only_known_silent_handlers_remain():
    tree = ast.parse(Path(agent_mod.__file__).read_text(encoding="utf-8"))
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    silent = []
    for n in ast.walk(tree):
        if (isinstance(n, ast.ExceptHandler) and len(n.body) == 1 and isinstance(n.body[0], ast.Pass)
                and (n.type is None or getattr(n.type, "id", None) in ("Exception", "BaseException"))):
            silent.append([f.name for f in funcs if f.lineno <= n.lineno <= f.end_lineno][-1])
    assert sorted(silent) == ["__init__", "_cleanup_server_registrations"]


def test_clone_memory_fallbacks_are_logged_and_memory_shared(agent, caplog):
    class _Mem:
        cfg = None

        def __deepcopy__(self, memo):
            raise RuntimeError("no copy")

    mem = _Mem()
    agent._memory_instance = mem
    with caplog.at_level(logging.DEBUG, logger=agent_mod.logger.name):
        assert agent._isolated_memory_for_clone() is mem  # as on main
    assert _records(caplog, "deepcopy of _Mem failed")


def test_reasoning_effort_not_forwarded_is_logged(agent, caplog):
    class _Backend:
        def __setattr__(self, key, value):
            if key == "reasoning_effort":
                raise RuntimeError("read-only")
            object.__setattr__(self, key, value)

    agent._llm_instance = _Backend()
    with caplog.at_level(logging.DEBUG, logger=agent_mod.logger.name):
        agent.reasoning_effort = "low"
    assert agent.reasoning_effort == "low"  # as on main
    assert _records(caplog, "Could not set reasoning_effort on _Backend")
