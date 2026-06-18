"""Tests for outstanding GHSA security fixes in praisonaiagents."""

from __future__ import annotations

import pytest


def test_searxng_url_blocks_private_ip():
    from praisonaiagents.tools.url_safety import validate_searxng_url

    assert validate_searxng_url("http://10.0.0.1/search") is None


def test_workflow_yaml_approve_gated_without_allow_dangerous():
    """GHSA-7qw2: approve list must not auto-approve when allow_dangerous_tools=False."""
    from praisonaiagents import Agent, Workflow
    from praisonaiagents.approval import get_approval_registry

    agent = Agent(name="a", instructions="test")
    wf = Workflow(steps=[agent])
    wf.approve_tools = ["execute_command"]
    wf.allow_dangerous_tools = False

    registry = get_approval_registry()
    before = set(registry._yaml_approved_tools.get() or ())

    try:
        wf.run("hello", verbose=False)
    except Exception:
        pass

    after = set(registry._yaml_approved_tools.get() or ())
    assert after == before
