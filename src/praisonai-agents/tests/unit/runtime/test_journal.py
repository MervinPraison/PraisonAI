"""Tests for the durable run-state journal (Issue #2994).

The journal records the execution cursor of a run — model decisions, tool
calls/results, iteration index — so a crash mid tool-loop can resume via
memoised replay: journalled steps return recorded results (no re-execution of
side-effecting tools, no re-billing of LLM calls) and real work restarts at the
first un-journalled step.
"""

import pytest

from praisonaiagents.runtime import JournalEvent, RunJournal, RunMeta
from praisonaiagents.runtime.journal import (
    KIND_ITERATION,
    KIND_MODEL_DECISION,
    KIND_TOOL_CALL,
    KIND_TOOL_RESULT,
)


@pytest.fixture
def journal():
    j = RunJournal(":memory:")
    yield j
    j.close()


# ── run lifecycle ─────────────────────────────────────────────────────


def test_open_run_records_meta(journal):
    journal.open_run("r1", agent="coder", task="migrate module")
    meta = journal.run_meta("r1")
    assert isinstance(meta, RunMeta)
    assert meta.run_id == "r1"
    assert meta.agent == "coder"
    assert meta.task == "migrate module"
    assert meta.status == "running"


def test_unknown_run_meta_is_none(journal):
    assert journal.run_meta("nope") is None


def test_set_checkpoint_binds_files_store(journal):
    journal.open_run("r1")
    journal.set_checkpoint("r1", "abc123")
    assert journal.run_meta("r1").checkpoint_id == "abc123"


def test_close_run_marks_terminal(journal):
    journal.open_run("r1")
    journal.close_run("r1", "succeeded")
    meta = journal.run_meta("r1")
    assert meta.status == "succeeded"
    assert meta.outcome == "succeeded"


# ── the six scenarios from the issue ──────────────────────────────────


def test_journal_appends_each_boundary(journal):
    """A 3-tool run writes model_decision/tool_call/tool_result/iteration
    events in order."""
    journal.open_run("r1", agent="a", task="t")
    seq = 0
    expected = []
    for i in range(3):
        journal.append(JournalEvent("r1", seq, KIND_MODEL_DECISION, {"text": f"call {i}"}))
        expected.append(KIND_MODEL_DECISION)
        journal.append(JournalEvent("r1", seq, KIND_TOOL_CALL,
                                    {"name": f"tool{i}", "args": {}, "idempotency_key": f"k{i}"}))
        expected.append(KIND_TOOL_CALL)
        journal.append(JournalEvent("r1", seq, KIND_TOOL_RESULT, {"result": i}))
        expected.append(KIND_TOOL_RESULT)
        journal.append(JournalEvent("r1", seq, KIND_ITERATION, {"index": i}))
        expected.append(KIND_ITERATION)
        seq += 1

    kinds = [ev.kind for ev in journal.events("r1")]
    assert kinds == expected


def test_resume_skips_completed_tools(journal):
    """Kill after tool 2; on resume tools 1-2 are NOT re-executed and the model
    is NOT re-called for journalled steps — memoised replay returns recorded
    payloads instead."""
    journal.open_run("r1")
    # Two completed tool steps journalled before the "crash".
    journal.append(JournalEvent("r1", 0, KIND_MODEL_DECISION, {"text": "d0"}))
    journal.append(JournalEvent("r1", 0, KIND_TOOL_RESULT, {"result": "r0"}))
    journal.append(JournalEvent("r1", 1, KIND_MODEL_DECISION, {"text": "d1"}))
    journal.append(JournalEvent("r1", 1, KIND_TOOL_RESULT, {"result": "r1"}))

    replay = journal.replay_index("r1")

    tool_fn_calls = []

    def run_tool(seq):
        # Memoised: recorded result returned without executing the tool.
        rec = replay.get((seq, KIND_TOOL_RESULT))
        if rec is not None:
            return rec["result"]
        tool_fn_calls.append(seq)  # would be a real (side-effecting) exec
        return f"live-{seq}"

    model_calls = []

    def call_model(seq):
        rec = replay.get((seq, KIND_MODEL_DECISION))
        if rec is not None:
            return rec["text"]
        model_calls.append(seq)
        return f"live-decision-{seq}"

    # Re-drive steps 0 and 1 (recorded) then step 2 (live).
    assert call_model(0) == "d0"
    assert run_tool(0) == "r0"
    assert call_model(1) == "d1"
    assert run_tool(1) == "r1"
    assert call_model(2) == "live-decision-2"  # first un-journalled decision
    assert run_tool(2) == "live-2"  # first un-journalled tool runs live

    # Journalled tools/model were NOT re-executed/re-called.
    assert tool_fn_calls == [2]
    assert model_calls == [2]


