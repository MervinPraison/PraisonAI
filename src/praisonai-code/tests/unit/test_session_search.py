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


def test_cli_session_search_no_matches(project, capsys, monkeypatch):
    _create_session("alpha", [("user", "hello world")])

    from praisonai_code.cli.output.console import get_output_controller

    controller = get_output_controller()
    monkeypatch.setattr(type(controller), "is_json_mode", property(lambda self: True))

    session_search("nonexistentterm", limit=5, window=5)

    payload = json.loads(capsys.readouterr().out)
    assert payload["results"] == []
