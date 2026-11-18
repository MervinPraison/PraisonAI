"""Characterisation of the guardrail + approval block of ``Agent.__init__``.

Pins what a caller observes right after ``Agent(...)`` so the block (from
"# Initialize guardrail settings" to "# Pending approvals") can move into a
``config/agent_init.py`` resolver unchanged. Values were measured on main.

Branch map (``here`` = this file; others already pin the rest):
  guardrail settings + _setup_guardrail ... here; guardrails= resolver: config/test_agent_init_guardrails.py
  approval=str, deny-set preset .......... here; test_permissions.py, config/test_preset_typo_validation.py
  approval=str, PermissionMode preset .... here; permissions/test_permissions.py::TestAgentApprovalPresetResolution
  approval=str, no preset and no mode .... here ("true"/"false"); unknown strings are rejected before
                                            this block: config/test_preset_typo_validation.py
  approval="True"/"False" (else branch) .. here
  approval=True .......................... here; dispatch: test_approval_protocol.py
  approval=None/False + PRAISONAI_TOOL_SAFETY here; TTY ask path: approval/test_default_tool_safety.py
  ApprovalConfig / dict .................. here; with permissions / empty policy:
                                            test_permissions.py::TestApprovalConfigNeverWeakensDefault
  backend object ......................... here; dispatch: test_approval_protocol.py
  raw approval kwarg persisted ........... here; clone: agent/test_clone_keeps_guardrail.py
  X-13 code-execution warning ............ here (wording); default preset: agent/test_code_execution_blocked_warning.py
  autonomy full_auto -> approval bridge .. here
  permissions -> PermissionManager ....... here; call-time enforcement: test_issue_6334_tool_authz_injected_guardrail.py
  pending approvals ...................... here
"""
import asyncio
import logging
import os
import warnings

import pytest

from praisonaiagents import Agent, ExecutionConfig
from praisonaiagents.approval import get_approval_registry
from praisonaiagents.approval.backends import AutoApproveBackend, CallbackBackend, ConsoleBackend
from praisonaiagents.approval.protocols import ApprovalConfig
from praisonaiagents.approval.registry import PERMISSION_PRESETS
from praisonaiagents.guardrails import LLMGuardrail
from praisonaiagents.permissions import PermissionManager, PermissionRule
from praisonaiagents.permissions.rules import PermissionAction, PermissionMode

DEFAULT, SAFE, READ_ONLY = (PERMISSION_PRESETS[k] for k in ("default", "safe", "read_only"))
NONE = frozenset()


@pytest.fixture(autouse=True)
def _isolated(monkeypatch, tmp_path):
    for var in ("PRAISONAI_TOOL_SAFETY", "PRAISONAI_AUTO_APPROVE", "OPENAI_API_BASE", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Agent, "_is_interactive_session", staticmethod(lambda: False))
    # The default rules dir is bound at import time; keep ~/.praisonai out of it.
    monkeypatch.setattr("praisonaiagents.permissions.manager.DEFAULT_PERMISSIONS_DIR", str(tmp_path / "perms"))
    # Process-global registry: deny instead of falling back to a stdin prompt.
    registry = get_approval_registry()
    monkeypatch.setattr(registry, "_global_backend", CallbackBackend(lambda *a: False))
    monkeypatch.setattr(registry, "_agent_backends", {})


def _agent(**kw):
    return Agent(name="a", instructions="x", **kw)


def _state(a):
    return (a._approval_backend, a._perm_deny, a._permission_mode,
            a._approve_all_tools, a._approval_timeout, a._approval_permissions)


def _check(output):
    return True, output


# --- guardrail settings -----------------------------------------------------

def test_guardrail_callable_and_counters():
    a = _agent(guardrails=_check)
    assert a.guardrail is _check and a._guardrail_fn is _check and a.max_guardrail_retries == 3
    assert (a._guardrail_retry_count, a._last_guardrail_error) == (0, None)
    assert (a._tool_call_guardrails, a._tool_result_guardrails) == ([], [])


def test_guardrail_string_is_output_only_llm_guardrail():
    a = _agent(guardrails="Be polite")
    assert isinstance(a._guardrail_fn, LLMGuardrail) and a._guardrail_fn._praison_output_only
    assert (a._tool_call_guardrails, a._tool_result_guardrails) == ([], [])


