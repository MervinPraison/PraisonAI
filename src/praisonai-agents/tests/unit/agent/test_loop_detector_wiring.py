"""
Tests for wiring the result-aware tool-loop detector into the tool-execution path.

Covers issue #3001: the result-aware detector (name + args + result-hash,
ping-pong) must actually run in the tool loop, and the doom-loop feed must no
longer be fed a constant success=True.
"""

import pytest
from unittest.mock import patch

from praisonaiagents import Agent


def _make_agent():
    return Agent(instructions="Test agent", output="silent")


def _run_tool(agent, name, arguments):
    """Invoke the tool-execution path directly with a stubbed tool impl."""
    return agent._execute_tool_with_context(
        function_name=name,
        arguments=arguments,
        tool_call_id="tc-1",
        state=None,
    )


class TestDetectorEnabledByDefault:
    def test_detector_enabled_by_default(self):
        agent = _make_agent()
        history, config = agent._ensure_loop_detector()
        assert config.enabled is True
        assert history == []


class TestResultAwareToolPath:
    """The detector must key on name+args+output, not just name+args."""

    def test_polling_changing_output_not_flagged(self):
        """Same tool+args, different result each call -> no loop flagged."""
        agent = _make_agent()
        _, config = agent._ensure_loop_detector()
        # Tune thresholds low so a false positive would be obvious.
        config.warn_threshold = 3
        config.critical_threshold = 5

        counter = {"n": 0}

        def _impl(function_name, arguments):
            counter["n"] += 1
            return f"result-{counter['n']}"  # changing output each call

        with patch.object(agent, "_execute_tool_with_circuit_breaker", side_effect=_impl):
            results = [_run_tool(agent, "poll_status", {"id": 1}) for _ in range(8)]

        assert all(
            not (isinstance(r, dict) and r.get("loop_blocked")) for r in results
        )

    def test_identical_output_repeat_flagged(self):
        """Same tool+args+output N times -> critical block."""
        agent = _make_agent()
        _, config = agent._ensure_loop_detector()
        config.warn_threshold = 3
        config.critical_threshold = 5

        with patch.object(
            agent,
            "_execute_tool_with_circuit_breaker",
            return_value="constant-output",
        ):
            results = [_run_tool(agent, "check_status", {"id": 1}) for _ in range(8)]

        assert any(
            isinstance(r, dict) and r.get("loop_blocked") for r in results
        ), "identical-output polling loop should be blocked"

    def test_generic_repeat_identical_args_flagged(self):
        """Non-poll tool called with identical args N times -> critical."""
        agent = _make_agent()
        _, config = agent._ensure_loop_detector()
        config.warn_threshold = 3
        config.critical_threshold = 5

        with patch.object(
            agent,
            "_execute_tool_with_circuit_breaker",
            return_value="ok",
        ):
            results = [_run_tool(agent, "write_file", {"path": "a"}) for _ in range(8)]

        assert any(
            isinstance(r, dict) and r.get("loop_blocked") for r in results
        )

    def test_two_tier_self_correction_then_stop(self):
        """Warning queues a self-correction nudge; persistence escalates to block."""
        agent = _make_agent()
        _, config = agent._ensure_loop_detector()
        config.warn_threshold = 3
        config.critical_threshold = 6
        agent._loop_warned_this_turn = False

        blocked = None
        with patch.object(
            agent,
            "_execute_tool_with_circuit_breaker",
            return_value="ok",
        ):
            for _ in range(config.warn_threshold):
                _run_tool(agent, "write_file", {"path": "a"})
            # After hitting warn threshold, a self-correction nudge is queued.
            assert agent._pending_self_correction is not None
            # Continue until critical -> block.
            for _ in range(config.critical_threshold):
                r = _run_tool(agent, "write_file", {"path": "a"})
                if isinstance(r, dict) and r.get("loop_blocked"):
                    blocked = r
                    break

        assert blocked is not None


class TestDetectorWiredIntoRealRun:
    def test_detector_invoked_during_multi_tool_run(self):
        """record_tool_call / record_tool_outcome / detect_tool_loop are invoked."""
        agent = _make_agent()

        called = {"call": 0, "outcome": 0, "detect": 0}

        from praisonaiagents.agent import loop_detection as _ld
        orig_call = _ld.record_tool_call
        orig_outcome = _ld.record_tool_outcome
        orig_detect = _ld.detect_tool_loop

        def _c(*a, **k):
            called["call"] += 1
            return orig_call(*a, **k)

        def _o(*a, **k):
            called["outcome"] += 1
            return orig_outcome(*a, **k)

        def _d(*a, **k):
            called["detect"] += 1
            return orig_detect(*a, **k)

        with patch.object(_ld, "record_tool_call", side_effect=_c), \
             patch.object(_ld, "record_tool_outcome", side_effect=_o), \
             patch.object(_ld, "detect_tool_loop", side_effect=_d), \
             patch.object(agent, "_execute_tool_with_circuit_breaker", return_value="ok"):
            _run_tool(agent, "my_tool", {"x": 1})

        assert called["call"] >= 1
        assert called["outcome"] >= 1
        assert called["detect"] >= 1


class TestBackwardCompat:
    def test_normal_run_not_flagged(self):
        """A normal, non-looping sequence of tool calls is unaffected."""
        agent = _make_agent()
        _, config = agent._ensure_loop_detector()
        config.warn_threshold = 3
        config.critical_threshold = 5

        with patch.object(
            agent,
            "_execute_tool_with_circuit_breaker",
            side_effect=lambda n, a: f"ok-{a}",
        ):
            results = [
                _run_tool(agent, "write_file", {"path": f"file-{i}"})
                for i in range(8)
            ]

        assert all(
            not (isinstance(r, dict) and r.get("loop_blocked")) for r in results
        )


class TestDoomLoopFeedFixed:
    def test_response_failure_signal_used(self):
        """_response_indicates_failure derives a real success bool (not True)."""
        agent = _make_agent()
        assert agent._response_indicates_failure("Traceback (most recent call last): ...")
        assert agent._response_indicates_failure("I failed to complete the task")
        assert not agent._response_indicates_failure("Here is the completed report.")
        # Partial-success phrasing must NOT be treated as a failure: the agent
        # may complete via an alternate path while noting missing optional data.
        assert not agent._response_indicates_failure(
            "I was unable to fetch the optional metadata, but finished the report."
        )

    def test_failure_streak_recorded_as_false(self):
        """Failing iterations are recorded as success=False (not hard-coded True)."""
        agent = _make_agent()

        recorded = []

        class _StubTracker:
            def record(self, action_type, args, result, success):
                recorded.append(success)

        agent._doom_loop_tracker = _StubTracker()

        for _ in range(5):
            success = not agent._response_indicates_failure("An error occurred while running.")
            agent._record_action("chat", {"response_hash": 1}, "err", success)

        # Previously every entry was hard-coded True; now failures are False.
        assert recorded == [False] * 5
