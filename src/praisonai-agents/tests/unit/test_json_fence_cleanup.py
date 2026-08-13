"""Regression tests for the shared JSON fence cleanup helper."""

import pytest

from praisonaiagents.agent.chat_mixin import ChatMixin
from praisonaiagents.agents.agents import PraisonAIAgents
from praisonaiagents.main import clean_triple_backticks


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ('  {"ok": true}  ', '{"ok": true}'),
        ('```json\n{"ok": true}\n```', '{"ok": true}'),
        ('```\n[1, 2]\n```', '[1, 2]'),
        ('```JSON\n{"ok": true}\n```', 'JSON\n{"ok": true}'),
    ],
)
def test_json_cleanup_surfaces_share_behavior(value, expected):
    assert clean_triple_backticks(value) == expected
    assert PraisonAIAgents.clean_json_output(None, value) == expected
    assert ChatMixin.clean_json_output(None, value) == expected


def test_legacy_methods_delegate_to_canonical_helper(monkeypatch):
    sentinel = object()

    def fake_cleaner(value):
        assert value == "response"
        return sentinel

    monkeypatch.setattr("praisonaiagents.main.clean_triple_backticks", fake_cleaner)

    assert PraisonAIAgents.clean_json_output(None, "response") is sentinel
    assert ChatMixin.clean_json_output(None, "response") is sentinel
