"""Tests for ``praisonai agent create`` (issue #3376).

Covers the golden-file round-trip (write → discover → assert frontmatter/prompt)
and the non-interactive CLI form, with LLM drafting stubbed so tests never call
a provider.
"""

import os

import pytest
from typer.testing import CliRunner

from praisonai_code.cli.commands.agent import app
from praisonai_code.cli.features import agent_scaffold
from praisonai_code.cli.features.agent_scaffold import (
    render_agent_markdown,
    write_agent_definition,
)
from praisonai_code.cli.features.custom_definitions import (
    CustomDefinitionsDiscovery,
    resolve_permission_config,
)


def test_render_roundtrips_through_discovery(tmp_path):
    agents_dir = tmp_path / ".praisonai" / "agents"
    path = write_agent_definition(
        name="reviewer",
        description="Review code and suggest improvements",
        role="Reviewer",
        goal="Review code and suggest improvements",
        model="gpt-4o-mini",
        permission="read-only",
        agents_dir=agents_dir,
        body="You are a careful code reviewer.",
    )

    discovery = CustomDefinitionsDiscovery()
    agent = discovery._load_agent(path, source="project")

    assert agent is not None
    assert agent.name == "reviewer"
    assert agent.model == "gpt-4o-mini"
    assert agent.role == "Reviewer"
    assert agent.mode == "read-only"
    assert "careful code reviewer" in (agent.system_prompt or "")
    # The mode preset must resolve to a real, restrictive permission config.
    resolved = resolve_permission_config(agent.permission, agent.mode)
    assert resolved is not None
    assert resolved.get("edit:*") == "deny"


def test_full_preset_omits_mode(tmp_path):
    content = render_agent_markdown(
        description="do things",
        role="Doer",
        goal="do things",
        model=None,
        permission="full",
        body="You do things.",
    )
    assert "mode:" not in content
    # Must still start with valid frontmatter.
    assert content.startswith("---\n")


def test_unknown_permission_rejected():
    with pytest.raises(ValueError):
        render_agent_markdown(
            description="x",
            role="X",
            goal="x",
            model=None,
            permission="bogus",
            body="body",
        )


def test_cli_create_non_interactive(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Stub LLM drafting so the test is deterministic and offline.
    monkeypatch.setattr(
        agent_scaffold,
        "draft_system_prompt",
        lambda description, role, model: "You are a helpful test agent.",
    )

    result = CliRunner().invoke(
        app,
        [
            "create",
            "helper",
            "--describe",
            "Assist with tasks",
            "--model",
            "gpt-4o-mini",
            "--permission",
            "read-only",
            "--yes",
        ],
    )

    assert result.exit_code == 0, result.output
    written = tmp_path / ".praisonai" / "agents" / "helper.md"
    assert written.exists()
    text = written.read_text()
    assert "mode: read-only" in text
    assert "helpful test agent" in text


def test_cli_create_refuses_overwrite(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        agent_scaffold,
        "draft_system_prompt",
        lambda description, role, model: "stub",
    )
    args = ["create", "dup", "--describe", "d", "--permission", "full", "--yes"]

    first = CliRunner().invoke(app, args)
    assert first.exit_code == 0, first.output

    second = CliRunner().invoke(app, args)
    assert second.exit_code == 1
    assert "already exists" in second.output.lower()
