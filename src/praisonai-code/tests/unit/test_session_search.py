"""Tests for `session search` (Issue #4701).

`session search <query>` runs a ranked full-text search across session
transcripts by delegating to ``SqliteSessionStore`` (FTS5/bm25 with snippets
and lineage dedup) — the same engine as the ``session_search`` agent tool —
instead of the substring scan the CLI previously had no command for at all.

The ranking test indexes three sessions, queries a term present in two, and
asserts both come back with a snippet and that the denser-match session ranks
first even though it sorts last by id. A substring scan returns matches in
directory order, so that assertion fails if search reverts to a substring scan.
"""

import json

import pytest

from praisonai_code.cli.commands.session import session_search


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Isolated project dir + sessions home under the test sandbox."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praison_home"))
    import praisonaiagents.paths as _paths

    sessions_dir = tmp_path / "sessions"

    def _fake_get_sessions_dir():
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir

    monkeypatch.setattr(_paths, "get_sessions_dir", _fake_get_sessions_dir)
    monkeypatch.setattr(
        "praisonaiagents.session.store.get_sessions_dir", _fake_get_sessions_dir
    )
    return tmp_path


def _create_session(session_id: str, texts) -> None:
    from praisonai_code.cli.state.project_sessions import get_project_session_store

    store = get_project_session_store()
    for role, content in texts:
        store.add_message(session_id, role, content)


def test_cli_session_search_ranks_with_snippets(project, capsys, monkeypatch):
    # "zeta" mentions the term densely, "alpha" once, "gamma" not at all.
    # "zeta" sorts last, so ranking-first only holds under real bm25 relevance.
    assert "alpha" < "zeta"
    _create_session("alpha", [("user", "one mention of migration here")])
    _create_session(
        "zeta",
        [
            ("user", "we need a billing migration migration migration plan"),
            ("assistant", "the migration is scheduled"),
        ],
    )
    _create_session("gamma", [("user", "totally unrelated content about weather")])

    # Force JSON output so we can assert on structured, ranked results.
    from praisonai_code.cli.output.console import get_output_controller

    controller = get_output_controller()
    monkeypatch.setattr(type(controller), "is_json_mode", property(lambda self: True))

    session_search("migration", limit=5, window=5)

    out = capsys.readouterr().out
    payload = json.loads(out)
    ids = [r["session_id"] for r in payload["results"]]

    assert "alpha" in ids
    assert "zeta" in ids
    assert "gamma" not in ids
    for r in payload["results"]:
        assert r["snippet"]
        assert "migration" in r["snippet"].lower()

    # Denser match ranks first despite sorting last by id (mutation guard).
    assert ids[0] == "zeta"


def test_cli_session_search_dedupes_cross_store_shadows(project, capsys, monkeypatch):
    # A session resumed from the global default store keeps a project-side
    # shadow, so the same id matches in both canonical stores. Those duplicate
    # rows must not each consume a slot of ``limit`` and crowd out distinct
    # sessions (Issue #4701). Stub two stores that both surface ``dup`` plus one
    # distinct id each; with limit=2 the deduped result must contain both
    # distinct ids, which only holds when the same id is collapsed.
    class _Hit:
        def __init__(self, sid, score):
            self.session_id = sid
            self.score = score
            self.when = ""
            self.title = sid
            self.snippet = "migration"

        def as_dict(self):
            return {
                "session_id": self.session_id,
                "title": self.title,
                "score": self.score,
                "snippet": self.snippet,
                "when": self.when,
            }

    class _Store:
        def __init__(self, session_dir, hits):
            self.session_dir = session_dir
            self._hits = hits

    class _Indexed:
        registry = {}

        def __init__(self, session_dir):
            self._hits = _Indexed.registry[session_dir]

        def search(self, query, limit=5, window=5):
            return list(self._hits)

    project_hits = [_Hit("dup", 5.0), _Hit("proj-only", 3.0)]
    global_hits = [_Hit("dup", 4.0), _Hit("glob-only", 2.0)]
    _Indexed.registry = {"proj-dir": project_hits, "glob-dir": global_hits}

    monkeypatch.setattr(
        "praisonaiagents.session.SqliteSessionStore", _Indexed, raising=False
    )
    monkeypatch.setattr(
        "praisonai_code.cli.state.project_sessions.canonical_cli_stores",
        lambda *a, **k: [
            _Store("proj-dir", project_hits),
            _Store("glob-dir", global_hits),
        ],
    )

    from praisonai_code.cli.output.console import get_output_controller

    controller = get_output_controller()
    monkeypatch.setattr(type(controller), "is_json_mode", property(lambda self: True))

    session_search("migration", limit=2, window=5)

    payload = json.loads(capsys.readouterr().out)
    ids = [r["session_id"] for r in payload["results"]]

    # "dup" collapses to a single row (its higher score, 5.0, is kept), leaving
    # room for a distinct id. Without dedup the two "dup" rows fill both slots.
    assert ids.count("dup") == 1
    assert "proj-only" in ids
    assert len(ids) == 2


def test_cli_session_search_no_matches(project, capsys, monkeypatch):
    _create_session("alpha", [("user", "hello world")])

    from praisonai_code.cli.output.console import get_output_controller

    controller = get_output_controller()
    monkeypatch.setattr(type(controller), "is_json_mode", property(lambda self: True))

    session_search("nonexistentterm", limit=5, window=5)

    payload = json.loads(capsys.readouterr().out)
    assert payload["results"] == []
