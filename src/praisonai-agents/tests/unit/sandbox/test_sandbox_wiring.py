"""Regression tests for `Agent(sandbox=...)` actually providing isolation.

Every test here corresponds to a shipped defect where the agent *looked*
sandboxed and was not. For a security setting, silently doing less than the
docs promise is the worst failure mode, so these assert behaviour, not config.
"""

import os


import pytest

from praisonaiagents import Agent


def _tool_names(agent):
    return [getattr(t, "__name__", getattr(t, "name", None)) for t in (agent.tools or [])]


def a_tool(x: str) -> str:
    """A plain user tool."""
    return x


# ── sandbox= must give the model sandboxed execution tools ───────────────────
def test_sandbox_attaches_code_execution_tools():
    """Previously `sandbox=` built a config nothing read: no tools were added."""
    agent = Agent(name="T", instructions="x", sandbox=True)
    names = _tool_names(agent)
    assert "execute_python_code" in names
    assert "execute_shell_command" in names


def test_sandbox_preserves_user_tools():
    agent = Agent(name="T", instructions="x", tools=[a_tool], sandbox=True)
    names = _tool_names(agent)
    assert "a_tool" in names, "user tools must survive"
    assert "execute_python_code" in names


def test_no_sandbox_adds_nothing():
    """The default path must be completely unchanged."""
    agent = Agent(name="T", instructions="x", tools=[a_tool])
    assert _tool_names(agent) == ["a_tool"]
    assert agent.sandbox_config is None


def test_sandbox_does_not_duplicate_tools_on_name_clash():
    def execute_python_code(code: str) -> str:
        """User-supplied tool with a colliding name."""
        return "user"

    agent = Agent(name="T", instructions="x", tools=[execute_python_code], sandbox=True)
    assert _tool_names(agent).count("execute_python_code") == 1


# ── the tools must genuinely isolate ─────────────────────────────────────────
def test_sandboxed_code_runs_out_of_process():
    """The point of the feature: not the same interpreter as the caller."""
    agent = Agent(name="T", instructions="x", sandbox=True)
    run = next(t for t in agent.tools if getattr(t, "__name__", "") == "execute_python_code")
    out = str(run("import os; print(os.getpid())"))
    child_pid = int(out.strip().splitlines()[-1])
    assert child_pid != os.getpid(), "code executed in the host process — not sandboxed"


def test_security_warning_does_not_break_execution():
    """`metadata` was forwarded into SandboxProtocol.execute(), which has no such
    parameter — so flagged code raised TypeError instead of running sandboxed."""
    agent = Agent(name="T", instructions="x", sandbox=True)
    run = [t for t in agent.tools if getattr(t, "__name__", "") == "execute_python_code"][0]
    out = str(run("import os\nprint('flagged-ok')"))  # `import os` trips the checker
    assert "flagged-ok" in out
    assert "TypeError" not in out


# ── clone must not silently drop isolation ───────────────────────────────────
def test_clone_keeps_sandbox():
    """clone_for_channel() read `_sandbox_config`, which is never assigned, so
    every clone silently ran unisolated."""
    agent = Agent(name="T", instructions="x", sandbox=True)
    clone = agent.clone_for_channel()
    assert agent.sandbox_config is not None
    assert getattr(clone, "sandbox_config", None) is not None, "clone lost its sandbox"


def test_clone_regenerates_clone_bound_sandbox_tools():
    """The generated tools close over the source agent. If the clone merely
    copied them, invoking a clone tool would run through the *source* agent's
    SandboxManager — sharing execution state across channels. The clone must
    own its execution tools."""
    agent = Agent(name="T", instructions="x", sandbox=True)
    clone = agent.clone_for_channel()

    src_run = next(t for t in agent.tools if getattr(t, "__name__", "") == "execute_python_code")
    clone_run = next(t for t in clone.tools if getattr(t, "__name__", "") == "execute_python_code")

    assert clone_run is not src_run, "clone reused the source-bound execution tool"

    src_mgr = agent.get_sandbox_manager()
    clone_mgr = clone.get_sandbox_manager()
    assert clone_mgr is not src_mgr, "clone shares the source agent's SandboxManager"


# ── conflicting settings must not be silent ──────────────────────────────────
class _FakeBackend:
    async def execute(self, prompt, **kwargs):
        return ""


# Use pytest's warning fixtures rather than warnings.catch_warnings():
# catch_warnings() restores filters but NOT __warningregistry__, so emitting a
# warning here would mark that site "already shown" and silently break
# unrelated deprecation tests later in the same session.
def test_sandbox_plus_backend_warns():
    """A managed backend takes the whole turn, making sandbox= inert. Say so."""
    with pytest.warns(FutureWarning, match="sandbox") as caught:
        Agent(name="T", instructions="x", sandbox=True, backend=_FakeBackend())

    assert any("backend" in str(w.message) for w in caught), (
        "the warning must name backend= as the reason sandbox= is ignored"
    )


def test_backend_alone_does_not_warn(recwarn):
    Agent(name="T", instructions="x", backend=_FakeBackend())
    assert not [
        w for w in recwarn
        if issubclass(w.category, FutureWarning) and "sandbox" in str(w.message)
    ]


# ── docstrings must not promise unimplemented protection ─────────────────────
def test_inert_fields_are_documented_as_inert():
    """These fields have zero consumers; their docs must not imply safety."""
    import inspect

    from praisonaiagents.agent import autonomy
    from praisonaiagents.config import feature_configs

    assert "NOT IMPLEMENTED" in (autonomy.AutonomyConfig.__doc__ or ""), (
        "AutonomyConfig.sandbox documented auto-enabling isolation that does not exist"
    )
    src = inspect.getsource(feature_configs.ExecutionConfig)
    idx = src.find("code_sandbox_mode")
    assert "NOT IMPLEMENTED" in src[max(0, idx - 400):idx], (
        "code_sandbox_mode is inert and must be labelled as such"
    )
