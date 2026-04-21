"""
Default tool-safety policy tests.

Covers the zero-kwarg, env-var-driven default that lands an
``Agent()`` into the ``PERMISSION_PRESETS['default']`` deny set when
no explicit ``approval=`` is passed.

Policy (see praisonaiagents/approval/registry.py):
- Allowed by default: read / create / edit tools (write_file,
  acp_create_file, acp_edit_file, read_file, search_*, get_*, ...).
- Blocked by default: destructive + arbitrary execution —
  delete_file, acp_delete_file, move_file, copy_file,
  execute_command, acp_execute_command, execute_code, kill_process.
- User escape hatches:
    - ``PRAISONAI_TOOL_SAFETY=off``   → behave like pre-4.6.27 (no blocks)
    - ``PRAISONAI_TOOL_SAFETY=full``  → alias of off
    - ``PRAISONAI_TOOL_SAFETY=safe``  → stricter preset (blocks writes too)
    - ``Agent(approval="full")``      → disable per-agent without env
- Ergonomic invariant: no new Agent kwarg was added.
"""
from __future__ import annotations

from praisonaiagents.approval.registry import PERMISSION_PRESETS


def _make_agent(**kwargs):
    # Import late so monkeypatched env is respected at Agent.__init__ time.
    from praisonaiagents import Agent
    return Agent(instructions="t", llm="gpt-4o-mini", **kwargs)


def test_default_preset_exists_and_blocks_destructive():
    d = PERMISSION_PRESETS["default"]
    for blocked in (
        "delete_file", "acp_delete_file", "move_file", "copy_file",
        "execute_command", "acp_execute_command", "execute_code",
        "kill_process",
    ):
        assert blocked in d, f"'default' preset should block {blocked}"


def test_default_preset_allows_read_create_edit():
    d = PERMISSION_PRESETS["default"]
    for allowed in (
        "read_file", "write_file", "acp_create_file", "acp_edit_file",
        "search_web", "get_weather", "list_directory",
    ):
        assert allowed not in d, (
            f"'default' preset must not block {allowed} — read/create/edit "
            f"is what 99% of agent workflows need."
        )


def test_off_and_full_presets_are_empty():
    assert PERMISSION_PRESETS["off"] == frozenset()
    assert PERMISSION_PRESETS["full"] == frozenset()


def test_agent_applies_default_preset_when_no_env_and_no_kwarg(monkeypatch):
    monkeypatch.delenv("PRAISONAI_TOOL_SAFETY", raising=False)
    a = _make_agent()
    assert "delete_file" in a._perm_deny
    assert "execute_command" in a._perm_deny
    assert "write_file" not in a._perm_deny  # create/edit stays allowed
    assert "read_file" not in a._perm_deny


def test_env_off_disables_default_policy(monkeypatch):
    monkeypatch.setenv("PRAISONAI_TOOL_SAFETY", "off")
    a = _make_agent()
    # Pre-4.6.27 behaviour: nothing blocked
    assert a._perm_deny == frozenset()


def test_env_full_is_alias_of_off(monkeypatch):
    monkeypatch.setenv("PRAISONAI_TOOL_SAFETY", "full")
    a = _make_agent()
    assert a._perm_deny == frozenset()


def test_env_safe_applies_stricter_preset(monkeypatch):
    monkeypatch.setenv("PRAISONAI_TOOL_SAFETY", "safe")
    a = _make_agent()
    # "safe" blocks writes too, per existing PERMISSION_PRESETS["safe"]
    assert "write_file" in a._perm_deny
    assert "delete_file" in a._perm_deny


def test_explicit_approval_kwarg_overrides_env(monkeypatch):
    monkeypatch.setenv("PRAISONAI_TOOL_SAFETY", "safe")
    a = _make_agent(approval="full")
    # Explicit kwarg wins — user opted out per-agent even with strict env.
    assert a._perm_deny == frozenset()


def test_unknown_env_value_falls_back_to_no_blocks(monkeypatch):
    # Defensive: a typo ("sfae") must not silently apply the strictest
    # preset or crash. It should leave the agent in the no-policy state.
    monkeypatch.setenv("PRAISONAI_TOOL_SAFETY", "sfae")
    a = _make_agent()
    assert a._perm_deny == frozenset()


def test_no_new_agent_kwarg_was_added():
    """Guard-rail: the feature must not add any new Agent() kwarg.

    The commit that introduced the default tool-safety policy must stay
    strictly behind the existing ``approval=`` knob and the
    ``PRAISONAI_TOOL_SAFETY`` env var. If a future refactor adds a
    dedicated ``tool_safety=`` parameter, this test fails loudly so it
    gets a conscious review.
    """
    import inspect
    from praisonaiagents import Agent
    params = set(inspect.signature(Agent.__init__).parameters)
    forbidden = {"tool_safety", "safety", "permission", "permissions", "deny_tools"}
    leaked = params & forbidden
    assert not leaked, (
        f"New Agent() kwarg(s) leaked: {leaked}. The tool-safety "
        f"feature must stay behind the existing 'approval=' kwarg + "
        f"PRAISONAI_TOOL_SAFETY env — see AGENTS.md 'Minimal API'."
    )
