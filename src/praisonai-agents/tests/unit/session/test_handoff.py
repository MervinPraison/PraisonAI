"""Tests for the cross-context continuation-prompt assembler (session handoff).

The handoff builder converts already-persisted durable state (recap + goal state
+ workflow checkpoint) into a self-contained continuation prompt. It must be
deterministic (no LLM call), omit empty sections, and stay within its char cap.
"""

from praisonaiagents.session import build_handoff_prompt


def _goal_state():
    return {
        "goal": "Ship the logging refactor",
        "criteria": {
            "outcome": "All modules use structured logging",
            "verification": "pytest passes and logs are JSON",
            "constraints": ["do not change public API"],
        },
        "last_reason": "tests still failing",
    }


def _checkpoint():
    return {"completed_steps": 3, "total_steps": 5, "last_step": "wire logger"}


def test_goal_and_progress_sections_render():
    out = build_handoff_prompt(
        recap="Recap — where we were: ...",
        goal_state=_goal_state(),
        workflow_checkpoint=_checkpoint(),
    )
    assert "GOAL: Ship the logging refactor" in out
    assert "DEFINITION OF DONE:" in out
    assert "CONSTRAINTS (never violate): do not change public API" in out
    assert "PROGRESS: 3 of 5 workflow steps done" in out
    assert "last completed: wire logger" in out
    assert out.startswith("You are resuming an interrupted run")
    assert "NEXT:" in out


def test_recap_only_when_no_goal_or_checkpoint():
    out = build_handoff_prompt(recap="Recap block here")
    assert "GOAL:" not in out
    assert "PROGRESS:" not in out
    assert "Recap block here" in out
    assert "NEXT:" in out


def test_empty_state_still_valid_prompt():
    out = build_handoff_prompt()
    assert out.startswith("You are resuming an interrupted run")
    assert "NEXT:" in out
    assert "GOAL:" not in out


def test_explicit_recent_actions_and_key_files():
    out = build_handoff_prompt(
        goal_state=_goal_state(),
        recent_actions=["read_file main.py (t0)", "run tests (t1)"],
        key_files=["src/main.py", "src/main.py", "tests/test_main.py"],
    )
    assert "RECENT ACTIONS:" in out
    assert "- read_file main.py (t0)" in out
    # Key files de-duplicated, order preserved.
    assert "KEY FILES: src/main.py, tests/test_main.py" in out


def test_char_cap_enforced():
    big = "x" * 10000
    out = build_handoff_prompt(recap=big, max_chars=500)
    assert len(out) <= 500


def test_determinism_no_llm_and_stable():
    # Two identical calls produce identical output (pure assembly, no LLM).
    args = dict(recap="same", goal_state=_goal_state())
    assert build_handoff_prompt(**args) == build_handoff_prompt(**args)
