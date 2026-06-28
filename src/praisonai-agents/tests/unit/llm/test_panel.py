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


def test_reference_llms_receive_connection_settings(monkeypatch):
    """Reference models must use the same backend/credentials as the aggregator."""
    import praisonaiagents.llm.panel as panel_mod

    captured = []

    def fake_init(self, model=None, **kwargs):
        captured.append({"model": model, **kwargs})

    monkeypatch.setattr("praisonaiagents.llm.llm.LLM.__init__", fake_init)

    panel = panel_mod.create_panel_llm(
        {
            "provider": "panel",
            "references": ["ref-a", "ref-b"],
            "aggregator": "agg",
            "base_url": "http://custom-ollama:11434/v1",
            "api_key": "secret",
            "auth": "claude-code",
        }
    )
    # Building a reference LLM must forward the connection + credential settings
    # (including subscription auth) so references hit the same backend.
    panel._get_reference_llm("ref-a")
    ref_call = captured[-1]
    assert ref_call["model"] == "ref-a"
    assert ref_call["base_url"] == "http://custom-ollama:11434/v1"
    assert ref_call["api_key"] == "secret"
    assert ref_call["auth"] == "claude-code"


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
    panel._panel_ref_kwargs = {}
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


# ---------------------------------------------------------------------------
# Async parity: the async path shares the same cache/inject/trim helpers, but
# is verified independently so regressions in get_response_async are caught.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_response_async_injects_and_caches(monkeypatch):
    panel = _make_panel(monkeypatch, references=["ref1", "ref2"])

    calls = {"ref": 0}

    async def fake_run_async(view):
        calls["ref"] += 1
        return "\n\n[REFS]"

    captured = {}

    async def fake_super_get_response_async(
        self, prompt, system_prompt=None, chat_history=None, **kwargs
    ):
        captured["prompt"] = prompt
        return "AGG RESPONSE"

    monkeypatch.setattr(panel, "_run_references_async", fake_run_async)
    monkeypatch.setattr(
        "praisonaiagents.llm.llm.LLM.get_response_async", fake_super_get_response_async
    )

    out1 = await panel.get_response_async(prompt="hello", system_prompt="SYS")
    assert out1 == "AGG RESPONSE"
    assert captured["prompt"] == "hello\n\n[REFS]"
    assert calls["ref"] == 1

    # Same trimmed view -> reference call cached (run once per turn signature).
    await panel.get_response_async(prompt="hello", system_prompt="SYS")
    assert calls["ref"] == 1


@pytest.mark.asyncio
async def test_get_response_async_enabled_false_collapses(monkeypatch):
    panel = _make_panel(monkeypatch, references=["ref1"], enabled=False)

    async def fail_run_async(view):
        raise AssertionError("references must not run when disabled")

    captured = {}

    async def fake_super_get_response_async(
        self, prompt, system_prompt=None, chat_history=None, **kwargs
    ):
        captured["prompt"] = prompt
        return "AGG"

    monkeypatch.setattr(panel, "_run_references_async", fail_run_async)
    monkeypatch.setattr(
        "praisonaiagents.llm.llm.LLM.get_response_async", fake_super_get_response_async
    )

    out = await panel.get_response_async(prompt="hello")
    assert out == "AGG"
    assert captured["prompt"] == "hello"


@pytest.mark.asyncio
async def test_async_partial_failure_tolerance(monkeypatch):
    panel = _make_panel(monkeypatch, references=["good", "bad"])

    class FakeRefLLM:
        def __init__(self, model):
            self.model = model

        async def get_response_async(self, **kwargs):
            if self.model == "bad":
                raise RuntimeError("network down")
            return "good perspective"

    monkeypatch.setattr(panel, "_get_reference_llm", lambda m: FakeRefLLM(m))

    guidance = await panel._run_references_async(
        [{"role": "user", "content": "q"}]
    )
    assert "good perspective" in guidance
    assert "unavailable" in guidance
    # Raw provider exception text must not be injected into the prompt.
    assert "network down" not in guidance


# ---------------------------------------------------------------------------
# Agent wiring: a panel descriptor resolves to a PanelLLM and Agent-level
# connection settings (base_url/api_key) are forwarded to the aggregator.
# ---------------------------------------------------------------------------


def test_agent_panel_descriptor_forwards_connection_settings(monkeypatch):
    import praisonaiagents.llm.panel as panel_mod
    from praisonaiagents.agent.agent import Agent

    captured = {}

    def fake_create_panel_llm(descriptor, **kwargs):
        captured["descriptor"] = descriptor
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(panel_mod, "create_panel_llm", fake_create_panel_llm)

    agent = Agent(
        instructions="x",
        llm={"provider": "panel", "references": ["a"], "aggregator": "c"},
        base_url="http://localhost:11434/v1",
        api_key="k",
        auth="claude-code",
    )
    # Lazy build of the panel LLM forwards Agent connection settings.
    agent._ensure_llm_instance()
    assert captured["kwargs"]["base_url"] == "http://localhost:11434/v1"
    assert captured["kwargs"]["api_key"] == "k"
    # Execution options the normal LLM paths preserve must also reach the panel.
    assert captured["kwargs"]["auth"] == "claude-code"
    assert "max_iter" in captured["kwargs"]
    assert captured["descriptor"]["aggregator"] == "c"


def test_agent_non_panel_llm_unaffected():
    from praisonaiagents.agent.agent import Agent

    agent = Agent(instructions="x", llm="gpt-4o-mini")
    # Non-panel selection must not be treated as a panel descriptor.
    assert agent._panel_descriptor is None
