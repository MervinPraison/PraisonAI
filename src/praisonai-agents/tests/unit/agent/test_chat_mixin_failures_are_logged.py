"""T-08, agent/chat_mixin.py: swallowed failures are logged at debug and the
result is unchanged (no block in this file runs from a finalizer).
"""
import ast
import logging
import types
from pathlib import Path

import pytest

import praisonaiagents.agent.chat_mixin as cm
from praisonaiagents import Agent


def _boom():
    raise RuntimeError("boom")


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    a = Agent(name="a", instructions="hi")
    a.execution = types.SimpleNamespace(
        resolved_max_steps=_boom, resolved_max_tool_calls=_boom,
        max_steps=7, max_tool_calls_per_turn=4,
    )
    return a


def _records(caplog, text):
    return [r for r in caplog.records if text in r.getMessage() and r.exc_info]


def test_no_silent_broad_handlers_left():
    tree = ast.parse(Path(cm.__file__).read_text(encoding="utf-8"))
    silent = [n.lineno for n in ast.walk(tree)
              if isinstance(n, ast.ExceptHandler) and len(n.body) == 1 and isinstance(n.body[0], ast.Pass)
              and (n.type is None or getattr(n.type, "id", None) in ("Exception", "BaseException"))]
    assert silent == []


def test_failing_step_resolver_is_logged_and_max_steps_used(agent, caplog):
    with caplog.at_level(logging.DEBUG, logger=cm.logger.name):
        assert agent._resolve_max_steps(10) == 7
    assert _records(caplog, "resolved_max_steps() failed")


def test_failing_tool_call_resolver_is_logged_and_field_used(agent, caplog):
    with caplog.at_level(logging.DEBUG, logger=cm.logger.name):
        assert agent._resolve_max_tool_calls(10) == 4
    assert _records(caplog, "resolved_max_tool_calls() failed")


def test_structured_validation_failure_logs_no_reply_values(agent, caplog):
    from pydantic import BaseModel

    class Reply(BaseModel):
        count: int

    secret = "private-customer-4111111111111111"
    with caplog.at_level(logging.DEBUG, logger=cm.logger.name):
        result = agent._coerce_structured_output('{"count": "%s"}' % secret, Reply)
    assert result == '{"count": "%s"}' % secret
    msgs = [r for r in caplog.records if "model_validate" in r.getMessage()]
    assert msgs and all(r.exc_info is None for r in msgs)
    assert secret not in caplog.text
