"""Tests for issue #2952 — centrally-managed / remote config + policy layer.

Covers the optional managed layer added to ``ConfigResolver``:

- Managed non-policy defaults sit BELOW local config (teams suggest, not clobber).
- Managed policy keys (permissions, model_allowlist) are enforced ABOVE local
  config so a local override of an enforced key is ignored.
- ``resolve_with_provenance`` labels ``managed:`` / ``managed-policy:`` origins.
- Fully opt-in: with no managed source configured, resolution is unchanged.
- Remote fetch is fail-soft (uses on-disk cache; never blocks a run).
"""

import json

from praisonai_code.cli.configuration.resolver import ConfigResolver


def _write_managed_dir(base, body: str):
    d = base / "managed"
    d.mkdir()
    (d / "config.yaml").write_text(body)
    return d


def test_no_managed_source_is_backward_compatible(tmp_path, monkeypatch):
    monkeypatch.delenv("PRAISONAI_MANAGED_CONFIG_URL", raising=False)
    monkeypatch.delenv("PRAISONAI_MANAGED_CONFIG_DIR", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")

    resolver = ConfigResolver(cwd=tmp_path)
    config = resolver.resolve()

    assert config.sources == ["defaults"]
    assert config.permissions == {}
    assert config.model_allowlist == []


def test_managed_dir_default_below_project(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    managed_dir = _write_managed_dir(tmp_path, "agent:\n  model: org-default-model\n")
    monkeypatch.setenv("PRAISONAI_MANAGED_CONFIG_DIR", str(managed_dir))
    monkeypatch.delenv("PRAISONAI_MODEL", raising=False)

    # No local project config: the managed default applies on a fresh machine.
    resolver = ConfigResolver(cwd=tmp_path)
    config = resolver.resolve()
    assert config.agent.model == "org-default-model"

    # A deliberate local project choice overrides the managed *default*.
    proj = tmp_path / ".praisonai"
    proj.mkdir()
    (proj / "config.yaml").write_text("agent:\n  model: my-local-model\n")
    resolver2 = ConfigResolver(cwd=tmp_path)
    config2 = resolver2.resolve()
    assert config2.agent.model == "my-local-model"


def test_managed_policy_enforced_above_local(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    managed_dir = _write_managed_dir(
        tmp_path,
        "permissions:\n"
        "  bash:\n"
        "    auto: false\n"
        "model_allowlist:\n"
        "  - gpt-4o\n",
    )
    monkeypatch.setenv("PRAISONAI_MANAGED_CONFIG_DIR", str(managed_dir))

    # Local project tries to override the enforced policy keys.
    proj = tmp_path / ".praisonai"
    proj.mkdir()
    (proj / "config.yaml").write_text(
        "permissions:\n"
        "  bash:\n"
        "    auto: true\n"
        "model_allowlist:\n"
        "  - evil-model\n"
    )

    resolver = ConfigResolver(cwd=tmp_path)
    config = resolver.resolve()

    # Enforced policy wins: local override is ignored, not merged/concatenated.
    assert config.permissions["bash"]["auto"] is False
    assert config.model_allowlist == ["gpt-4o"]


def test_enforced_policy_replaces_local_nested_permissions(tmp_path, monkeypatch):
    """A managed policy that narrows permissions must not inherit local sub-keys.

    Regression guard for the deep-merge leak: a local ``permissions.default:
    allow`` / local ``rules`` must NOT survive when the managed policy sets a
    different, narrower ``permissions`` block. Enforcement replaces the whole
    ``permissions`` key wholesale.
    """
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    managed_dir = _write_managed_dir(
        tmp_path,
        "permissions:\n"
        "  bash:\n"
        "    auto: false\n",
    )
    monkeypatch.setenv("PRAISONAI_MANAGED_CONFIG_DIR", str(managed_dir))

    proj = tmp_path / ".praisonai"
    proj.mkdir()
    (proj / "config.yaml").write_text(
        "permissions:\n"
        "  default: allow\n"
        "  rules:\n"
        "    - allow-everything\n"
    )

    resolver = ConfigResolver(cwd=tmp_path)
    config = resolver.resolve()

    # Only the managed permissions block remains — no local default/rules leak.
    assert config.permissions == {"bash": {"auto": False}}
    assert "default" not in config.permissions
    assert "rules" not in config.permissions


def test_unsafe_managed_url_is_not_fetched(tmp_path, monkeypatch):
    """SSRF guard: non-http(s) and internal-host URLs must not be fetched.

    A ``file://`` URL (and, by extension, loopback/metadata hosts) is rejected
    before any network/file access, so a configured managed URL cannot coerce
    the CLI into reading internal endpoints. With no cache the layer is skipped.
    """
    home = tmp_path / "home"
    monkeypatch.setattr("pathlib.Path.home", lambda: home)

    secret = tmp_path / "secret.yaml"
    secret.write_text("agent:\n  model: exfiltrated\n")
    monkeypatch.setenv("PRAISONAI_MANAGED_CONFIG_URL", f"file://{secret}")

    resolver = ConfigResolver(cwd=tmp_path)
    config = resolver.resolve()

    # The file:// URL was refused: the managed layer is a no-op.
    assert config.agent.model != "exfiltrated"
    assert config.sources == ["defaults"]


def test_provenance_labels_managed_origins(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    managed_dir = _write_managed_dir(
        tmp_path,
        "agent:\n  provider: org-provider\n"
        "model_allowlist:\n  - gpt-4o\n",
    )
    monkeypatch.setenv("PRAISONAI_MANAGED_CONFIG_DIR", str(managed_dir))

    resolver = ConfigResolver(cwd=tmp_path)
    prov = resolver.resolve_with_provenance()

    assert prov["agent.provider"]["layer"].startswith("managed:")
    allow = prov["model_allowlist"]
    assert allow["layer"].startswith("managed-policy:")
    assert allow["enforced"] is True


def test_enforce_false_makes_policy_advisory(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    managed_dir = _write_managed_dir(
        tmp_path,
        "enforce: false\n"
        "model_allowlist:\n  - gpt-4o\n",
    )
    monkeypatch.setenv("PRAISONAI_MANAGED_CONFIG_DIR", str(managed_dir))

    proj = tmp_path / ".praisonai"
    proj.mkdir()
    (proj / "config.yaml").write_text("model_allowlist:\n  - local-model\n")

    resolver = ConfigResolver(cwd=tmp_path)
    config = resolver.resolve()
    # Advisory: managed is a default below local, so local + managed concatenate
    # with the local value present (not enforced-replaced).
    assert "local-model" in config.model_allowlist


def test_remote_fetch_uses_cache_when_offline(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr("pathlib.Path.home", lambda: home)
    url = "https://example.invalid/managed.yaml"
    monkeypatch.setenv("PRAISONAI_MANAGED_CONFIG_URL", url)

    resolver = ConfigResolver(cwd=tmp_path)
    # Seed the on-disk last-good cache to simulate a prior successful fetch.
    cache_path = resolver._managed_cache_path(url)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps({"agent": {"model": "cached-model"}}))

    # urlopen will fail (invalid host) → fail-soft to the cached copy.
    config = resolver.resolve()
    assert config.agent.model == "cached-model"


def test_offline_no_cache_skips_layer(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path / "home")
    monkeypatch.setenv("PRAISONAI_MANAGED_CONFIG_URL", "https://example.invalid/x.yaml")

    resolver = ConfigResolver(cwd=tmp_path)
    config = resolver.resolve()
    # No cache and offline: managed layer is skipped, behaviour unchanged.
    assert config.sources == ["defaults"]
