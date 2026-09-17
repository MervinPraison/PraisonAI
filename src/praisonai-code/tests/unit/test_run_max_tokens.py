"""Tests for model-aware `--max-tokens` resolution on `praisonai run` (#5017).

`run.py` must derive/clamp the output budget against the resolved model's real
output ceiling and thread the resolved value into every dispatch path that
builds an agent (default prompt, actions fast path, custom `--agent`), instead
of sending an over-limit request that the provider 400s on.
"""

from unittest.mock import patch

from praisonai_code.cli.commands import run as run_cmd


class _RecordingOutput:
    def __init__(self):
        self.warnings = []

    def print_warning(self, message):
        self.warnings.append(message)


def _patch_ceiling(value):
    """Patch the core accessor imported inside ``_resolve_max_tokens``."""
    return patch(
        "praisonaiagents.llm.model_capabilities.max_output_tokens",
        return_value=value,
    )


def test_resolve_no_model_returns_unchanged():
    out = _RecordingOutput()
    assert run_cmd._resolve_max_tokens(None, 16000, False, out) == 16000
    assert out.warnings == []


def test_resolve_unknown_ceiling_keeps_constant():
    out = _RecordingOutput()
    with _patch_ceiling(None):
        assert run_cmd._resolve_max_tokens("mystery-model", 16000, False, out) == 16000
    assert out.warnings == []


def test_resolve_unset_small_model_uses_ceiling():
    # Unset default (16000) on a 4096-ceiling model must drop to the ceiling.
    out = _RecordingOutput()
    with _patch_ceiling(4096):
        assert run_cmd._resolve_max_tokens("gpt-3.5-turbo", 16000, False, out) == 4096
    assert out.warnings == []


def test_resolve_unset_large_model_capped_at_preferred():
    # A high-ceiling model still keeps the preferred constant when unset.
    out = _RecordingOutput()
    with _patch_ceiling(100000):
        assert run_cmd._resolve_max_tokens("o3", 16000, False, out) == 16000
    assert out.warnings == []


def test_resolve_explicit_over_ceiling_clamps_and_warns():
    out = _RecordingOutput()
    with _patch_ceiling(8192):
        assert run_cmd._resolve_max_tokens("gemini-1.5-flash", 32000, True, out) == 8192
    assert len(out.warnings) == 1
    assert "clamping to 8192" in out.warnings[0]


def test_resolve_explicit_under_ceiling_unchanged():
    out = _RecordingOutput()
    with _patch_ceiling(8192):
        assert run_cmd._resolve_max_tokens("gemini-1.5-flash", 2000, True, out) == 2000
    assert out.warnings == []


def test_apply_max_tokens_string_llm_becomes_dict():
    cfg = {"name": "A", "llm": "gpt-4o"}
    run_cmd._apply_max_tokens(cfg, 4096)
    assert cfg["llm"] == {"model": "gpt-4o", "max_tokens": 4096}


def test_apply_max_tokens_dict_llm_sets_default_only():
    cfg = {"llm": {"model": "gpt-4o", "max_tokens": 1234}}
    run_cmd._apply_max_tokens(cfg, 4096)
    # An already-pinned budget wins (setdefault does not overwrite).
    assert cfg["llm"]["max_tokens"] == 1234


def test_apply_max_tokens_no_budget_noop():
    cfg = {"llm": "gpt-4o"}
    run_cmd._apply_max_tokens(cfg, None)
    assert cfg["llm"] == "gpt-4o"


def test_apply_max_tokens_no_llm_key_noop():
    cfg = {"name": "A"}
    run_cmd._apply_max_tokens(cfg, 4096)
    assert "llm" not in cfg