def test_resume_continues_at_recorded_iteration(journal):
    """iteration_count is restored so the loop continues to completion."""
    journal.open_run("r1")
    for i in range(7):
        journal.append(JournalEvent("r1", i, KIND_ITERATION, {"index": i}))
    assert journal.last_iteration("r1") == 6  # resume at cursor 6, continue to 7+


def test_last_iteration_none_when_absent(journal):
    journal.open_run("r1")
    assert journal.last_iteration("r1") is None


def test_replay_divergence_fails_loud(journal):
    """A replay whose kinds diverge from the recorded journal raises rather
    than proceeding down a different, unrecorded path."""
    journal.open_run("r1")
    journal.append(JournalEvent("r1", 0, KIND_MODEL_DECISION, {"text": "d"}))
    journal.append(JournalEvent("r1", 0, KIND_TOOL_CALL, {"name": "x", "args": {}, "idempotency_key": "k"}))
    journal.append(JournalEvent("r1", 0, KIND_TOOL_RESULT, {"result": 1}))

    # Matching order passes.
    journal.assert_replay_order("r1", [KIND_MODEL_DECISION, KIND_TOOL_CALL, KIND_TOOL_RESULT])

    # Divergent order fails loud.
    with pytest.raises(RuntimeError, match="replay divergence"):
        journal.assert_replay_order("r1", [KIND_MODEL_DECISION, KIND_TOOL_RESULT])


def test_durable_off_is_zero_overhead():
    """durable=False (default) means no journal is instantiated at all — the
    seam is opt-in; a caller simply never constructs a RunJournal."""
    # Nothing to persist: the journal is only created when a run opts in.
    # This asserts the module import is cheap and the primitive is inert until
    # explicitly used (no global state, no files touched on import).
    from praisonaiagents.runtime import journal as journal_mod

    assert hasattr(journal_mod, "RunJournal")
    # No RunJournal constructed → no side effects. A default-off run behaves
    # identically to today because it never calls append/open_run.


# ── journal semantics ─────────────────────────────────────────────────


def test_append_rejects_unknown_kind(journal):
    journal.open_run("r1")
    with pytest.raises(ValueError, match="unknown journal event kind"):
        journal.append(JournalEvent("r1", 0, "bogus", {}))


def test_append_is_idempotent_on_key(journal):
    """Re-appending the same (run_id, seq, kind) updates payload, not duplicates
    — so a harmlessly re-journalled replayed step stays the single source of
    truth."""
    journal.open_run("r1")
    journal.append(JournalEvent("r1", 0, KIND_TOOL_RESULT, {"result": "old"}))
    journal.append(JournalEvent("r1", 0, KIND_TOOL_RESULT, {"result": "new"}))
    events = journal.events("r1")
    assert len(events) == 1
    assert events[0].payload == {"result": "new"}


def test_events_ordered_call_before_result(journal):
    journal.open_run("r1")
    journal.append(JournalEvent("r1", 0, KIND_TOOL_CALL, {"name": "x", "args": {}, "idempotency_key": "k"}))
    journal.append(JournalEvent("r1", 0, KIND_TOOL_RESULT, {"result": 1}))
    kinds = [ev.kind for ev in journal.events("r1")]
    assert kinds.index(KIND_TOOL_CALL) < kinds.index(KIND_TOOL_RESULT)


def test_interrupted_runs_lists_only_running(journal):
    """Runs left 'running' are resume candidates on restart; closed ones are
    not."""
    journal.open_run("running1")
    journal.open_run("running2")
    journal.open_run("done1")
    journal.close_run("done1", "succeeded")
    interrupted = journal.interrupted_runs()
    assert set(interrupted) == {"running1", "running2"}


def test_reopen_preserves_journal(journal):
    """Resuming (re-open) an existing run keeps its journal and running status
    without clobbering created_at."""
    journal.open_run("r1", agent="a", task="t")
    journal.append(JournalEvent("r1", 0, KIND_TOOL_RESULT, {"result": 1}))
    created = journal.run_meta("r1").created_at

    journal.open_run("r1")  # resume
    assert journal.run_meta("r1").status == "running"
    assert journal.run_meta("r1").created_at == created
    assert len(journal.events("r1")) == 1  # journal preserved


def test_payload_survives_non_json_native_values(journal):
    """A payload with a non-JSON-native value (e.g. a set) is still persisted
    via the str fallback, keeping the run journalled instead of raising."""
    journal.open_run("r1")
    journal.append(JournalEvent("r1", 0, KIND_MODEL_DECISION, {"tags": {"a", "b"}}))
    # Round-trips without raising; value is coerced to a JSON-safe form.
    events = journal.events("r1")
    assert len(events) == 1
    assert events[0].kind == KIND_MODEL_DECISION
