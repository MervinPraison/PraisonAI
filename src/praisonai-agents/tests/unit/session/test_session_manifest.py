"""Tests for the session manifest (Issue #6248)."""

from praisonaiagents.session import FileSessionManifest, SessionManifestProtocol


def test_satisfies_protocol(tmp_path):
    assert isinstance(FileSessionManifest(str(tmp_path)), SessionManifestProtocol)


def test_missing_session_has_no_entry(tmp_path):
    m = FileSessionManifest(str(tmp_path))
    assert m.get("missing") is None and m.interrupted("missing") is None


def test_legacy_entry_with_unknown_keys_still_loads(tmp_path):
    (tmp_path / "s1.json").write_text(
        '{"session_id": "s1", "refs": {"plan": "p"}, "run_in_flight": true}',
        encoding="utf-8",
    )
    assert FileSessionManifest(str(tmp_path)).interrupted("s1") is not None


def test_completed_run_is_not_interrupted(tmp_path):
    m = FileSessionManifest(str(tmp_path))
    m.begin_run("s1", "r1", run_input="task")
    assert m.interrupted("s1") is not None
    m.end_run("s1", "completed")
    assert m.interrupted("s1") is None
    assert m.get("s1").run_status == "completed"


def test_interrupted_run_survives_new_process(tmp_path):
    FileSessionManifest(str(tmp_path)).begin_run("s1", "r1", run_input="task")
    # A new process (new instance) sees the surviving write-ahead marker.
    stale = FileSessionManifest(str(tmp_path)).interrupted("s1")
    assert stale is not None and stale.run_id == "r1" and stale.run_digest


def test_attempt_budget_is_bounded(tmp_path):
    m = FileSessionManifest(str(tmp_path))
    attempts = [m.begin_run("s1", f"r{i}", run_input="task", max_attempts=2).attempt
                for i in range(4)]
    # Retries of the same interrupted task count up, then the budget resets.
    assert attempts == [1, 2, 1, 2]


def test_new_task_after_interruption_is_a_fresh_attempt(tmp_path):
    m = FileSessionManifest(str(tmp_path))
    m.begin_run("s1", "r1", run_input="task a")
    assert m.begin_run("s1", "r2", run_input="task b").attempt == 1


def test_unsafe_session_id_stays_in_directory(tmp_path):
    m = FileSessionManifest(str(tmp_path))
    m.begin_run("../../etc/x", "r1")
    assert all(p.parent == tmp_path for p in tmp_path.iterdir())
    assert m.get("../../etc/x").run_id == "r1"


def test_run_input_is_never_written_in_plaintext(tmp_path):
    secret = "deploy with token sk-SECRET-12345"
    m = FileSessionManifest(str(tmp_path))
    m.begin_run("s1", "r1", run_input=secret)
    for f in tmp_path.iterdir():
        assert "sk-SECRET-12345" not in f.read_text(encoding="utf-8")
    # The digest still recognises a retry of the same task.
    assert m.begin_run("s1", "r2", run_input=secret).attempt == 2


def test_absolute_and_backslash_ids_stay_in_directory(tmp_path):
    m = FileSessionManifest(str(tmp_path))
    for sid in ("/etc/passwd", "..\\..\\x", "..", "C:\\x"):
        m.begin_run(sid, sid)
        assert m.get(sid).run_id == sid
    assert all(p.parent == tmp_path for p in tmp_path.iterdir())


def test_ids_differing_only_in_punctuation_stay_separate(tmp_path):
    m = FileSessionManifest(str(tmp_path))
    m.begin_run("a:b", "colon")
    m.begin_run("a_b", "underscore")
    assert m.get("a:b").run_id == "colon"
    assert m.get("a_b").run_id == "underscore"


def test_end_run_only_releases_its_own_marker(tmp_path):
    m = FileSessionManifest(str(tmp_path))
    m.begin_run("s1", "r1", run_input="first")
    m.begin_run("s1", "r2", run_input="second")  # second terminal takes over
    assert m.end_run("s1", "completed", run_id="r1") is None
    stale = m.interrupted("s1")
    assert stale is not None and stale.run_id == "r2"
    m.end_run("s1", "completed", run_id="r2")
    assert m.interrupted("s1") is None