def test_guardrail_with_tool_surfaces_is_registered():
    class G:
        def __call__(self, output):
            return True, output

        def validate_tool_call(self, *a):
            return True

        def validate_tool_result(self, *a):
            return True

    g = G()
    a = _agent(guardrails=g)
    assert a._tool_call_guardrails == [a._guardrail_fn] == a._tool_result_guardrails


def test_no_guardrail_and_bad_signature():
    assert _agent()._guardrail_fn is None
    with pytest.raises(ValueError, match="exactly one parameter"):
        _agent(guardrails=lambda x, y: (True, x))


# --- approval= resolution -----------------------------------------------------

@pytest.mark.parametrize("value, deny", [
    ("safe", SAFE), ("read_only", READ_ONLY), (" Read-Only ", READ_ONLY),
    ("full", NONE), ("off", NONE), ("default", DEFAULT),
])
def test_deny_set_preset_strings(value, deny):
    assert _state(_agent(approval=value)) == (None, deny, None, False, 0, None)


@pytest.mark.parametrize("value, mode", [
    ("plan", PermissionMode.PLAN), ("yolo", PermissionMode.BYPASS),
    ("ask", PermissionMode.DEFAULT), ("reject", PermissionMode.DONT_ASK),
])
def test_permission_mode_strings(value, mode):
    assert _state(_agent(approval=value)) == (None, NONE, mode, False, 0, None)


@pytest.mark.parametrize("value", ["true", "false"])
def test_string_with_no_preset_and_no_mode_is_no_approval(value):
    assert _state(_agent(approval=value)) == (None, NONE, None, False, 0, None)


@pytest.mark.parametrize("value", ["True", "False"])
def test_capitalised_bool_strings_fall_to_backend_branch(value):
    assert _state(_agent(approval=value)) == (value, NONE, None, False, 0, None)


def test_approval_true_auto_approves_without_default_denials():
    backend, *rest = _state(_agent(approval=True))
    assert isinstance(backend, AutoApproveBackend) and rest == [NONE, None, False, 0, None]


@pytest.mark.parametrize("approval", [None, False])
@pytest.mark.parametrize("env, deny", [
    (None, DEFAULT), ("off", NONE), ("full", NONE), ("none", NONE), ("0", NONE),
    ("false", NONE), (" OFF ", NONE), ("safe", SAFE), ("read_only", READ_ONLY),
])
def test_no_approval_follows_tool_safety_env(monkeypatch, approval, env, deny):
    if env is not None:
        monkeypatch.setenv("PRAISONAI_TOOL_SAFETY", env)
    assert _state(_agent(approval=approval)) == (None, deny, None, False, 0, None)


def test_unknown_tool_safety_env_warns_and_uses_default(monkeypatch, caplog):
    monkeypatch.setenv("PRAISONAI_TOOL_SAFETY", "sfae")
    with caplog.at_level(logging.WARNING, logger="praisonaiagents.agent.agent"):
        assert _agent()._perm_deny == DEFAULT
    assert "Unknown PRAISONAI_TOOL_SAFETY value 'sfae'" in caplog.text


def test_approval_config_fields_are_copied():
    b = object()
    a = _agent(approval=ApprovalConfig(backend=b, all_tools=True, timeout=None,
                                       permission_mode=PermissionMode.PLAN))
    assert _state(a) == (b, DEFAULT, PermissionMode.PLAN, True, None, None)
    assert a._permission_manager is None


def test_dict_is_read_as_approval_config():
    b = object()
    a = _agent(approval={"backend": b, "all_tools": True, "timeout": 5})
    assert _state(a) == (b, DEFAULT, None, True, 5, None)
    with pytest.raises(TypeError):
        _agent(approval={"bogus": 1})


def test_backend_object_is_stored_as_is():
    b = object()
    assert _state(_agent(approval=b)) == (b, NONE, None, False, 0, None)


@pytest.mark.parametrize("value", [
    None, True, False, "safe", "plan", "True", ApprovalConfig(timeout=3), {"timeout": 3}, object(),
])
def test_raw_approval_kwarg_is_persisted(value):
    a = _agent(approval=value)
    assert a._approval_config is value
    assert (a._perm_allow, a._pending_approvals) == (None, {})
    assert isinstance(a._approvals_lock, asyncio.Lock)


# --- X-13: code execution vs tool safety ---------------------------------------

def _user_warnings(**kw):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _agent(execution=ExecutionConfig(code_execution=True), **kw)
    return [str(w.message) for w in caught if w.category is UserWarning]


