"""GitHub write tools must go through the approval system (issue #6023)."""
import pytest

from praisonaiagents.approval import get_approval_registry
from praisonaiagents.approval.registry import PERMISSION_PRESETS

GITHUB_WRITE_TOOLS = (
    "github_create_branch",
    "github_commit_and_push",
    "github_create_pull_request",
)


@pytest.mark.parametrize("name", GITHUB_WRITE_TOOLS)
def test_registered_as_high_risk(name):
    reg = get_approval_registry()
    assert reg.is_required(name)
    # high (not critical) so YAML/declarative approve lists still apply
    assert reg.get_risk_level(name) == "high"


@pytest.mark.parametrize("name", GITHUB_WRITE_TOOLS)
def test_in_deny_presets(name):
    for preset in ("default", "safe", "read_only"):
        assert name in PERMISSION_PRESETS[preset]
    assert name not in PERMISSION_PRESETS["full"]


def test_unattended_agent_denied_by_default(monkeypatch):
    monkeypatch.delenv("PRAISONAI_TOOL_SAFETY", raising=False)
    from praisonaiagents import Agent

    agent = Agent(instructions="t", llm="gpt-4o-mini", approval=False)
    for name in ("github_commit_and_push", "github_create_pull_request"):
        result = agent._check_tool_approval_sync(name, {})
        assert isinstance(result, dict) and result.get("permission_denied")


def test_explicit_full_preset_allows(monkeypatch):
    monkeypatch.setenv("PRAISONAI_TOOL_SAFETY", "off")
    from praisonaiagents import Agent

    agent = Agent(instructions="t", llm="gpt-4o-mini", approval=False)
    assert "github_commit_and_push" not in (agent._perm_deny or ())
