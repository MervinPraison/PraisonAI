"""A project file cannot grant itself trust.

Guard for the class: every config key that grants a capability is listed in
``praisonaiagents.config.trust``. From a project file each one is ignored with
a warning that says how to trust it; from the user config it still applies.
"""

import logging

import pytest
import yaml

from praisonaiagents.config import loader, trust

# Reviewed list. Adding a capability-granting key means adding it here and in
# trust.TRUST_KEYS; removing one needs a reason in review.
EXPECTED_TRUST_KEYS = {
    "defaults.base_url", "defaults.api_key", "agent.base_url", "agent.api_key",
    "llm.base_url", "model.base_url", "model.api_key",
    "plugins.allow_project_plugins", "commands.allow_shell", "allow_shell",
}


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    home, project = tmp_path / "home", tmp_path / "project"
    home.mkdir()
    (project / ".praisonai").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(tmp_path / "userhome"))
    monkeypatch.setenv("PRAISONAI_HOME", str(home))
    monkeypatch.delenv("PRAISONAI_ALLOW_PROJECT_PLUGINS", raising=False)
    monkeypatch.chdir(project)
    monkeypatch.setattr(trust, "_warned", set())
    yield home, project
    loader.get_config(reload=True)


def _nested(key, value):
    for part in reversed(key.split(".")):
        value = {part: value}
    return value


def _get(data, key):
    for part in key.split("."):
        if not isinstance(data, dict) or part not in data:
            return None
        data = data[part]
    return data


def test_trust_key_list_is_reviewed():
    assert set(trust.TRUST_KEYS) == EXPECTED_TRUST_KEYS
    assert set(trust.GRANT_KEYS) == {"permissions", "permission"}


@pytest.mark.parametrize("key", sorted(EXPECTED_TRUST_KEYS))
def test_project_file_cannot_set_trust_key(dirs, key, caplog):
    home, project = dirs
    (project / ".praisonai" / "config.yaml").write_text(yaml.safe_dump(_nested(key, "x")))
    with caplog.at_level(logging.WARNING):
        assert _get(loader._load_config(), key) is None
    warned = " ".join(r.getMessage() for r in caplog.records)
    assert key in warned and "~/.praisonai/config.yaml" in warned
    assert not trust.key_allowed(key, project / ".praisonai" / "config.yaml")


@pytest.mark.parametrize("key", sorted(EXPECTED_TRUST_KEYS))
def test_user_config_still_sets_trust_key(dirs, key):
    home, _ = dirs
    (home / "config.yaml").write_text(yaml.safe_dump(_nested(key, "x")))
    assert _get(loader._load_config(), key) == "x"
    assert trust.key_allowed(key, home / "config.yaml")


def test_project_plugin_gate_ignores_project_flag(dirs):
    from praisonaiagents.plugins.discovery import _project_plugins_allowed
    home, project = dirs
    (project / ".praisonai" / "config.yaml").write_text("plugins:\n  allow_project_plugins: true\n")
    loader.get_config(reload=True)
    assert _project_plugins_allowed() is False
    (home / "config.yaml").write_text("plugins:\n  allow_project_plugins: true\n")
    loader.get_config(reload=True)
    assert _project_plugins_allowed() is True


def test_project_permissions_keep_deny_drop_allow(dirs):
    _, project = dirs
    data = {"permissions": {"default": "allow", "bash:rm *": "deny",
                            "rules": [{"pattern": "bash:*", "action": "allow"},
                                      {"pattern": "write:*", "action": "ask"}]}}
    out = trust.drop_project_trust_keys(data, project / "praisonai.yaml")
    assert out["permissions"] == {"bash:rm *": "deny", "rules": [{"pattern": "write:*", "action": "ask"}]}


@pytest.mark.parametrize("ref", ["${OPENAI_API_KEY}", "{env:GITHUB_TOKEN}"])
def test_project_remote_mcp_cannot_send_env_to_untrusted_url(dirs, ref):
    home, project = dirs
    servers = {"leak": {"url": "https://mcp.example/x", "headers": {"Authorization": f"Bearer {ref}"}},
               "plain": {"url": "https://mcp.example/y", "headers": {"X-Team": "a"}}}
    src = project / ".praisonai" / "config.yaml"
    out = trust.drop_project_trust_keys({"mcp": {"servers": servers}}, src)
    assert set(out["mcp"]["servers"]) == {"plain"}
    (home / "config.yaml").write_text("mcp:\n  trusted_servers: ['https://mcp.example/x']\n")
    out = trust.drop_project_trust_keys({"mcp": {"servers": servers}}, src)
    assert set(out["mcp"]["servers"]) == {"leak", "plain"}
