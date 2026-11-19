"""Approval grants cover only what the person approved.

* A "this session" / "always" grant is pinned to the call's arguments, so
  approving ``send_email(to=a)`` does not approve ``send_email(to=b)``.
* A skill's ``allowed-tools`` cannot skip the prompt for a tool registered
  above low risk, or for a tool with no registered risk (external / MCP).
* ``PermissionMode.PLAN`` denies outbound-send and scheduling tools.
"""
import pytest

from praisonaiagents.approval import ApprovalDecision, get_approval_registry
from praisonaiagents.approval.backends import CallbackBackend
from praisonaiagents.approval.utils import build_permission_target


@pytest.fixture
def registry(monkeypatch):
    monkeypatch.delenv("PRAISONAI_AUTO_APPROVE", raising=False)
    reg = get_approval_registry()
    reg.clear_approved()
    saved_auto = dict(reg._agent_tool_auto_approve)
    yield reg
    reg.clear_approved()
    reg._agent_tool_auto_approve.clear()
    reg._agent_tool_auto_approve.update(saved_auto)
    reg.remove_backend("vf-agent")


@pytest.mark.parametrize("tool, a, b", [
    ("execute_code", {"code": "print(1)"}, {"code": "import os; os.system('id')"}),
    ("send_email", {"to": "a@example.com", "subject": "s", "body": "b"},
     {"to": "b@example.com", "subject": "s", "body": "b"}),
    ("apply_patch", {"patch": "--- a\n+++ b\n"}, {"patch": "--- c\n+++ d\n"}),
    ("execute_command", {"cmd_line": "ls"}, {"cmd_line": "rm -rf /tmp/x"}),
])
def test_permission_target_depends_on_arguments(tool, a, b):
    assert build_permission_target(tool, a) != build_permission_target(tool, b)
    assert build_permission_target(tool, a) == build_permission_target(tool, dict(a))


def test_existing_shell_and_file_targets_unchanged():
    assert build_permission_target("execute_command", {"command": "ls -la"}) == "bash:ls -la"
    assert build_permission_target("write_file", {"path": "a.py"}) == "write:a.py"
    assert build_permission_target("send_email") == "tool:send_email"


def test_session_grant_does_not_cover_other_arguments(registry):
    asked = []

    def person(name, args, risk):
        asked.append(args["to"])
        return ApprovalDecision(approved=True, approver="human", scope="session")

    registry.add_requirement("vf_send", "high")
    registry.set_backend(CallbackBackend(person), agent_name="vf-agent")
    first = {"to": "a@example.com", "subject": "s", "body": "b"}
    other = {"to": "stranger@example.com", "subject": "s", "body": "b"}
    try:
        assert registry.approve_sync("vf-agent", "vf_send", first, scope_id="vf-1").approved
        registry._approved_context.set(None)  # drop the exact-args cache
        same = registry.approve_sync("vf-agent", "vf_send", dict(first), scope_id="vf-1")
        assert same.approved and same.approver == "session"
        registry._approved_context.set(None)
        registry.approve_sync("vf-agent", "vf_send", other, scope_id="vf-1")
        assert asked == ["a@example.com", "stranger@example.com"]
    finally:
        registry.remove_requirement("vf_send")


def test_agent_session_grant_is_argument_scoped(registry):
    from praisonaiagents import Agent

    asked = []

    def person(name, args, risk):
        asked.append(args.get("code"))
        return ApprovalDecision(approved=True, approver="human", scope="session")

    agent = Agent(name="vf-session", instructions="x", approval=CallbackBackend(person))
    try:
        agent._resolve_approval_decision("execute_code", {"code": "print(1)"})
        registry._approved_context.set(None)
        agent._resolve_approval_decision("execute_code", {"code": "print(1)"})
        agent._resolve_approval_decision("execute_code", {"code": "import os"})
        assert asked == ["print(1)", "import os"]
    finally:
        agent.close()


def test_skill_grant_does_not_skip_prompt_for_gated_tool(registry):
    registry.add_requirement("vf_high_tool", "high")
    try:
        registry.auto_approve_tool("vf_high_tool", "vf-scope")
        registry.set_backend(CallbackBackend(
            lambda n, a, r: ApprovalDecision(approved=False, reason="person said no")
        ), agent_name="vf-agent")
        decision = registry.approve_sync(
            "vf-agent", "vf_high_tool", {"command": "id"}, auto_approve_scope="vf-scope"
        )
        assert not decision.approved
        assert decision.approver != "skill"
    finally:
        registry.remove_requirement("vf_high_tool")


def test_skill_grant_still_covers_low_risk_tool(registry):
    registry.add_requirement("vf_low_tool", "low")
    try:
        registry.auto_approve_tool("vf_low_tool", "vf-scope")
        decision = registry.approve_sync(
            "vf-agent", "vf_low_tool", {}, auto_approve_scope="vf-scope"
        )
        assert decision.approved and decision.approver == "skill"
    finally:
        registry.remove_requirement("vf_low_tool")


def test_agent_skill_grant_does_not_skip_prompt_for_external_tool(registry):
    from praisonaiagents import Agent
    from praisonaiagents.tools.registry import get_registry

    def vf_mcp_shell(command: str) -> str:
        """Simulated external tool."""
        return "ran"

    get_registry().register(vf_mcp_shell, name="vf_mcp_shell", trust_level="external")
    asked = []

    def person(name, args, risk):
        asked.append(name)
        return ApprovalDecision(approved=False, reason="no")

    agent = Agent(name="vf-skill", instructions="x", approval=CallbackBackend(person))
    try:
        registry.auto_approve_tool("vf_mcp_shell", agent._approval_scope_id)
        decision = agent._resolve_approval_decision("vf_mcp_shell", {"command": "id"})
        assert not decision.approved
        assert asked == ["vf_mcp_shell"]
    finally:
        agent.close()
        get_registry().unregister("vf_mcp_shell")


@pytest.mark.parametrize("tool", ["send_email", "smtp_send_email", "send_message",
                                  "schedule_add", "reply_email"])
def test_plan_mode_denies_outside_effect_tools(tool):
    from praisonaiagents import Agent

    agent = Agent(name="vf-plan", instructions="x", approval="plan")
    try:
        decision = agent._resolve_permission_mode_decision(tool)
        assert decision is not None and not decision.approved
    finally:
        agent.close()


@pytest.mark.parametrize("tool", ["send_notification", "publish_release", "upload_report",
                                  "git_push", "forward_ticket"])
def test_plan_mode_treats_send_and_publish_names_as_writes(tool):
    from praisonaiagents.agent.tool_execution import ToolExecutionMixin

    assert not ToolExecutionMixin._is_read_only_tool(tool)

