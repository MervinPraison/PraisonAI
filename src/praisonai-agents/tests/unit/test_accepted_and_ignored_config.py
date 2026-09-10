"""Regression tests for config knobs that were accepted and then ignored.

Each test here fails on the pre-fix code:

* ``HooksConfig(on_step=..., on_tool_call=...)`` -- both callbacks were stored
  and never invoked, while the TypeError for an unknown key advertised them.
* ``ExecutionConfig(code_execution=True)`` -- set ``allow_code_execution`` and
  produced no tool, so the agent gained no capability; ``code_mode`` was a
  security-shaped label with no behaviour behind it.
* ``AgentTeam(execution=ExecutionConfig(...))`` -- the top-level-exported
  single-agent config was resolved against ``MultiAgentExecutionConfig`` and
  dropped whole, silently, including the ``max_iter`` both classes define.
"""

import warnings

import pytest

from praisonaiagents import Agent, AgentTeam, ExecutionConfig
from praisonaiagents.config import HooksConfig
from praisonaiagents.config.feature_configs import MultiAgentExecutionConfig


@pytest.fixture(autouse=True)
def _restore_approval_state():
    """Keep approval backend + context from leaking between tests.

    Several tests here install an ``AutoApproveBackend`` to exercise the
    approval-gated ``execute_code`` tool. Without this the backend (and any
    sticky per-tool approval) would bleed into later tests in the same process
    and silently auto-approve their gates -- violating the deterministic-tests
    invariant.
    """
    from praisonaiagents.approval import get_approval_registry, clear_approval_context

    registry = get_approval_registry()
    previous = registry.get_backend()
    try:
        yield
    finally:
        registry.set_backend(previous)
        clear_approval_context()


# ---------------------------------------------------------------------------
# 1. HooksConfig callbacks actually fire
# ---------------------------------------------------------------------------

