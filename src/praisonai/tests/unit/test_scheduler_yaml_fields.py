"""Regression tests for #6281: scheduled YAML agents must not silently drop fields."""

import pytest

from praisonai.scheduler.yaml_loader import create_agent_from_config


def test_scheduler_fails_closed_on_dropped_approval():
    with pytest.raises(ValueError, match="approval") as exc:
        create_agent_from_config({
            "name": "a", "role": "r", "instructions": "i",
            "approval": {"backend": "console"},
        })
    msg = str(exc.value)
    assert "Scheduled agents cannot enforce" in msg
    assert "praisonai run" in msg
    assert "framework: praisonai" not in msg


def test_scheduler_error_names_only_active_gates():
    with pytest.raises(ValueError) as exc:
        create_agent_from_config({
            "name": "a", "role": "r", "instructions": "i",
            "approval": False, "guardrails": "must cite sources",
        })
    assert "['guardrails']" in str(exc.value)


def test_scheduler_forwards_llm():
    agent = create_agent_from_config({
        "name": "a", "role": "r", "instructions": "i", "llm": "gpt-4.1-nano",
    })
    # Exact match: the Agent default (gpt-4o-mini) must not satisfy this.
    assert agent.llm == "gpt-4.1-nano"