def test_code_execution_warning_names_the_blocking_policy(monkeypatch):
    (msg,) = _user_warnings(approval="safe")
    assert "approval='safe' blocks 'execute_code'" in msg
    monkeypatch.setenv("PRAISONAI_TOOL_SAFETY", "safe")
    (msg,) = _user_warnings()
    assert "the 'safe' tool-safety preset blocks 'execute_code'" in msg
    assert _user_warnings(approval=True) == _user_warnings(approval="plan") == []


# --- autonomy full_auto -> approval bridge -------------------------------------

@pytest.mark.parametrize("approval", [None, False])
def test_full_auto_auto_approves_this_agent_only(approval):
    a = _agent(autonomy={"level": "full_auto"}, approval=approval)
    assert isinstance(a._approval_backend, AutoApproveBackend)
    assert a._perm_deny == DEFAULT  # the bridge leaves the deny set alone
    assert "PRAISONAI_AUTO_APPROVE" not in os.environ
    assert _agent()._approval_backend is None


def test_full_auto_replaces_the_terminal_prompt(monkeypatch):
    monkeypatch.setattr(Agent, "_is_interactive_session", staticmethod(lambda: True))
    assert isinstance(_agent()._approval_backend, ConsoleBackend)
    assert isinstance(_agent(autonomy={"level": "full_auto"})._approval_backend, AutoApproveBackend)


def test_full_auto_keeps_an_explicit_approval_and_other_levels_do_nothing():
    b = object()
    assert _agent(autonomy={"level": "full_auto"}, approval=b)._approval_backend is b
    assert _agent(autonomy={"level": "full_auto"}, approval="safe")._approval_backend is None
    assert _agent(autonomy={"level": "auto_edit"})._approval_backend is None


# --- permissions -> PermissionManager ------------------------------------------

def test_permission_manager_instance_is_reused(tmp_path):
    mgr = PermissionManager(storage_dir=str(tmp_path / "own"))
    a = _agent(approval={"permissions": mgr})
    assert a._permission_manager is mgr and a._perm_deny == NONE


def test_permissions_dict_builds_a_manager_for_this_agent(tmp_path):
    mgr = _agent(approval=ApprovalConfig(permissions={"lookup": "deny"}))._permission_manager
    assert type(mgr) is PermissionManager and mgr.agent_name == "a"
    assert mgr.workspace_root == os.path.realpath(tmp_path)
    assert [(r.pattern, r.action) for r in mgr.get_rules()] == [("lookup", PermissionAction.DENY)]


def test_permissions_list_keeps_only_rule_objects():
    rule = PermissionRule(pattern="lookup", action=PermissionAction.DENY)
    mgr = _agent(approval={"permissions": [rule, "junk"]})._permission_manager
    assert mgr.get_rules() == [rule]


@pytest.mark.parametrize("permissions, has_manager", [({}, False), ([], False), ("junk", True)])
def test_other_permissions_values(permissions, has_manager):
    mgr = _agent(approval={"permissions": permissions})._permission_manager
    assert (mgr is not None) is has_manager
    assert mgr is None or mgr.get_rules() == []


def test_manager_failure_is_not_fatal(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no")
    monkeypatch.setattr("praisonaiagents.permissions.PermissionManager.__init__", boom)
    a = _agent(approval={"permissions": {"lookup": "deny"}})
    assert a._permission_manager is None and a._perm_deny == NONE


# --- deny rules: hidden from the schema and blocked at call time ---------------

def _tools(calls):
    def lookup(q: str) -> str:
        """Look something up."""
        calls.append(("lookup", q))
        return "found"

    def delete_file(path: str) -> str:
        """Delete a file."""
        calls.append(("delete_file", path))
        return "deleted"

    return [lookup, delete_file]


def _advertised(a):
    return {t["function"]["name"] for t in a._format_tools_for_completion()}


@pytest.mark.parametrize("approval, hidden, allowed", [
    (None, "delete_file", "lookup"),
    ({"permissions": {"lookup": "deny"}}, "lookup", "delete_file"),
])
def test_denied_tool_is_hidden_and_blocked(approval, hidden, allowed):
    calls = []
    a = _agent(tools=_tools(calls), approval=approval)
    assert _advertised(a) == {allowed}
    assert a.execute_tool(hidden, {"q": "x", "path": "x"}).get("permission_denied") is True
    assert calls == []
