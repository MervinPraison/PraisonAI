"""X-13: turning code execution on under a policy that blocks it says so.

``Agent(execution=ExecutionConfig(code_execution=True))`` added
``execute_code`` to ``agent.tools``, but the default tool-safety preset denies
it, so the model was never offered the tool and nothing said why. The default
policy is unchanged; the agent now warns once, naming the block and the
settings that allow it.
"""

import warnings

import pytest

from praisonaiagents import Agent, ExecutionConfig


def _build(monkeypatch, tmp_path, **kwargs):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-local-fake")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.delenv("PRAISONAI_TOOL_SAFETY", raising=False)
    monkeypatch.setattr(Agent, "_is_interactive_session", lambda self: False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        agent = Agent(name="c", instructions="x", llm="gpt-4o-mini", **kwargs)
    return agent, [str(w.message) for w in caught if "execute_code" in str(w.message)]


def test_default_policy_block_is_announced(monkeypatch, tmp_path):
    agent, msgs = _build(monkeypatch, tmp_path, execution=ExecutionConfig(code_execution=True))
    assert "execute_code" in agent._perm_deny  # the default policy is not weakened
    assert len(msgs) == 1
    assert "PRAISONAI_TOOL_SAFETY" in msgs[0] and "approval=True" in msgs[0]


@pytest.mark.parametrize("kwargs", [
    {"approval": True},
    {"approval": "full"},
], ids=["approval_true", "approval_full"])
def test_no_warning_when_the_policy_allows_it(monkeypatch, tmp_path, kwargs):
    agent, msgs = _build(monkeypatch, tmp_path, execution=ExecutionConfig(code_execution=True), **kwargs)
    assert "execute_code" not in agent._perm_deny
    assert msgs == []


def test_no_warning_without_code_execution(monkeypatch, tmp_path):
    _, msgs = _build(monkeypatch, tmp_path)
    assert msgs == []
