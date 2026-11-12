"""Regression tests for #6281: scheduled YAML agents must not silently drop fields."""

import pytest

from praisonai.scheduler.yaml_loader import create_agent_from_config


def test_scheduler_fails_closed_on_dropped_approval():
    with pytest.raises(ValueError, match="approval"):
        create_agent_from_config({
            "name": "a", "role": "r", "instructions": "i",
            "approval": {"backend": "console"},
        })


def test_scheduler_forwards_llm():
    agent = create_agent_from_config({
        "name": "a", "role": "r", "instructions": "i", "llm": "gpt-4o",
    })
    assert "gpt-4o" in str(getattr(agent, "llm", ""))
