"""
Unit tests for in-loop context management and accurate token counting.

Covers:
- Accurate token counting (tiktoken with heuristic fallback + tool_calls payloads)
- clear_tool_results() clearing old tool outputs while keeping tool_calls
- LLM._manage_context_in_loop tiered clear/compact behaviour
- Backward-compat when in-loop management is disabled
"""

import sys
from unittest.mock import Mock

import pytest

from praisonaiagents.compaction.config import CompactionConfig
from praisonaiagents.compaction.strategy import CompactionStrategy
from praisonaiagents.compaction.compactor import ContextCompactor


# =============================================================================
# Token counting
# =============================================================================

class TestTokenCounting:
    def test_count_tokens_falls_back_when_tiktoken_absent(self, monkeypatch):
        """With tiktoken unavailable, heuristic fallback is used (no crash)."""
        monkeypatch.setitem(sys.modules, "tiktoken", None)
        compactor = ContextCompactor()
        assert compactor.estimate_tokens("hello world this is text") > 0

    def test_empty_text_is_zero(self):
        compactor = ContextCompactor()
        assert compactor.estimate_tokens("") == 0

    def test_tool_calls_payload_is_counted(self):
        """Messages with tool_calls should count more than an empty message."""
        compactor = ContextCompactor()
        plain = {"role": "assistant", "content": ""}
        with_calls = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "search",
                        "arguments": '{"query": "a very long search query string here"}',
                    },
                }
            ],
        }
        assert compactor.count_message_tokens(with_calls) > compactor.count_message_tokens(plain)


# =============================================================================
# clear_tool_results
# =============================================================================

class TestClearToolResults:
    def _build_messages(self, n_tools=10):
        messages = [{"role": "system", "content": "sys"}]
        for i in range(n_tools):
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": f"c{i}", "function": {"name": "f", "arguments": "{}"}}],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": f"c{i}",
                "content": f"verbose tool output number {i} " * 20,
            })
        return messages

    def test_old_tool_results_cleared_recent_preserved(self):
        compactor = ContextCompactor()
        messages = self._build_messages(n_tools=10)
        placeholder = "[tool result cleared to save context; re-fetch if needed]"

        out = compactor.clear_tool_results(messages, keep_recent=6, placeholder=placeholder)

        tool_msgs = [m for m in out if m.get("role") == "tool"]
        cleared = [m for m in tool_msgs if m["content"] == placeholder]
        kept = [m for m in tool_msgs if m["content"] != placeholder]

        assert len(cleared) == 4  # 10 total - 6 recent
        assert len(kept) == 6

    def test_tool_calls_survive_clear(self):
        compactor = ContextCompactor()
        messages = self._build_messages(n_tools=10)
        out = compactor.clear_tool_results(messages, keep_recent=6)

        assistant_calls = [m for m in out if m.get("tool_calls")]
        assert len(assistant_calls) == 10  # all tool_calls intact

    def test_noop_when_under_keep_recent(self):
        compactor = ContextCompactor()
        messages = self._build_messages(n_tools=3)
        out = compactor.clear_tool_results(messages, keep_recent=6)
        assert out == messages


# =============================================================================
# LLM in-loop management
# =============================================================================

def _make_llm():
    """Construct an LLM-like object without invoking heavy __init__."""
    from praisonaiagents.llm.llm import LLM
    llm = LLM.__new__(LLM)
    llm.model = "gpt-4o"
    llm._in_loop_compaction = True
    llm._clear_threshold_pct = 0.5
    llm._compact_threshold_pct = 0.8
    llm._loop_compactor = None
    return llm


class TestManageContextInLoop:
    def test_noop_under_threshold(self):
        llm = _make_llm()
        messages = [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "hi"},
        ]
        out = llm._manage_context_in_loop(messages)
        assert out == messages

    def test_disabled_is_passthrough(self):
        llm = _make_llm()
        llm._in_loop_compaction = False
        messages = [{"role": "user", "content": "x" * 1000}]
        out = llm._manage_context_in_loop(messages)
        assert out is messages

    def test_resolve_context_window_uses_budgeter(self):
        llm = _make_llm()
        assert llm._resolve_context_window() == 128000  # gpt-4o

    def test_clear_fires_above_threshold(self, monkeypatch):
        """Force a small window so the clear pass triggers on modest input."""
        llm = _make_llm()
        monkeypatch.setattr(llm, "_resolve_context_window", lambda: 2000)

        messages = [{"role": "system", "content": "s"}]
        for i in range(12):
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": f"c{i}", "function": {"name": "f", "arguments": "{}"}}],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": f"c{i}",
                "content": "big output " * 40,
            })

        out = llm._manage_context_in_loop(messages)
        placeholder = "[tool result cleared to save context; re-fetch if needed]"
        cleared = [m for m in out if m.get("role") == "tool" and m.get("content") == placeholder]
        assert len(cleared) > 0
        # tool_calls preserved
        assert len([m for m in out if m.get("tool_calls")]) == 12

    def test_clear_pass_has_hysteresis_to_keep_cached_prefix_stable(self, monkeypatch):
        """Past the clear threshold, the prefix must not be rewritten every turn.

        Without a reserve band, each iteration clears one more old tool result,
        moving the request prefix and busting the provider prompt cache.
        """
        import json

        llm = _make_llm()
        monkeypatch.setattr(llm, "_resolve_context_window", lambda: 4000)

        messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "task"}]
        rewrites = 0
        iterations = 120
        for i in range(iterations):
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": f"c{i}", "function": {"name": "f", "arguments": "{}"}}],
            })
            messages.append({"role": "tool", "tool_call_id": f"c{i}", "content": "x " * 150})
            before = json.dumps(messages[:-2])[:-1]
            messages = llm._manage_context_in_loop(messages)
            if not json.dumps(messages).startswith(before):
                rewrites += 1

        # Management still bounds the context...
        compactor = llm._loop_compactor
        assert compactor.count_total_tokens(messages) < 4000
        # ...but rewrites the prefix in batches, not on (nearly) every turn.
        assert rewrites < iterations // 3

    def test_clear_hysteresis_is_per_conversation(self, monkeypatch):
        """Interleaved tool loops sharing one LLM must not reset each other's band."""
        llm = _make_llm()
        monkeypatch.setattr(llm, "_resolve_context_window", lambda: 4000)

        def conv(task, n, size):
            msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": task}]
            for i in range(n):
                add_turn(msgs, f"{task}-{i}", size)
            return msgs

        def add_turn(msgs, cid, size):
            msgs.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{"id": cid, "function": {"name": "f", "arguments": "{}"}}],
            })
            msgs.append({"role": "tool", "tool_call_id": cid, "content": "x " * size})

        # A: smaller history; a clear pass leaves it near the clear threshold.
        a = llm._manage_context_in_loop(conv("A", 8, 700))
        # B: a larger history on the same LLM, outside A's reserve band.
        llm._manage_context_in_loop(conv("B", 7, 860))

        # A grows by one turn, well inside its own reserve band: no rewrite.
        add_turn(a, "A-x", 10)
        snapshot = [dict(m) for m in a]
        out = llm._manage_context_in_loop(a)
        assert out == snapshot
