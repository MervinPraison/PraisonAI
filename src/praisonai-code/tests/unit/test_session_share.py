"""Tests for `session share` / `session unshare` (Issue #3590).

`session share` publishes a *redacted*, read-only transcript as a single
self-contained HTML file and returns a ``file://`` link; `session unshare`
revokes it. These tests assert the round-trip against the real canonical
project store, that secrets are redacted before publish, that transcript
content can never break out of the HTML, and that a missing session is a
clean not-found.
"""

import pytest

from praisonai_code.cli.commands.session import (
    _render_share_html,
    _share_path,
    session_share,
    session_unshare,
)


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Isolated project dir + sessions/data home under the test sandbox."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PRAISONAI_HOME", str(tmp_path / ".praison_home"))
    import praisonaiagents.paths as _paths

    sessions_dir = tmp_path / "sessions"
    data_dir = tmp_path / "data"

    def _fake_get_sessions_dir():
        sessions_dir.mkdir(parents=True, exist_ok=True)
        return sessions_dir

    def _fake_get_data_dir():
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    monkeypatch.setattr(_paths, "get_sessions_dir", _fake_get_sessions_dir)
    monkeypatch.setattr(_paths, "get_data_dir", _fake_get_data_dir)
    monkeypatch.setattr(
        "praisonaiagents.session.store.get_sessions_dir", _fake_get_sessions_dir
    )
    return tmp_path


def _create_project_session(session_id: str) -> None:
    from praisonai_code.cli.state.project_sessions import get_project_session_store

    store = get_project_session_store()
    store.add_message(session_id, "user", "my token is sk-ABCDEF1234567890ABCDEF")
    store.add_message(session_id, "assistant", "noted")
    store.update_session_metadata(session_id, agent_name="Tester", model="gpt-4o")


def test_share_writes_redacted_html_and_returns_link(project):
    _create_project_session("sess-share")

    session_share("sess-share", redact_level="standard")

    path = _share_path("sess-share")
    assert path.exists()
    html = path.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in html
    # The raw secret must not appear; the redactor placeholder should.
    assert "sk-ABCDEF1234567890ABCDEF" not in html
    assert "[redacted:" in html


def test_share_escapes_transcript_markup():
    html = _render_share_html("sid", "<script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_share_path_is_stable_per_session():
    assert _share_path("abc") == _share_path("abc")
    assert _share_path("abc") != _share_path("def")


def test_unshare_revokes_published_transcript(project):
    _create_project_session("sess-unshare")
    session_share("sess-unshare", redact_level="standard")
    path = _share_path("sess-unshare")
    assert path.exists()

    session_unshare("sess-unshare")
    assert not path.exists()


def test_unshare_missing_is_clean_noop(project):
    session_unshare("never-shared")
    assert not _share_path("never-shared").exists()


def test_share_missing_session_exits(project):
    import typer

    with pytest.raises(typer.Exit) as exc:
        session_share("does-not-exist", redact_level="standard")
    assert exc.value.exit_code == 1


def test_share_rejects_invalid_redact_level(project):
    import typer

    _create_project_session("sess-lvl")
    with pytest.raises(typer.Exit) as exc:
        session_share("sess-lvl", redact_level="bogus")
    assert exc.value.exit_code == 1
