"""Tests for the read-only session recap (build_recap).

Recap reuses the existing summariser purely to *inform* the user; it must never
mutate the transcript or trigger a compaction event.
"""

import copy

from praisonaiagents.compaction import build_recap


def _transcript(n=8):
    msgs = [{"role": "system", "content": "You are a helpful agent."}]
    for i in range(n):
        msgs.append({"role": "user", "content": f"user message {i}"})
        msgs.append({"role": "assistant", "content": f"assistant reply {i}"})
    return msgs


def test_recap_empty_history():
    assert "Nothing to recap" in build_recap([])


def test_recap_nondestructive():
    """The transcript must be unchanged and no compaction event emitted."""
    history = _transcript()
    before = copy.deepcopy(history)
    out = build_recap(history)
    assert isinstance(out, str) and out
    # Transcript is untouched (same length and content, no injected summary).
    assert history == before


def test_recap_includes_recent_tail():
    history = _transcript(2)
    out = build_recap(history)
    assert "Recent:" in out
    assert "assistant reply 1" in out


def test_recap_uses_persisted_summary_when_available():
    """A persisted compaction summary is reused verbatim, not recomputed."""
    history = [
        {"role": "system", "content": "sys"},
        {
            "role": "system",
            "content": "[Previous conversation summary]\nUser wants X; did Y.",
            "_compacted": True,
        },
        {"role": "user", "content": "and now Z"},
        {"role": "assistant", "content": "doing Z"},
    ]
    out = build_recap(history)
    assert "User wants X; did Y." in out


def test_recap_naive_summary_when_no_persisted():
    """Without a persisted summary, the naive summariser distils older turns."""
    history = _transcript(8)
    out = build_recap(history)
    # The naive summariser tags its output; recap surfaces that distilled line.
    assert "📌" in out
