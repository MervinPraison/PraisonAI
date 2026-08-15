"""Contract tests for `Agent(sandbox=...)`.

History worth keeping: an earlier version of this file asserted
`child_pid != os.getpid()` and treated that as proof of isolation. That is a
false equivalence -- a separate process is not a security boundary -- and it
let a privilege-escalating change ship on a green suite. These tests assert the
*contract* instead: `sandbox=` configures isolation for explicit execute_code()
calls, and never silently grants the model new capabilities.
"""

import pytest

from praisonaiagents import Agent


def _tool_names(agent):
    return [getattr(t, "__name__", getattr(t, "name", None)) for t in (agent.tools or [])]


def a_tool(x: str) -> str:
    """A plain user tool."""
    return x


# ── sandbox= must not grant capabilities ─────────────────────────────────────
def test_sandbox_does_not_inject_tools():
    """`sandbox=` is a restriction; it must never add tools the caller didn't ask for."""
    plain = Agent(name="A", instructions="x", tools=[a_tool])
    boxed = Agent(name="B", instructions="x", tools=[a_tool], sandbox=True)
    assert _tool_names(boxed) == _tool_names(plain) == ["a_tool"]


def test_sandbox_does_not_bypass_approval_presets():
    """Regression: approval='read_only' exposed no tools, but adding sandbox=True
    exposed two ungated arbitrary-code-execution tools, because the injected
    names are absent from the approval registry's dangerous-tool presets."""
    read_only = Agent(name="A", instructions="x", approval="read_only")
    with_sandbox = Agent(name="B", instructions="x", approval="read_only", sandbox=True)
    assert _tool_names(with_sandbox) == _tool_names(read_only), (
        "sandbox= must not widen what an approval preset exposes"
    )


def test_sandbox_still_configures_explicit_execution():
    """The documented meaning of sandbox=: configure agent.execute_code()."""
    agent = Agent(name="T", instructions="x", sandbox=True)
    assert agent.has_sandbox
    assert agent.sandbox_config is not None
    assert agent.get_sandbox_manager() is not None


def test_no_sandbox_leaves_agent_untouched():
    agent = Agent(name="T", instructions="x", tools=[a_tool])
    assert _tool_names(agent) == ["a_tool"]
    assert agent.sandbox_config is None
    assert agent.has_sandbox is False


# ── the metadata fix (kept from the reverted change) ─────────────────────────
def test_security_warning_does_not_break_execution():
    """`metadata` was forwarded into SandboxProtocol.execute(), which has no such
    parameter, so flagged code raised TypeError instead of executing."""
    agent = Agent(name="T", instructions="x", sandbox=True)
    result = agent.execute_code_sync("import os\nprint('flagged-ok')")
    assert "flagged-ok" in (result.stdout or result.output or "")


def test_security_warnings_are_attached_to_result():
    agent = Agent(name="T", instructions="x", sandbox=True)
    result = agent.execute_code_sync("import os\nprint('x')")
    meta = getattr(result, "metadata", None) or {}
    assert "security_warnings" in meta, "flagged code should carry its warnings"


# ── the clone fix (kept from the reverted change) ────────────────────────────
def test_clone_keeps_sandbox():
    """clone_for_channel() read `_sandbox_config`, which is never assigned, so
    every clone silently ran unisolated."""
    agent = Agent(name="T", instructions="x", sandbox=True)
    clone = agent.clone_for_channel()
    assert getattr(clone, "sandbox_config", None) is not None


def test_clone_does_not_accumulate_tools():
    agent = Agent(name="T", instructions="x", tools=[a_tool], sandbox=True)
    once = agent.clone_for_channel()
    twice = once.clone_for_channel()
    assert _tool_names(twice) == _tool_names(agent)


# ── the backend precedence warning (kept) ────────────────────────────────────
class _FakeBackend:
    async def execute(self, prompt, **kwargs):
        return ""


def test_sandbox_plus_backend_warns():
    """A managed backend takes the whole turn, making sandbox= inert."""
    with pytest.warns(FutureWarning, match="sandbox") as caught:
        Agent(name="T", instructions="x", sandbox=True, backend=_FakeBackend())
    assert any("backend" in str(w.message) for w in caught)


def test_backend_alone_does_not_warn(recwarn):
    Agent(name="T", instructions="x", backend=_FakeBackend())
    assert not [
        w for w in recwarn
        if issubclass(w.category, FutureWarning) and "sandbox" in str(w.message)
    ]


# ── the no-injection contract must stay documented at the call site ──────────
def test_no_injection_contract_is_documented():
    import inspect

    from praisonaiagents.agent import agent as agent_mod

    src = inspect.getsource(agent_mod.Agent.__init__)
    assert "does NOT add code-execution tools" in src


# ── inert fields must stay labelled ──────────────────────────────────────────
def test_inert_fields_are_documented_as_inert():
    import inspect

    from praisonaiagents.agent import autonomy
    from praisonaiagents.config import feature_configs

    assert "NOT IMPLEMENTED" in (autonomy.AutonomyConfig.__doc__ or "")
    src = inspect.getsource(feature_configs.ExecutionConfig)
    idx = src.find("code_sandbox_mode")
    assert "NOT IMPLEMENTED" in src[max(0, idx - 400):idx]
