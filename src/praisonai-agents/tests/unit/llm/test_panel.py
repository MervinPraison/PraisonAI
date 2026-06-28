"""Unit tests for the Panel (multi-model) LLM provider.

These tests avoid real API calls by stubbing the reference/aggregator calls,
focusing on descriptor resolution, cache-safe tail injection, trimmed-view
construction, partial-failure tolerance, per-turn caching, the recursion guard,
and the enabled=False collapse.
"""

import pytest

from praisonaiagents.llm.panel import (
    PanelLLM,
    is_panel_descriptor,
    resolve_panel_config,
    register_panel_preset,
    PANEL_PRESETS,
)


def test_is_panel_descriptor():
    assert is_panel_descriptor("panel:deep")
    assert is_panel_descriptor({"provider": "panel", "aggregator": "x"})
    assert not is_panel_descriptor("gpt-4o")
    assert not is_panel_descriptor("anthropic/claude-3-5-sonnet")
    assert not is_panel_descriptor({"model": "gpt-4o"})
    assert not is_panel_descriptor(None)


def test_resolve_panel_config_dict():
    cfg = resolve_panel_config(
        {"provider": "panel", "references": ["a", "b"], "aggregator": "c"}
    )
    assert cfg == {"references": ["a", "b"], "aggregator": "c", "enabled": True}


def test_resolve_panel_config_preset():
    register_panel_preset("unit_deep", {"references": ["a"], "aggregator": "c"})
    try:
        cfg = resolve_panel_config("panel:unit_deep")
        assert cfg["aggregator"] == "c"
        assert cfg["references"] == ["a"]
    finally:
        PANEL_PRESETS.pop("unit_deep", None)


def test_resolve_panel_config_unknown_preset():
    with pytest.raises(ValueError, match="Unknown panel preset"):
        resolve_panel_config("panel:does_not_exist")


def test_resolve_panel_config_missing_aggregator():
    with pytest.raises(ValueError, match="aggregator"):
        resolve_panel_config({"provider": "panel", "references": ["a"]})


def test_recursion_guard_aggregator():
    with pytest.raises(ValueError, match="aggregator"):
        resolve_panel_config(
            {"provider": "panel", "references": ["a"], "aggregator": "panel:other"}
        )


def test_recursion_guard_reference():
    with pytest.raises(ValueError, match="references"):
        resolve_panel_config(
            {
                "provider": "panel",
                "references": ["panel:x"],
                "aggregator": "c",
            }
        )


def test_resolve_panel_config_rejects_non_string_references():
    with pytest.raises(ValueError, match="references"):
        resolve_panel_config(
            {"provider": "panel", "references": [{"model": "x"}], "aggregator": "c"}
        )


def test_resolve_panel_config_rejects_non_bool_enabled():
    with pytest.raises(ValueError, match="enabled"):
        resolve_panel_config(
            {"provider": "panel", "references": ["a"], "aggregator": "c", "enabled": "false"}
        )


def test_create_panel_llm_forwards_extra_descriptor_options(monkeypatch):
    import praisonaiagents.llm.panel as panel_mod

    captured = {}

    def fake_init(self, model=None, **kwargs):
        captured["model"] = model
        captured["kwargs"] = kwargs

    monkeypatch.setattr("praisonaiagents.llm.llm.LLM.__init__", fake_init)

    panel_mod.create_panel_llm(
        {
            "provider": "panel",
            "references": ["a"],
            "aggregator": "c",
            "base_url": "http://localhost:11434/v1",
            "api_key": "k",
        }
    )
    assert captured["model"] == "c"
    assert captured["kwargs"]["base_url"] == "http://localhost:11434/v1"
    assert captured["kwargs"]["api_key"] == "k"
    # Panel-only keys must not leak into the aggregator LLM kwargs.
    for key in ("references", "aggregator", "enabled", "provider"):
        assert key not in captured["kwargs"]


