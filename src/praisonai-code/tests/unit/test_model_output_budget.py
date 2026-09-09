"""Tests for model-aware ``run --max-tokens`` resolution."""

from types import SimpleNamespace

from praisonai_code.cli.commands import run as run_command


def test_default_budget_is_capped_to_known_model_limit(monkeypatch):
    monkeypatch.setattr(
        "praisonaiagents.llm.model_capabilities.max_output_tokens",
        lambda model: 8192,
    )

    assert run_command._resolve_max_tokens("provider/model", None) == 8192


def test_default_budget_uses_large_known_model_limit(monkeypatch):
    monkeypatch.setattr(
        "praisonaiagents.llm.model_capabilities.max_output_tokens",
        lambda model: 32768,
    )

    assert run_command._resolve_max_tokens("provider/model", None) == 32768


def test_explicit_budget_is_capped_with_warning(monkeypatch):
    monkeypatch.setattr(
        "praisonaiagents.llm.model_capabilities.max_output_tokens",
        lambda model: 8192,
    )
    warnings = []
    output = SimpleNamespace(print_warning=warnings.append)

    assert run_command._resolve_max_tokens(
        "provider/model", 12000, output=output
    ) == 8192
    assert warnings == [
        "--max-tokens 12000 exceeds provider/model's output limit (8192); "
        "clamping to 8192"
    ]


def test_explicit_budget_warning_is_single_ndjson_event_in_stream_mode(monkeypatch):
    monkeypatch.setattr(
        "praisonaiagents.llm.model_capabilities.max_output_tokens",
        lambda model: 8192,
    )
    events = []
    output = SimpleNamespace(
        mode=SimpleNamespace(value="stream-json"),
        emit_event=lambda *args, **kwargs: events.append((args, kwargs)),
        is_json_mode=True,
    )

    assert run_command._resolve_max_tokens(
        "provider/model", 12000, output=output
    ) == 8192
    assert events == [
        (
            ("warning",),
            {
                "message": "--max-tokens 12000 exceeds provider/model's output limit (8192); clamping to 8192",
                "data": {"code": "max_tokens_clamped"},
            },
        )
    ]


def test_unknown_model_preserves_historical_default(monkeypatch):
    monkeypatch.setattr(
        "praisonaiagents.llm.model_capabilities.max_output_tokens",
        lambda model: None,
    )

    assert run_command._resolve_max_tokens("unknown/model", None) == 16000


def test_llm_spec_budget_preserves_existing_options():
    spec = {"model": "provider/model", "temperature": 0.2}

    resolved = run_command._llm_spec_with_max_tokens(spec, None, 4096)

    assert resolved == {
        "model": "provider/model",
        "temperature": 0.2,
        "max_tokens": 4096,
    }
    assert spec == {"model": "provider/model", "temperature": 0.2}
