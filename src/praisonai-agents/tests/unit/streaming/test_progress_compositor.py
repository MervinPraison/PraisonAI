"""
Unit tests for the progress-feed compositor (praisonaiagents.streaming.progress).

Covers:
- merge_progress_line correlates a tool's start and finish onto one line
- error state takes precedence and is not downgraded
- non-progress events are a no-op passthrough
- render_progress renders a bounded, word-aware rolling window
- exports are reachable from praisonaiagents.streaming
"""

from praisonaiagents.streaming.events import StreamEvent, StreamEventType
from praisonaiagents.streaming.progress import (
    ProgressLine,
    merge_progress_line,
    render_progress,
    STATE_DONE,
    STATE_ERROR,
    STATE_RUNNING,
)


class TestMergeProgressLine:
    def test_start_then_finish_coalesce_by_id(self):
        lines = []
        lines = merge_progress_line(
            lines,
            StreamEvent(type=StreamEventType.TOOL_CALL_START,
                        tool_call={"id": "a", "name": "web_search"}),
        )
        assert len(lines) == 1
        assert lines[0].state == STATE_RUNNING
        assert lines[0].kind == "tool"

        lines = merge_progress_line(
            lines,
            StreamEvent(type=StreamEventType.TOOL_CALL_RESULT,
                        tool_call={"id": "a", "name": "web_search",
                                   "result_summary": "5 results"}),
        )
        # Same id → same single line, now done
        assert len(lines) == 1
        assert lines[0].state == STATE_DONE
        assert "5 results" in lines[0].text

    def test_distinct_ids_append(self):
        lines = []
        for i, name in enumerate(["a", "b", "c"]):
            lines = merge_progress_line(
                lines,
                StreamEvent(type=StreamEventType.TOOL_CALL_START,
                            tool_call={"id": name, "name": f"tool_{i}"}),
            )
        assert len(lines) == 3

    def test_error_takes_precedence(self):
        lines = merge_progress_line(
            [],
            StreamEvent(type=StreamEventType.TOOL_CALL_START,
                        tool_call={"id": "x", "name": "write_file"}),
        )
        lines = merge_progress_line(
            lines, StreamEvent(type=StreamEventType.ERROR, metadata={"id": "x"})
        )
        assert lines[0].state == STATE_ERROR
        # A subsequent done event must not downgrade an errored line
        lines = merge_progress_line(
            lines,
            StreamEvent(type=StreamEventType.TOOL_CALL_RESULT,
                        tool_call={"id": "x", "name": "write_file"}),
        )
        assert lines[0].state == STATE_ERROR

    def test_done_not_downgraded_by_late_running(self):
        lines = merge_progress_line(
            [],
            StreamEvent(type=StreamEventType.TOOL_CALL_START,
                        tool_call={"id": "d", "name": "write_file"}),
        )
        lines = merge_progress_line(
            lines,
            StreamEvent(type=StreamEventType.TOOL_CALL_RESULT,
                        tool_call={"id": "d", "name": "write_file"}),
        )
        assert lines[0].state == STATE_DONE
        # A late/overlapping running event must not reset a completed line
        lines = merge_progress_line(
            lines,
            StreamEvent(type=StreamEventType.DELTA_TOOL_CALL,
                        tool_call={"id": "d", "name": "write_file"}),
        )
        assert lines[0].state == STATE_DONE

    def test_non_progress_event_is_noop(self):
        lines = [ProgressLine("a", "tool", "web_search", STATE_DONE)]
        out = merge_progress_line(
            lines, StreamEvent(type=StreamEventType.DELTA_TEXT, content="hi")
        )
        assert out == lines

    def test_does_not_mutate_input(self):
        lines = []
        merge_progress_line(
            lines,
            StreamEvent(type=StreamEventType.TOOL_CALL_START,
                        tool_call={"id": "a", "name": "web_search"}),
        )
        assert lines == []

    def test_falls_back_to_tool_name_id(self):
        lines = merge_progress_line(
            [],
            StreamEvent(type=StreamEventType.TOOL_CALL_START,
                        tool_call={"name": "web_search"}),
        )
        # No explicit id → correlate on name
        lines = merge_progress_line(
            lines,
            StreamEvent(type=StreamEventType.TOOL_CALL_RESULT,
                        tool_call={"name": "web_search"}),
        )
        assert len(lines) == 1
        assert lines[0].state == STATE_DONE


class TestRenderProgress:
    def test_empty(self):
        assert render_progress([]) == ""

    def test_glyphs_and_lines(self):
        lines = [
            ProgressLine("a", "tool", "web_search — 5 results", STATE_DONE),
            ProgressLine("b", "tool", "fetch_url", STATE_RUNNING),
        ]
        out = render_progress(lines)
        assert "✓ web_search — 5 results" in out
        assert "⏳ fetch_url" in out
        assert out.count("\n") == 1

    def test_bounded_window(self):
        lines = [ProgressLine(str(i), "tool", f"t{i}", STATE_DONE) for i in range(20)]
        out = render_progress(lines, max_lines=3)
        assert len(out.splitlines()) == 3
        # Only the trailing lines survive
        assert "t19" in out
        assert "t0" not in out

    def test_word_aware_truncation_respects_cap(self):
        line = ProgressLine("x", "tool", "alpha beta gamma delta epsilon", STATE_DONE)
        out = render_progress([line], max_line_chars=15)
        assert len(out) <= 15
        assert out.endswith("…")
