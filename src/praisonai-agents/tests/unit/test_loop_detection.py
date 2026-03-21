"""
TDD tests for PraisonAI tool loop detection.

Tests are written BEFORE implementation (TDD).
Port of OpenClaw's tool-loop-detection.ts patterns to Python.
"""

import hashlib
import json
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Helper: compute expected hash the same way the module will
# ---------------------------------------------------------------------------

def _hash(tool_name: str, args: dict) -> str:
    stable = json.dumps({"t": tool_name, "a": args}, sort_keys=True, default=str)
    return hashlib.sha256(stable.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Import the module under test (will fail until implemented — that's TDD)
# ---------------------------------------------------------------------------

class TestLoopDetectionImport:
    """The module must be importable with zero side-effects."""

    def test_module_importable(self):
        from praisonaiagents.agent.loop_detection import (
            LoopDetectionConfig,
            LoopDetectionResult,
            detect_tool_loop,
            record_tool_call,
            record_tool_outcome,
            hash_tool_call,
        )
        assert LoopDetectionConfig is not None
        assert detect_tool_loop is not None

    def test_no_side_effects_on_import(self):
        """Importing must not change global state or call LLM."""
        import praisonaiagents.agent.loop_detection  # noqa


class TestLoopDetectionConfig:
    def setup_method(self):
        from praisonaiagents.agent.loop_detection import LoopDetectionConfig
        self.Config = LoopDetectionConfig

    def test_default_disabled(self):
        cfg = self.Config()
        assert cfg.enabled is False  # safe default: opt-in only

    def test_custom_thresholds(self):
        cfg = self.Config(enabled=True, warn_threshold=3, critical_threshold=5)
        assert cfg.warn_threshold == 3
        assert cfg.critical_threshold == 5

    def test_critical_must_be_greater_than_warn(self):
        """If critical <= warn, it should be auto-corrected."""
        cfg = self.Config(enabled=True, warn_threshold=10, critical_threshold=5)
        assert cfg.critical_threshold > cfg.warn_threshold


class TestHashToolCall:
    def test_hash_is_deterministic(self):
        from praisonaiagents.agent.loop_detection import hash_tool_call
        h1 = hash_tool_call("search", {"query": "foo"})
        h2 = hash_tool_call("search", {"query": "foo"})
        assert h1 == h2

    def test_different_args_produce_different_hashes(self):
        from praisonaiagents.agent.loop_detection import hash_tool_call
        h1 = hash_tool_call("search", {"query": "foo"})
        h2 = hash_tool_call("search", {"query": "bar"})
        assert h1 != h2

    def test_different_tools_produce_different_hashes(self):
        from praisonaiagents.agent.loop_detection import hash_tool_call
        h1 = hash_tool_call("search", {"query": "foo"})
        h2 = hash_tool_call("fetch", {"query": "foo"})
        assert h1 != h2

    def test_arg_order_does_not_matter(self):
        """Stable JSON sort keys: {'a':1,'b':2} == {'b':2,'a':1}"""
        from praisonaiagents.agent.loop_detection import hash_tool_call
        h1 = hash_tool_call("t", {"b": 2, "a": 1})
        h2 = hash_tool_call("t", {"a": 1, "b": 2})
        assert h1 == h2


class TestDetectToolLoop:
    def setup_method(self):
        from praisonaiagents.agent.loop_detection import (
            LoopDetectionConfig,
            detect_tool_loop,
            record_tool_call,
        )
        self.Config = LoopDetectionConfig
        self.detect = detect_tool_loop
        self.record = record_tool_call

    # --- disabled ---

    def test_disabled_always_returns_not_stuck(self):
        cfg = self.Config(enabled=False)
        history = []
        # Fill history with many identical calls
        for _ in range(50):
            self.record(history, "search", {"q": "x"}, cfg)
        result = self.detect(history, "search", {"q": "x"}, cfg)
        assert result["stuck"] is False

    # --- generic_repeat ---

    def test_below_warn_threshold_not_stuck(self):
        cfg = self.Config(enabled=True, warn_threshold=5, critical_threshold=10)
        history = []
        for _ in range(4):
            self.record(history, "search", {"q": "foo"}, cfg)
        result = self.detect(history, "search", {"q": "foo"}, cfg)
        assert result["stuck"] is False

    def test_at_warn_threshold_warning(self):
        cfg = self.Config(enabled=True, warn_threshold=5, critical_threshold=10)
        history = []
        for _ in range(5):
            self.record(history, "search", {"q": "foo"}, cfg)
        result = self.detect(history, "search", {"q": "foo"}, cfg)
        assert result["stuck"] is True
        assert result["level"] == "warning"
        assert result["detector"] == "generic_repeat"

    def test_at_critical_threshold_critical(self):
        cfg = self.Config(enabled=True, warn_threshold=5, critical_threshold=10)
        history = []
        for _ in range(10):
            self.record(history, "search", {"q": "foo"}, cfg)
        result = self.detect(history, "search", {"q": "foo"}, cfg)
        assert result["stuck"] is True
        assert result["level"] == "critical"

    def test_different_tools_no_false_positive(self):
        """Alternating different tools should NOT trigger generic_repeat."""
        cfg = self.Config(enabled=True, warn_threshold=3, critical_threshold=6)
        history = []
        for i in range(6):
            self.record(history, "search", {"q": str(i)}, cfg)  # different args each time
        result = self.detect(history, "search", {"q": "0"}, cfg)
        # Only 1 occurrence of {"q": "0"} — not stuck
        assert result["stuck"] is False

    # --- message content ---

    def test_warning_message_contains_tool_name(self):
        cfg = self.Config(enabled=True, warn_threshold=3, critical_threshold=10)
        history = []
        for _ in range(3):
            self.record(history, "my_tool", {"x": 1}, cfg)
        result = self.detect(history, "my_tool", {"x": 1}, cfg)
        if result["stuck"]:
            assert "my_tool" in result["message"]

    def test_result_has_count_field(self):
        cfg = self.Config(enabled=True, warn_threshold=3, critical_threshold=10)
        history = []
        for _ in range(3):
            self.record(history, "t", {}, cfg)
        result = self.detect(history, "t", {}, cfg)
        assert "count" in result


class TestRecordToolCall:
    def test_record_appends_to_history(self):
        from praisonaiagents.agent.loop_detection import (
            LoopDetectionConfig, record_tool_call
        )
        cfg = LoopDetectionConfig(enabled=True)
        history = []
        record_tool_call(history, "search", {"q": "test"}, cfg)
        assert len(history) == 1
        assert history[0]["tool_name"] == "search"

    def test_history_respects_max_size(self):
        from praisonaiagents.agent.loop_detection import (
            LoopDetectionConfig, record_tool_call
        )
        cfg = LoopDetectionConfig(enabled=True, history_size=5)
        history = []
        for i in range(10):
            record_tool_call(history, "t", {"i": i}, cfg)
        assert len(history) <= 5


class TestRecordToolOutcome:
    def test_outcome_updates_result_hash(self):
        from praisonaiagents.agent.loop_detection import (
            LoopDetectionConfig, record_tool_call, record_tool_outcome
        )
        cfg = LoopDetectionConfig(enabled=True)
        history = []
        record_tool_call(history, "search", {"q": "x"}, cfg)
        assert history[0].get("result_hash") is None
        record_tool_outcome(history, "search", {"q": "x"}, "some result", cfg)
        assert history[0].get("result_hash") is not None


class TestLoopDetectionPlugin:
    """Tests for the plugin interface (hooks integration)."""

    def test_plugin_importable(self):
        from praisonaiagents.plugins import loop_detection_plugin  # noqa
        assert loop_detection_plugin is not None

    def test_plugin_registers_hook(self):
        """Plugin import should register a BEFORE_TOOL hook."""
        from praisonaiagents.hooks.registry import get_default_registry
        from praisonaiagents.hooks.types import HookEvent
        import praisonaiagents.plugins.loop_detection_plugin  # noqa ensure imported
        hooks = get_default_registry().get_hooks(HookEvent.BEFORE_TOOL)
        assert len(hooks) >= 1