def _adder(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


def test_hooks_config_on_tool_call_fires_on_every_tool():
    seen = []
    agent = Agent(
        name="HookToolAgent",
        instructions="test",
        tools=[_adder],
        hooks=HooksConfig(on_tool_call=seen.append),
    )

    assert agent.execute_tool("_adder", {"a": 1, "b": 2}) == 3

    assert len(seen) == 1, "on_tool_call was never invoked"
    assert seen[0].tool_name == "_adder"
    assert seen[0].arguments == {"a": 1, "b": 2}


def test_hooks_config_on_step_fires_once_per_model_call():
    seen = []
    agent = Agent(
        name="HookStepAgent",
        instructions="test",
        hooks=HooksConfig(on_step=seen.append),
    )
    agent._chat_completion_with_retry_core = lambda *a, **k: "hello"

    out = agent._chat_completion_with_retry([{"role": "user", "content": "hi"}])

    assert out == "hello", "on_step must not change the model result"
    assert len(seen) == 1, "on_step was never invoked"
    assert seen[0].content == "hello"


def test_hooks_config_middleware_still_works_alongside_callbacks():
    from praisonaiagents.hooks import before_tool

    order = []

    @before_tool
    def mw(request):
        order.append("middleware")
        return request

    agent = Agent(
        name="HookBothAgent",
        instructions="test",
        tools=[_adder],
        hooks=HooksConfig(on_tool_call=lambda r: order.append("on_tool_call"), middleware=[mw]),
    )
    agent.execute_tool("_adder", {"a": 1, "b": 1})

    assert order == ["middleware", "on_tool_call"]


# ---------------------------------------------------------------------------
# 2. ExecutionConfig(code_execution=True) grants a real capability
# ---------------------------------------------------------------------------

def _tool_names(agent):
    return [getattr(t, "__name__", None) for t in (agent.tools or [])]


def test_code_execution_flag_adds_a_code_tool():
    plain = Agent(name="NoCode", instructions="test")
    coder = Agent(
        name="Coder",
        instructions="test",
        execution=ExecutionConfig(code_execution=True),
    )

    assert _tool_names(plain) == []
    assert "execute_code" in _tool_names(coder), (
        "ExecutionConfig(code_execution=True) produced no code tool"
    )
    assert coder.allow_code_execution is True


def test_code_execution_tool_is_approval_gated_as_critical():
    from praisonaiagents.approval import get_risk_level

    coder = Agent(
        name="CoderGated",
        instructions="test",
        execution=ExecutionConfig(code_execution=True),
    )
    tool = next(t for t in coder.tools if getattr(t, "__name__", None) == "execute_code")
    assert getattr(tool, "_requires_approval", False) or get_risk_level("execute_code") == "critical"


def test_code_mode_changes_what_the_tool_can_do():
    """'unsafe' must mean something: in-process, with the agent's tools reachable."""
    from praisonaiagents.approval import (
        get_approval_registry,
        AutoApproveBackend,
        clear_approval_context,
    )
    from praisonaiagents.tools.registry import get_registry

    def code_mode_probe() -> str:
        """Return a marker string."""
        return "PROBE-OK"

    _probe_tool_name = "code_mode_probe"
    get_registry().register(code_mode_probe)
    previous = get_approval_registry().get_backend()
    get_approval_registry().set_backend(AutoApproveBackend())
    try:
        safe = Agent(
            name="SafeCoder",
            instructions="test",
            tools=[code_mode_probe],
            execution=ExecutionConfig(code_execution=True),
        )
        unsafe = Agent(
            name="UnsafeCoder",
            instructions="test",
            # The tool is GRANTED to the agent; code mode may only reach the
            # agent's own tools, never the process-global registry.
            tools=[code_mode_probe],
            execution=ExecutionConfig(
                code_execution=True,
                code_mode="unsafe",
                code_tools=True,
                code_tools_allow=["code_mode_probe"],
            ),
        )
        code = "print(code_mode_probe())"
        safe_exec = next(t for t in safe.tools if getattr(t, "__name__", None) == "execute_code")
        unsafe_exec = next(t for t in unsafe.tools if getattr(t, "__name__", None) == "execute_code")
        safe_result = safe_exec(code)
        unsafe_result = unsafe_exec(code)
    finally:
        get_approval_registry().set_backend(previous)
        clear_approval_context()
        # The tool registry is process-global. Leaving these probe tools in it
        # changed what later tests saw when they enumerated or dispatched
        # tools -- test_presentation_poll, test_mixed_tools_list_resolution and
        # test_code_tools_bridge all pass alone and failed after this file ran.
        get_registry().unregister(_probe_tool_name)
        # Approvals granted here are remembered by the process-global registry,
        # so a later test asserting "every call is gated" saw one of its calls
        # already approved (test_code_tools_bridge::
        # test_approval_gate_required_for_every_call counted 1 instead of 2).
        get_approval_registry().clear_approved()

    assert unsafe_result["success"] is True
    assert "PROBE-OK" in unsafe_result["stdout"]
    # Safe mode runs in a subprocess where the parent's tools do not exist.
    assert "PROBE-OK" not in (safe_result.get("stdout") or "")


def test_unsafe_code_mode_cannot_reach_tools_the_agent_was_not_granted():
    """A globally-registered tool NOT in the agent's tools must be unreachable.

    code_tools_allow is a per-run filter, not a grant: the tool must also be one
    the agent itself holds, or unsafe code mode would escape the agent's tool
    boundary and reach plugin/entry-point tools it was never given.
    """
    from praisonaiagents.approval import (
        get_approval_registry,
        AutoApproveBackend,
        clear_approval_context,
    )
    from praisonaiagents.tools.registry import get_registry

    def ungranted_global_tool() -> str:
        """Registered globally but never handed to the agent."""
        return "LEAK"

    _probe_tool_name = "ungranted_global_tool"
    get_registry().register(ungranted_global_tool)
    previous = get_approval_registry().get_backend()
    get_approval_registry().set_backend(AutoApproveBackend())
    try:
        agent = Agent(
            name="ScopedCoder",
            instructions="test",
            # NB: ungranted_global_tool is NOT in tools=[...]
            execution=ExecutionConfig(
                code_execution=True,
                code_mode="unsafe",
                code_tools=True,
                code_tools_allow=["ungranted_global_tool"],
            ),
        )
        execute = next(
            t for t in agent.tools if getattr(t, "__name__", None) == "execute_code"
        )
        result = execute("print(ungranted_global_tool())")
    finally:
        get_approval_registry().set_backend(previous)
        clear_approval_context()
        # The tool registry is process-global. Leaving these probe tools in it
        # changed what later tests saw when they enumerated or dispatched
        # tools -- test_presentation_poll, test_mixed_tools_list_resolution and
        # test_code_tools_bridge all pass alone and failed after this file ran.
        get_registry().unregister(_probe_tool_name)
        # Approvals granted here are remembered by the process-global registry,
        # so a later test asserting "every call is gated" saw one of its calls
        # already approved (test_code_tools_bridge::
        # test_approval_gate_required_for_every_call counted 1 instead of 2).
        get_approval_registry().clear_approved()

    assert result["success"] is False
    assert "LEAK" not in (result.get("stdout") or "")


def test_async_on_step_callback_is_awaited_not_dropped():
    """An async on_step callback must actually run, not be discarded silently."""
    from praisonaiagents.hooks.middleware import as_step_hook

    ran = {"called": False}

    async def on_step(_response):
        ran["called"] = True

    hook = as_step_hook(on_step)
    hook(object())  # sync invocation path (no running loop)
    assert ran["called"] is True


def test_code_execution_runs_a_trailing_expression_exactly_once():
    """exec-then-re-eval used to run a trailing expression statement twice."""
    from praisonaiagents.approval import get_approval_registry, AutoApproveBackend
    from praisonaiagents.tools.python_tools import execute_code, execute_code_with_tools

    from praisonaiagents.approval import clear_approval_context

    registry = get_approval_registry()
    previous = registry.get_backend()
    registry.set_backend(AutoApproveBackend())
    try:
        assert execute_code("print(7)")["stdout"] == "7\n"
        assert execute_code_with_tools("print(7)")["stdout"] == "7\n"
    finally:
        registry.set_backend(previous)
        clear_approval_context()


def test_unknown_code_mode_is_rejected():
    with pytest.raises(ValueError, match="code_mode"):
        Agent(
            name="BadMode",
            instructions="test",
            execution=ExecutionConfig(code_execution=True, code_mode="turbo"),
        )


def test_code_tools_without_unsafe_mode_warns():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Agent(
            name="CodeToolsSafe",
            instructions="test",
            execution=ExecutionConfig(
                code_execution=True, code_tools=True, code_tools_allow=["x"]
            ),
        )
    assert any("code_mode='unsafe'" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# 3. AgentTeam(execution=ExecutionConfig(...)) is no longer swallowed
# ---------------------------------------------------------------------------

def test_team_accepts_single_agent_execution_config_and_warns():
    agent = Agent(name="TeamMember", instructions="test")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        team = AgentTeam(agents=[agent], execution=ExecutionConfig(max_iter=99))

    assert team.max_iter == 99, "max_iter was silently dropped"
    messages = [str(w.message) for w in caught if issubclass(w.category, UserWarning)]
    assert any("MultiAgentExecutionConfig" in m for m in messages), messages


def test_team_keeps_its_retry_default_when_execution_config_untouched():
    """An ExecutionConfig(max_iter=99) must not drag the team's retries down.

    ExecutionConfig.max_retry_limit defaults to 2; MultiAgentExecutionConfig
    .max_retries defaults to 5. Carrying the untouched single-agent default
    would silently reduce team retries, so it must be left alone.
    """
    agent = Agent(name="TeamRetryMember", instructions="test")

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        team = AgentTeam(agents=[agent], execution=ExecutionConfig(max_iter=99))

    default_team = AgentTeam(
        agents=[Agent(name="DefaultRetryMember", instructions="test")],
        execution=MultiAgentExecutionConfig(max_iter=99),
    )
    assert team.max_retries == default_team.max_retries


def test_team_carries_retry_when_explicitly_set():
    agent = Agent(name="ExplicitRetryMember", instructions="test")

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        team = AgentTeam(
            agents=[agent],
            execution=ExecutionConfig(max_iter=7, max_retry_limit=9),
        )

    assert team.max_retries == 9


def test_team_warning_names_the_fields_it_cannot_carry():
    agent = Agent(name="TeamMember2", instructions="test")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        AgentTeam(agents=[agent], execution=ExecutionConfig(max_iter=5, max_rpm=30))

    messages = [str(w.message) for w in caught if issubclass(w.category, UserWarning)]
    assert any("max_rpm" in m for m in messages), messages


def test_team_with_correct_config_does_not_warn():
    agent = Agent(name="TeamMember3", instructions="test")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        team = AgentTeam(agents=[agent], execution=MultiAgentExecutionConfig(max_iter=42))

    assert team.max_iter == 42
    assert not [
        w for w in caught
        if issubclass(w.category, UserWarning) and "MultiAgentExecutionConfig" in str(w.message)
    ]
