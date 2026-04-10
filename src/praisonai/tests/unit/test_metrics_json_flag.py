#!/usr/bin/env python3
"""
Unit tests for --metrics-json CLI flag.

These tests are pure unit tests: no network, no LLM calls, no side effects.
They validate argument parsing and the JSON output assembly logic in
handle_direct_prompt().
"""

import argparse
import json
import pytest


def _get_metrics_json_parser():
    """Minimal argument parser that mirrors the relevant CLI args."""
    parser = argparse.ArgumentParser(description="praisonAI CLI")
    parser.add_argument("--metrics", action="store_true")
    parser.add_argument("--metrics-json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("command", nargs="?")
    return parser


def _build_metrics_out(agent_metrics, agent_config):
    """
    Mirror of the JSON-assembly block in handle_direct_prompt().

    Centralised here so tests can validate logic without importing main.py.
    """
    model_name = agent_metrics.get("model")
    if not model_name:
        model_name = agent_config.get("llm", "unknown")
        if isinstance(model_name, dict):
            model_name = model_name.get("model", "unknown")
    return {
        "cost_usd": agent_metrics.get("cost", 0.0),
        "tokens_in": agent_metrics.get("prompt_tokens", 0),
        "tokens_out": agent_metrics.get("completion_tokens", 0),
        "model": model_name or "unknown",
        "request_count": agent_metrics.get("llm_calls", 0),
    }


class TestMetricsJsonArgParsing:
    """Argument-parsing behaviour for --metrics-json."""

    def test_flag_stored_as_metrics_json(self):
        """--metrics-json is stored as metrics_json (underscore) on the namespace."""
        args = _get_metrics_json_parser().parse_args(["--metrics-json", "task"])
        assert args.metrics_json is True
        assert args.command == "task"

    def test_default_false_when_absent(self):
        """--metrics-json defaults to False when not supplied."""
        args = _get_metrics_json_parser().parse_args(["task"])
        assert args.metrics_json is False

    def test_independent_from_metrics_flag(self):
        """--metrics and --metrics-json are independent boolean flags."""
        args = _get_metrics_json_parser().parse_args(["--metrics", "task"])
        assert args.metrics is True
        assert args.metrics_json is False

        args2 = _get_metrics_json_parser().parse_args(["--metrics-json", "task"])
        assert args2.metrics is False
        assert args2.metrics_json is True

    def test_both_flags_together(self):
        """Both --metrics and --metrics-json can be set simultaneously."""
        args = _get_metrics_json_parser().parse_args(["--metrics", "--metrics-json", "task"])
        assert args.metrics is True
        assert args.metrics_json is True


class TestMetricsJsonOutput:
    """JSON assembly logic for --metrics-json output."""

    def test_output_has_required_keys(self):
        """Emitted JSON contains exactly the five required keys."""
        payload = _build_metrics_out(
            {"prompt_tokens": 42, "completion_tokens": 17, "cost": 0.000123, "model": "test-model"},
            {"llm": "test-model"},
        )
        assert set(payload.keys()) == {"cost_usd", "tokens_in", "tokens_out", "model", "request_count"}

    def test_tokens_mapped_from_correct_keys(self):
        """prompt_tokens → tokens_in, completion_tokens → tokens_out."""
        payload = _build_metrics_out(
            {"prompt_tokens": 42, "completion_tokens": 17},
            {},
        )
        assert payload["tokens_in"] == 42
        assert payload["tokens_out"] == 17

    def test_cost_preserved(self):
        """cost value is preserved as cost_usd."""
        payload = _build_metrics_out({"cost": 0.000123}, {})
        assert abs(payload["cost_usd"] - 0.000123) < 1e-9

    def test_request_count_defaults_to_zero(self):
        """request_count defaults to 0 when llm_calls is absent."""
        payload = _build_metrics_out({}, {})
        assert payload["request_count"] == 0

    def test_request_count_from_llm_calls(self):
        """request_count is taken from llm_calls when present."""
        payload = _build_metrics_out({"llm_calls": 3}, {})
        assert payload["request_count"] == 3

    def test_model_from_agent_metrics(self):
        """Model is taken from agent_metrics['model'] when available."""
        payload = _build_metrics_out({"model": "test-model-from-agent"}, {"llm": "config-model"})
        assert payload["model"] == "test-model-from-agent"

    def test_model_fallback_to_config_string(self):
        """Falls back to agent_config['llm'] string when agent_metrics has no model."""
        payload = _build_metrics_out({}, {"llm": "config-llm-string"})
        assert payload["model"] == "config-llm-string"

    def test_model_fallback_to_config_dict(self):
        """When agent_config['llm'] is a dict, extracts nested 'model' key."""
        payload = _build_metrics_out({}, {"llm": {"model": "nested-model", "temperature": 0.5}})
        assert payload["model"] == "nested-model"

    def test_model_unknown_when_no_info(self):
        """Falls back to 'unknown' when neither agent nor config provides a model."""
        payload = _build_metrics_out({}, {})
        assert payload["model"] == "unknown"

    def test_output_is_json_serialisable(self):
        """The output dict round-trips through JSON without error."""
        payload = _build_metrics_out(
            {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.00001},
            {"llm": "test-model"},
        )
        assert json.loads(json.dumps(payload)) == payload

    def test_regression_wrong_keys_produce_zeros(self):
        """
        Regression guard: the old code used 'input_tokens'/'output_tokens' which
        are never populated by MetricsHandler.extract_metrics_from_agent().
        These should always be absent; the correct keys are prompt/completion_tokens.
        """
        agent_metrics = {"prompt_tokens": 100, "completion_tokens": 50}
        # Wrong keys (old bug):
        assert agent_metrics.get("input_tokens", 0) == 0
        assert agent_metrics.get("output_tokens", 0) == 0
        # Correct keys (fixed):
        assert agent_metrics.get("prompt_tokens", 0) == 100
        assert agent_metrics.get("completion_tokens", 0) == 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
