"""YAML wrapper permission decisions and explicit approval options."""

import pytest


@pytest.mark.parametrize("section", ["roles", "agents"])
@pytest.mark.parametrize("action", ["allow", "deny"])
def test_cli_permissions_survive_yaml_merge_and_decide_without_prompt(monkeypatch, tmp_path, section, action):
    import asyncio
    import logging

    from praisonai.agents_generator import AgentsGenerator
    from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter
    from praisonaiagents.approval.protocols import ApprovalRequest

    monkeypatch.chdir(tmp_path)
    rules = {"audit_probe:*": action}
    generator = AgentsGenerator.__new__(AgentsGenerator)
    generator.logger = logging.getLogger(__name__)
    config = {section: {"reviewer": {}}}
    generator._merge_cli_config(config, {
        "approval": "console", "permissions_config": rules,
    })
    adapter = PraisonAIAdapter.__new__(PraisonAIAdapter)
    approval = adapter._resolve_agent_approval(config[section]["reviewer"], config)

    def unexpected_prompt(request):
        pytest.fail("YAML permission rule fell back to interactive approval")

    monkeypatch.setattr(approval.backend, "_prompt_user", unexpected_prompt)
    decision = asyncio.run(approval.backend.request_approval(
        ApprovalRequest(tool_name="audit_probe", arguments={}, risk_level="low")
    ))
    assert decision.approved is (action == "allow")
    assert decision.approver == "permission_rule"
    assert approval.permissions == rules


def test_yaml_inline_rules_preserve_explicit_plan_and_approval_options(tmp_path, monkeypatch):
    """Inline rules retain explicit mode, all-tools and timeout configuration."""
    import asyncio

    from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter
    from praisonaiagents.approval.protocols import ApprovalRequest
    from praisonaiagents.permissions import PermissionMode

    monkeypatch.chdir(tmp_path)
    adapter = PraisonAIAdapter.__new__(PraisonAIAdapter)
    approval = adapter._resolve_agent_approval({"approval": {
        "backend": "plan", "permissions": {"write:*": "allow"},
        "approve_all_tools": True, "timeout": 30,
    }}, {})
    assert approval.backend.permission_mode == PermissionMode.PLAN
    assert approval.all_tools is True
    assert approval.timeout == 30
    decision = asyncio.run(approval.backend.request_approval(
        ApprovalRequest(tool_name="write", arguments={}, risk_level="low")
    ))
    assert decision.approved is False


def test_yaml_inline_rules_preserve_explicit_disabled_backend():
    """An explicit disabled backend follows the same override as direct runs."""
    from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter

    adapter = PraisonAIAdapter.__new__(PraisonAIAdapter)
    assert adapter._resolve_agent_approval({"approval": {
        "backend": "none", "permissions": {"audit_probe:*": "deny"},
    }}, {}) is None


@pytest.mark.parametrize("timeout_options, expected", [
    ({}, 0), ({"timeout": None}, None), ({"timeout": 30}, 30),
    ({"timeout": 0}, 0), ({"timeout": "none"}, None),
])
def test_yaml_inline_rules_preserve_timeout_semantics(timeout_options, expected):
    """Explicit null waits indefinitely; omission retains the backend default."""
    from praisonai.framework_adapters.praisonai_adapter import PraisonAIAdapter

    adapter = PraisonAIAdapter.__new__(PraisonAIAdapter)
    approval = adapter._resolve_agent_approval({"approval": {
        "backend": "console", "permissions": {"audit_probe:*": "deny"},
        **timeout_options,
    }}, {})
    assert approval.timeout == expected
