"""T-08, agent/tool_execution.py: swallowed failures are logged at debug and
the result is unchanged. Only _remove_circuit_breaker stays silent: it runs
from a weakref.finalize callback.
"""
import ast
import logging
from pathlib import Path

import pytest

import praisonaiagents.agent.tool_execution as te
import praisonaiagents.tools.base as tools_base
import praisonaiagents.tools.registry as tools_registry
from praisonaiagents import Agent


def _boom(*a, **k):
    raise RuntimeError("boom")


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return Agent(name="a", instructions="hi")


def _records(caplog, text):
    return [r for r in caplog.records if text in r.getMessage() and r.exc_info]


def test_only_the_finalizer_stays_silent():
    tree = ast.parse(Path(te.__file__).read_text(encoding="utf-8"))
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    silent = set()
    for n in ast.walk(tree):
        if (isinstance(n, ast.ExceptHandler) and len(n.body) == 1 and isinstance(n.body[0], ast.Pass)
                and (n.type is None or getattr(n.type, "id", None) in ("Exception", "BaseException"))):
            silent.add([f.name for f in funcs if f.lineno <= n.lineno <= f.end_lineno][-1])
    assert silent == {"_remove_circuit_breaker"}


def test_failed_model_view_is_logged_and_full_result_kept(agent, monkeypatch, caplog):
    monkeypatch.setattr(tools_base, "resolve_model_output", _boom)
    with caplog.at_level(logging.DEBUG, logger=te.logger.name):
        assert agent._resolve_model_facing_result("my_tool", "RAW") is None
    assert _records(caplog, "resolve_model_output failed for 'my_tool'")


def test_failed_registry_lookup_is_logged_and_default_kept(agent, monkeypatch, caplog):
    class _Registry:
        get = staticmethod(_boom)

    monkeypatch.setattr(tools_registry, "get_registry", lambda: _Registry())
    monkeypatch.setattr(agent, "_allow_global_tools", True, raising=False)  # ToolConfig(allow_global_tools=True)
    with caplog.at_level(logging.DEBUG, logger=te.logger.name):
        assert agent._is_tool_idempotent("my_tool") is False
        assert agent._tool_declares_not_idempotent("my_tool") is False
    assert len(_records(caplog, "Registry lookup for 'my_tool' failed")) == 2
