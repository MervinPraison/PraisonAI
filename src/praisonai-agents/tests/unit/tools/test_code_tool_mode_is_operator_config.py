"""The model cannot choose or weaken how its code runs.

The execution mode is operator configuration (``ExecutionConfig(code_mode=...)``).
``execute_code`` used to take ``sandbox_mode``, and the model saw it in the tool
schema, so a tool call could pick in-process execution, which has no timeout.
"""

import importlib
import inspect
import warnings

import pytest

from praisonaiagents.tools.python_tools import build_code_execution_tools, execute_code
from praisonaiagents.tools.schema import build_tool_definition

MODE_PARAMS = {"sandbox_mode", "sandbox", "code_mode", "execution_mode", "isolation",
               "globals_dict", "locals_dict"}


def _model_params(func):
    return set(build_tool_definition(func)["function"]["parameters"]["properties"])


def _model_tools():
    """Every tool the model can be given by name, plus every code-execution tool."""
    from praisonaiagents import tools as tools_pkg

    found = []
    for name, (module, _attr) in tools_pkg.TOOL_MAPPINGS.items():
        try:
            obj = getattr(importlib.import_module(module, tools_pkg.__name__), _attr or name)
        except Exception:  # optional dependency missing
            continue
        if inspect.isfunction(obj) or inspect.ismethod(obj):
            found.append((name, obj))
    for mode in ("safe", "unsafe", "isolated"):
        for timeout in (30, 5):
            (tool,) = build_code_execution_tools(code_mode=mode, timeout=timeout)
            found.append((f"{mode}/{timeout}", tool))
    return found


def test_no_model_tool_schema_has_an_execution_mode_parameter():
    tools = _model_tools()
    assert any(name == "execute_code" for name, _ in tools)
    leaks = {name: sorted(_model_params(f) & MODE_PARAMS) for name, f in tools}
    assert {k: v for k, v in leaks.items() if v} == {}


@pytest.mark.parametrize("timeout", [30, 5])
def test_safe_mode_tool_takes_only_code(timeout):
    (tool,) = build_code_execution_tools(code_mode="safe", timeout=timeout)
    assert tool.__name__ == "execute_code"
    assert list(inspect.signature(tool).parameters) == ["code"]


def test_tool_call_asking_for_direct_mode_still_runs_in_the_sandbox(monkeypatch):
    calls = []
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")
    import praisonaiagents.tools.python_tools as pt
    monkeypatch.setattr(pt, "_execute_code_direct", lambda *a, **k: calls.append("direct"))
    monkeypatch.setattr(pt, "_execute_code_sandboxed",
                        lambda code, timeout, size: calls.append(("sandbox", timeout)) or {})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        execute_code("while True: pass", sandbox_mode="direct", timeout=5)
    assert calls == [("sandbox", 5)]
    assert any(issubclass(w.category, DeprecationWarning) for w in caught)


def test_unknown_keyword_is_still_an_error(monkeypatch):
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")
    with pytest.raises(TypeError):
        execute_code("1", bogus=1)


@pytest.mark.parametrize("args,kwargs,expected_timeout", [
    (("print(1)", None, None, 5), {}, 5),           # the old positional order still works
    (("print(1)",), {"timeout": 7}, 7),
])
def test_old_positional_order_still_works(monkeypatch, args, kwargs, expected_timeout):
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")
    import praisonaiagents.tools.python_tools as pt
    seen = []
    monkeypatch.setattr(pt, "_execute_code_sandboxed", lambda code, timeout, size: seen.append(timeout) or {})
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)  # None/defaults do not warn
        execute_code(*args, **kwargs)
    assert seen == [expected_timeout]


def test_code_agent_in_process_mode_still_asks_for_approval(monkeypatch):
    import praisonaiagents.approval as approval
    import praisonaiagents.tools.python_tools as pt
    from praisonaiagents.agent.code_agent import CodeAgent

    monkeypatch.delenv("PRAISONAI_AUTO_APPROVE", raising=False)
    ran = []
    monkeypatch.setattr(pt, "_execute_code_direct", lambda code, **k: ran.append(code) or {})

    async def deny(name, arguments):
        return approval.ApprovalDecision(approved=False, reason="denied in test")

    monkeypatch.setattr(approval, "request_approval", deny)
    agent = CodeAgent(name="c", code={"sandbox": False}, verbose=False)
    with pytest.raises(PermissionError):
        agent._execute_python("print('in-process approval probe')")
    assert ran == []


def test_code_agent_keeps_its_operator_chosen_direct_mode(monkeypatch):
    monkeypatch.setenv("PRAISONAI_AUTO_APPROVE", "true")
    import praisonaiagents.tools.python_tools as pt
    from praisonaiagents.agent.code_agent import CodeAgent

    calls = []
    monkeypatch.setattr(pt, "_execute_code_direct",
                        lambda code, **k: calls.append("direct") or {"success": True, "stdout": ""})
    monkeypatch.setattr(pt, "_execute_code_sandboxed",
                        lambda *a, **k: calls.append("sandbox") or {"success": True, "stdout": ""})
    agent = CodeAgent(name="c", code={"sandbox": False}, verbose=False)
    agent._execute_python("print(1)")
    assert calls == ["direct"]
