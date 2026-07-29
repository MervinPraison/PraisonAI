"""Tests for opt-in transcript redaction on session export (Issue #3426).

``praisonai session export <id> --sanitise`` must replace a seeded secret, an
absolute path, and embedded file contents with stable placeholders, while a
plain ``session export <id>`` stays byte-for-byte unchanged.
"""

import json

import pytest

from praisonai_code.cli.state.redact import REDACT_LEVELS, redact_transcript


def _fixture_payload():
    return {
        "session_id": "sess-redact",
        "agent_name": "Tester",
        "model": "gpt-4o",
        "chat_history": [
            {
                "role": "user",
                "content": "read /home/alice/project/secret_config.yaml please",
            },
            {
                "role": "assistant",
                "content": (
                    "The file at /home/alice/project/secret_config.yaml holds "
                    "api_key=sk-ABCDEF0123456789ABCDEF and a token."
                ),
            },
            {
                "role": "user",
                "content": "and again /home/alice/project/secret_config.yaml",
            },
        ],
        "metadata": {"cwd": "/home/alice/project"},
        "message_count": 3,
    }


def test_secret_is_redacted():
    out = redact_transcript(_fixture_payload())
    dumped = json.dumps(out)
    assert "sk-ABCDEF0123456789ABCDEF" not in dumped
    assert "[redacted:secret:" in dumped


def test_absolute_path_is_redacted():
    out = redact_transcript(_fixture_payload())
    dumped = json.dumps(out)
    assert "/home/alice/project/secret_config.yaml" not in dumped
    assert "[redacted:path:" in dumped


def test_placeholders_are_stable():
    """The same value maps to the same placeholder across the transcript."""
    out = redact_transcript(_fixture_payload())
    first = out["chat_history"][0]["content"]
    third = out["chat_history"][2]["content"]
    # The repeated path yields an identical placeholder in both messages.
    assert "[redacted:path:1]" in first
    assert "[redacted:path:1]" in third


def test_input_payload_is_not_mutated():
    payload = _fixture_payload()
    original = json.dumps(payload)
    redact_transcript(payload)
    assert json.dumps(payload) == original


def test_extra_secrets_are_masked():
    payload = {"chat_history": [{"role": "user", "content": "the value is HUNTER2SECRET"}]}
    out = redact_transcript(payload, extra_secrets=["HUNTER2SECRET"])
    assert "HUNTER2SECRET" not in json.dumps(out)


def test_single_segment_posix_path_is_redacted():
    payload = {"chat_history": [{"role": "user", "content": "logs live in /tmp"}]}
    out = redact_transcript(payload)
    assert "/tmp" not in json.dumps(out)
    assert "[redacted:path:" in json.dumps(out)


def test_cwd_is_redacted_as_path_without_dangling_suffix(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    cwd = str(tmp_path)
    payload = {"chat_history": [{"role": "user", "content": f"open {cwd}/config.yaml"}]}
    dumped = json.dumps(redact_transcript(payload))
    assert cwd not in dumped
    # The cwd must be masked as a path, never leaving a secret-prefixed suffix.
    assert "[redacted:secret:" not in dumped
    assert "[redacted:path:" in dumped


def test_unc_path_is_redacted():
    payload = {"chat_history": [{"role": "user", "content": r"copy \\server\share\secret.txt"}]}
    dumped = json.dumps(redact_transcript(payload))
    assert r"\\\\server\\share\\secret.txt" not in dumped
    assert "server" not in dumped
    assert "[redacted:path:" in dumped


def test_strict_masks_bearer_and_pem_but_standard_does_not():
    bearer = "Authorization: Bearer abcDEF123456ghijkl"
    pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIBOgIBAAJBAKj34GkxFhD\n"
        "-----END RSA PRIVATE KEY-----"
    )
    payload = {"chat_history": [{"role": "user", "content": f"{bearer}\n{pem}"}]}

    standard = json.dumps(redact_transcript(payload, level="standard"))
    assert "abcDEF123456ghijkl" in standard  # not covered by standard

    strict = json.dumps(redact_transcript(payload, level="strict"))
    assert "abcDEF123456ghijkl" not in strict
    assert "MIIBOgIBAAJBAKj34GkxFhD" not in strict
    assert "[redacted:secret:" in strict


def test_invalid_level_raises():
    with pytest.raises(ValueError):
        redact_transcript(_fixture_payload(), level="bogus")


def test_redact_levels_exposed():
    assert REDACT_LEVELS == ("standard", "strict")


def test_export_default_unchanged_and_sanitise_redacts(tmp_path, monkeypatch):
    """End-to-end: plain export unchanged; --sanitise scrubs the transcript."""
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

    from praisonai_code.cli.state.project_sessions import get_project_session_store
    from praisonai_code.cli.state.session_resolver import export_session

    store = get_project_session_store()
    store.add_message(
        "sess-e2e",
        "assistant",
        "leaked sk-ABCDEF0123456789ABCDEF at /home/alice/project/config.yaml",
    )
    store.update_session_metadata("sess-e2e", agent_name="Tester", model="gpt-4o")

    plain = export_session("sess-e2e", format="json")
    assert plain is not None
    assert "sk-ABCDEF0123456789ABCDEF" in plain

    sanitised = export_session("sess-e2e", format="json", redact=True)
    assert sanitised is not None
    assert "sk-ABCDEF0123456789ABCDEF" not in sanitised
    assert "/home/alice/project/config.yaml" not in sanitised
    assert "[redacted:secret:" in sanitised

    # Default export path must not change when the flag is absent.
    assert export_session("sess-e2e", format="json") == plain
