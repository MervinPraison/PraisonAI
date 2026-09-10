"""A durable run can move between processes that share no disk.

Durable execution replays from a journal, but the journal is a local SQLite
file -- so a run could only resume where it started. Pausing on a web worker,
putting the state in a queue and resuming it elsewhere was not possible.
"""
import json
import pytest

from praisonaiagents.runtime.journal import JournalEvent, RunJournal
from praisonaiagents.runtime.portable import (
    PORTABLE_RUN_VERSION,
    PortableRunError,
    export_run,
    export_run_json,
    import_run,
    import_run_json,
)


@pytest.fixture
def source(tmp_path):
    j = RunJournal(str(tmp_path / "a.db"))
    j.open_run("r1", agent="researcher", task="find X")
    j.append(JournalEvent(run_id="r1", seq=0, kind="tool_call", payload={"name": "search"}))
    j.append(JournalEvent(run_id="r1", seq=1, kind="tool_result", payload={"out": "found"}))
    return j


@pytest.fixture
def elsewhere(tmp_path):
    return RunJournal(str(tmp_path / "b.db"))


class TestRoundTrip:
    def test_a_run_moves_to_a_journal_that_shares_no_state(self, source, elsewhere):
        run_id = import_run(elsewhere, export_run(source, "r1"))
        meta = elsewhere.run_meta(run_id)
        assert meta.agent == "researcher"
        assert meta.task == "find X"
        assert [(e.seq, e.kind) for e in elsewhere.events(run_id)] == [
            (0, "tool_call"), (1, "tool_result")
        ]

    def test_the_replay_index_is_rebuilt_so_the_run_can_resume(self, source, elsewhere):
        """The point of the export: durable replay must work on the far side."""
        run_id = import_run(elsewhere, export_run(source, "r1"))
        assert len(elsewhere.replay_index(run_id)) > 0

    def test_payloads_survive_the_trip(self, source, elsewhere):
        run_id = import_run(elsewhere, export_run(source, "r1"))
        payloads = [e.payload for e in elsewhere.events(run_id)]
        assert {"name": "search"} in payloads
        assert {"out": "found"} in payloads

    def test_json_form_is_a_string_that_round_trips(self, source, elsewhere):
        text = export_run_json(source, "r1")
        assert isinstance(text, str)
        json.loads(text)  # must be valid JSON for a queue or a form field
        assert import_run_json(elsewhere, text) == "r1"


class TestRefusals:
    def test_exporting_a_run_that_does_not_exist_is_refused(self, source):
        """An empty blob would import as an empty run and replay nothing."""
        with pytest.raises(PortableRunError, match="No run"):
            export_run(source, "nope")

    def test_importing_over_an_existing_run_is_refused(self, source, elsewhere):
        blob = export_run(source, "r1")
        import_run(elsewhere, blob)
        with pytest.raises(PortableRunError, match="already exists"):
            import_run(elsewhere, blob)

    def test_control_a_new_id_lets_the_same_blob_import_twice(self, source, elsewhere):
        blob = export_run(source, "r1")
        import_run(elsewhere, blob)
        assert import_run(elsewhere, blob, run_id="r1-copy") == "r1-copy"

    def test_control_overwrite_is_allowed_when_asked_for(self, source, elsewhere):
        blob = export_run(source, "r1")
        import_run(elsewhere, blob)
        assert import_run(elsewhere, blob, overwrite=True) == "r1"

    def test_a_blob_from_another_version_is_refused(self, source, elsewhere):
        blob = export_run(source, "r1")
        blob["version"] = PORTABLE_RUN_VERSION + 1
        with pytest.raises(PortableRunError, match="version"):
            import_run(elsewhere, blob)

    def test_invalid_json_is_reported_as_such(self, elsewhere):
        with pytest.raises(PortableRunError, match="not valid JSON"):
            import_run_json(elsewhere, "{not json")

    def test_a_blob_with_no_run_id_is_refused(self, elsewhere):
        with pytest.raises(PortableRunError, match="no run_id"):
            import_run(elsewhere, {"version": PORTABLE_RUN_VERSION, "run": {}, "events": []})


class TestLifecycleSurvives:
    """A terminal run must not resurrect as ``running`` on the far side."""

    def test_a_terminal_run_keeps_its_outcome(self, tmp_path, elsewhere):
        src = RunJournal(str(tmp_path / "src.db"))
        src.open_run("done1", agent="a", task="t")
        src.append(JournalEvent(run_id="done1", seq=0, kind="tool_call", payload={}))
        src.close_run("done1", "succeeded")

        run_id = import_run(elsewhere, export_run(src, "done1"))
        meta = elsewhere.run_meta(run_id)
        assert meta.status == "succeeded"
        assert meta.outcome == "succeeded"

    def test_a_running_run_stays_running(self, source, elsewhere):
        run_id = import_run(elsewhere, export_run(source, "r1"))
        assert elsewhere.run_meta(run_id).status == "running"


class TestOverwriteReplacesRatherThanMerges:
    def test_overwrite_drops_the_destinations_stale_events(self, source, elsewhere):
        # A different run already lives at r1 in the destination with events the
        # imported blob does not have.
        elsewhere.open_run("r1", agent="old", task="old")
        elsewhere.append(JournalEvent(run_id="r1", seq=5, kind="iteration", payload={"index": 5}))

        import_run(elsewhere, export_run(source, "r1"), overwrite=True)

        assert [(e.seq, e.kind) for e in elsewhere.events("r1")] == [
            (0, "tool_call"), (1, "tool_result")
        ]
        assert (5, "iteration") not in elsewhere.replay_index("r1")


class TestPartialImportsAreRefusedBeforeAnyWrite:
    def test_a_malformed_event_leaves_no_run_behind(self, elsewhere):
        blob = {
            "version": PORTABLE_RUN_VERSION,
            "run": {"run_id": "bad", "agent": "a", "task": "t"},
            "events": [{"seq": 0, "kind": "tool_call", "payload": {}}, {"seq": 1}],
        }
        with pytest.raises(PortableRunError):
            import_run(elsewhere, blob)
        assert elsewhere.run_meta("bad") is None

    def test_an_unknown_kind_leaves_no_run_behind(self, elsewhere):
        blob = {
            "version": PORTABLE_RUN_VERSION,
            "run": {"run_id": "bad2", "agent": "a", "task": "t"},
            "events": [{"seq": 0, "kind": "not_a_kind", "payload": {}}],
        }
        with pytest.raises(PortableRunError, match="unknown kind"):
            import_run(elsewhere, blob)
        assert elsewhere.run_meta("bad2") is None
