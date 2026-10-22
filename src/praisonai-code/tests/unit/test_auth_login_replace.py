"""Re-running `auth login` must not silently replace a stored key (#5949)."""

from typer.testing import CliRunner

from praisonai_code.cli.commands import auth
from praisonai_code.cli.configuration.credentials import CredentialStore

OLD = "sk-old-aaaaaaaaaaaaaaaaaaaaaaaa1111"
NEW = "sk-new-bbbbbbbbbbbbbbbbbbbbbbbb2222"


def _setup(tmp_path, monkeypatch):
    path = tmp_path / "creds.json"
    CredentialStore(path).store_credential("openai", OLD)
    monkeypatch.setattr(auth, "CredentialStore", lambda: CredentialStore(path))
    return path


def test_prompted_login_declined_keeps_existing_key(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    result = CliRunner().invoke(
        auth.app, ["login", "openai", "--skip-validation"], input=f"{NEW}\nn\n"
    )
    assert result.exit_code == 1
    assert CredentialStore(path).get_credential("openai").api_key == OLD


def test_scripted_login_replaces_and_reports(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch)
    result = CliRunner().invoke(
        auth.app, ["login", "openai", "--key", NEW, "--skip-validation"]
    )
    assert result.exit_code == 0, result.output
    assert "Replacing existing openai key" in result.output
    assert CredentialStore(path).get_credential("openai").api_key == NEW