def _make_panel(monkeypatch, references, enabled=True):
    """Create a PanelLLM without invoking LLM.__init__ (no litellm needed)."""
    panel = PanelLLM.__new__(PanelLLM)
    panel.model = "aggregator-model"
    panel._panel_references = list(references)
    panel._panel_enabled = enabled
    panel._panel_reference_temperature = 0.0
    from collections import OrderedDict
    panel._panel_ref_cache = OrderedDict()
    panel._panel_ref_cache_max = 128
    panel._panel_ref_llms = {}
    return panel


def test_trimmed_view_drops_tools_and_system():
    view = PanelLLM._panel_trimmed_messages(
        prompt="latest user turn",
        system_prompt="SYSTEM PROMPT",
        chat_history=[
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": "tool output", "tool_call_id": "1"},
        ],
    )
    # System prompt, tool messages, and tool_calls assistant turn are dropped.
    assert view == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "latest user turn"},
    ]


def test_inject_into_prompt_string_tail():
    out = PanelLLM._inject_into_prompt("Do the task.", "\n\nGUIDANCE")
    assert out == "Do the task.\n\nGUIDANCE"


def test_inject_into_prompt_list_appends_to_last_text():
    prompt = [{"type": "text", "text": "first"}, {"type": "text", "text": "last"}]
    out = PanelLLM._inject_into_prompt(prompt, "\n\nG")
    assert out[-1]["text"] == "last\n\nG"
    assert out[0]["text"] == "first"


def test_get_response_injects_and_caches(monkeypatch):
    panel = _make_panel(monkeypatch, references=["ref1", "ref2"])

    calls = {"ref": 0}

    def fake_run_sync(view):
        calls["ref"] += 1
        return "\n\n[REFS]"

    captured = {}

    def fake_super_get_response(self, prompt, system_prompt=None, chat_history=None, **kwargs):
        captured["prompt"] = prompt
        return "AGG RESPONSE"

    monkeypatch.setattr(panel, "_run_references_sync", fake_run_sync)
    monkeypatch.setattr(
        "praisonaiagents.llm.llm.LLM.get_response", fake_super_get_response
    )

    out1 = panel.get_response(prompt="hello", system_prompt="SYS")
    assert out1 == "AGG RESPONSE"
    assert captured["prompt"] == "hello\n\n[REFS]"
    assert calls["ref"] == 1

    # Same trimmed view -> reference call cached (run once per turn signature).
    panel.get_response(prompt="hello", system_prompt="SYS")
    assert calls["ref"] == 1


def test_enabled_false_collapses_to_aggregator(monkeypatch):
    panel = _make_panel(monkeypatch, references=["ref1"], enabled=False)

    def fail_run_sync(view):
        raise AssertionError("references must not run when disabled")

    captured = {}

    def fake_super_get_response(self, prompt, system_prompt=None, chat_history=None, **kwargs):
        captured["prompt"] = prompt
        return "AGG"

    monkeypatch.setattr(panel, "_run_references_sync", fail_run_sync)
    monkeypatch.setattr(
        "praisonaiagents.llm.llm.LLM.get_response", fake_super_get_response
    )

    out = panel.get_response(prompt="hello")
    assert out == "AGG"
    # No guidance appended.
    assert captured["prompt"] == "hello"


def test_partial_failure_tolerance(monkeypatch):
    panel = _make_panel(monkeypatch, references=["good", "bad"])

    class FakeRefLLM:
        def __init__(self, model):
            self.model = model

        def get_response(self, **kwargs):
            if self.model == "bad":
                raise RuntimeError("network down")
            return "good perspective"

    monkeypatch.setattr(panel, "_get_reference_llm", lambda m: FakeRefLLM(m))

    guidance = panel._run_references_sync(
        [{"role": "user", "content": "q"}]
    )
    assert "good perspective" in guidance
    assert "unavailable" in guidance  # bad reference folded in as a note
    # Raw provider exception text must not be injected into the prompt.
    assert "network down" not in guidance
