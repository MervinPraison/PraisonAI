"""
Tests for `.praisonai/config.yaml` as a single source of truth.

Verifies that the resolver surfaces `mcp` and `permissions` sections and that
the run command wiring converts them into the structures the run path consumes,
with CLI flags still overriding config.
"""

import os
from pathlib import Path
from types import SimpleNamespace

import yaml


def _write_project_config(root: Path, data: dict) -> Path:
    config_dir = root / ".praisonai"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "config.yaml"
    config_path.write_text(yaml.safe_dump(data))
    return config_path


class TestResolverSurfacesMcpAndPermissions:
    """The resolver must expose `mcp` and `permissions` on the resolved config."""

    def test_resolved_config_has_mcp_and_permissions_defaults(self):
        from praisonai.cli.configuration.resolver import ResolvedConfig

        config = ResolvedConfig()
        assert config.mcp == {}
        assert config.permissions == {}

    def test_resolver_reads_mcp_section(self, tmp_path, monkeypatch):
        from praisonai.cli.configuration.resolver import ConfigResolver

        # Isolate global config so only project config is picked up.
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        (tmp_path / "home").mkdir(parents=True, exist_ok=True)

        _write_project_config(
            tmp_path,
            {
                "agent": {"model": "gpt-4o"},
                "mcp": {
                    "servers": {
                        "playwright": {
                            "command": ["npx", "-y", "@playwright/mcp"],
                        }
                    }
                },
            },
        )

        resolver = ConfigResolver(cwd=tmp_path)
        config = resolver.resolve(force_refresh=True)

        assert config.agent.model == "gpt-4o"
        assert "servers" in config.mcp
        assert "playwright" in config.mcp["servers"]
        assert config.mcp["servers"]["playwright"]["command"] == [
            "npx",
            "-y",
            "@playwright/mcp",
        ]

    def test_resolver_reads_permissions_section(self, tmp_path, monkeypatch):
        from praisonai.cli.configuration.resolver import ConfigResolver

        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        (tmp_path / "home").mkdir(parents=True, exist_ok=True)

        _write_project_config(
            tmp_path,
            {
                "permissions": {
                    "default": "ask",
                    "rules": [
                        {"pattern": "bash:git *", "action": "allow"},
                        {"pattern": "bash:rm *", "action": "deny"},
                    ],
                },
            },
        )

        resolver = ConfigResolver(cwd=tmp_path)
        config = resolver.resolve(force_refresh=True)

        assert config.permissions["default"] == "ask"
        patterns = {r["pattern"]: r["action"] for r in config.permissions["rules"]}
        assert patterns["bash:git *"] == "allow"
        assert patterns["bash:rm *"] == "deny"

    def test_resolved_config_roundtrip_preserves_sections(self):
        from praisonai.cli.configuration.resolver import ResolvedConfig

        data = {
            "mcp": {"servers": {"x": {"command": ["echo"]}}},
            "permissions": {"default": "deny"},
        }
        config = ResolvedConfig.from_dict(data)
        out = config.to_dict()
        assert out["mcp"] == data["mcp"]
        assert out["permissions"] == data["permissions"]


class TestRunWiringConverters:
    """The run command helpers convert resolved config into run-path structures."""

    def test_mcp_server_to_command_list_form(self):
        from praisonai.cli.commands.run import _mcp_server_to_command

        result = _mcp_server_to_command(
            {"command": ["npx", "-y", "@playwright/mcp"]}
        )
        assert result == ("npx -y @playwright/mcp", None)

    def test_mcp_server_to_command_string_form_with_env(self):
        from praisonai.cli.commands.run import _mcp_server_to_command

        result = _mcp_server_to_command(
            {"command": "npx -y server", "env": {"TOKEN": "abc"}}
        )
        assert result == ("npx -y server", "TOKEN=abc")

    def test_mcp_server_to_command_skips_disabled(self):
        from praisonai.cli.commands.run import _mcp_server_to_command

        assert (
            _mcp_server_to_command(
                {"command": ["npx"], "enabled": False}
            )
            is None
        )

    def test_mcp_server_to_command_skips_remote(self):
        from praisonai.cli.commands.run import _mcp_server_to_command

        assert (
            _mcp_server_to_command({"type": "remote", "url": "http://x"})
            is None
        )

    def test_mcp_server_to_command_quotes_tokens(self):
        from praisonai.cli.commands.run import _mcp_server_to_command

        result = _mcp_server_to_command(
            {"command": ["python", "/tmp/my server.py", "--label", "hello world"]}
        )
        command_str, _ = result
        import shlex

        assert shlex.split(command_str) == [
            "python",
            "/tmp/my server.py",
            "--label",
            "hello world",
        ]

    def test_mcp_server_to_command_skips_comma_env(self):
        import warnings

        from praisonai.cli.commands.run import _mcp_server_to_command

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = _mcp_server_to_command(
                {
                    "command": ["npx", "server"],
                    "env": {"OK": "value", "BAD": "a,b"},
                }
            )
        command_str, env_str = result
        assert command_str == "npx server"
        assert env_str == "OK=value"

    def test_permissions_from_config_rule_list(self):
        from praisonai.cli.commands.run import _permissions_from_config

        cfg = SimpleNamespace(
            permissions={
                "default": "ask",
                "rules": [
                    {"pattern": "bash:git *", "action": "allow"},
                    {"pattern": "bash:rm *", "action": "deny"},
                ],
            }
        )

        result = _permissions_from_config(cfg)
        assert result["bash:git *"] == "allow"
        assert result["bash:rm *"] == "deny"
        assert result["*"] == "ask"

    def test_permissions_from_config_flat_mapping(self):
        from praisonai.cli.commands.run import _permissions_from_config

        cfg = SimpleNamespace(permissions={"read:*": "allow", "bash:rm *": "deny"})

        result = _permissions_from_config(cfg)
        assert result["read:*"] == "allow"
        assert result["bash:rm *"] == "deny"

    def test_permissions_from_config_empty(self):
        from praisonai.cli.commands.run import _permissions_from_config

        cfg = SimpleNamespace(permissions={})

        assert _permissions_from_config(cfg) is None

    def test_permissions_from_config_skips_invalid_action(self):
        from praisonai.cli.commands.run import _permissions_from_config

        cfg = SimpleNamespace(
            permissions={
                "rules": [
                    {"pattern": "bash:git *", "action": "allow"},
                    {"pattern": "bash:evil *", "action": "exfiltrate"},
                ]
            }
        )
        result = _permissions_from_config(cfg)
        assert result == {"bash:git *": "allow"}

    def test_resolve_mcp_from_config_handles_non_dict(self):
        from praisonai.cli.commands.run import _resolve_mcp_from_config

        assert _resolve_mcp_from_config(SimpleNamespace(mcp=True)) is None


class TestApplyConfigDefaults:
    """`_apply_config_defaults` layers config under explicit CLI flags."""

    def _resolve_in_dir(self, tmp_path, monkeypatch, fn):
        monkeypatch.setenv("HOME", str(tmp_path / "home"))
        (tmp_path / "home").mkdir(parents=True, exist_ok=True)
        old_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            # Reset cached resolver so the new cwd is discovered.
            from praisonai.cli.configuration import resolver as resolver_mod

            resolver_mod.get_resolver(cwd=tmp_path, reset=True)
            return fn()
        finally:
            os.chdir(old_cwd)
            from praisonai.cli.configuration import resolver as resolver_mod

            resolver_mod.get_resolver(reset=True)

    def test_config_fills_mcp_and_permissions(self, tmp_path, monkeypatch):
        from praisonai.cli.commands.run import _apply_config_defaults

        _write_project_config(
            tmp_path,
            {
                "mcp": {
                    "servers": {
                        "playwright": {"command": ["npx", "-y", "@playwright/mcp"]}
                    }
                },
                "permissions": {
                    "default": "ask",
                    "rules": [{"pattern": "bash:rm *", "action": "deny"}],
                },
            },
        )

        mcp, _mcp_env, perms = self._resolve_in_dir(
            tmp_path,
            monkeypatch,
            lambda: _apply_config_defaults(None, None, None),
        )

        assert mcp == "npx -y @playwright/mcp"
        assert perms["bash:rm *"] == "deny"
        assert perms["*"] == "ask"

    def test_cli_permissions_override_config(self, tmp_path, monkeypatch):
        from praisonai.cli.commands.run import _apply_config_defaults

        _write_project_config(
            tmp_path,
            {
                "permissions": {
                    "rules": [{"pattern": "bash:rm *", "action": "deny"}],
                },
            },
        )

        # CLI flag allows what config denies; CLI must win.
        cli_perms = {"bash:rm *": "allow"}
        _, _, perms = self._resolve_in_dir(
            tmp_path,
            monkeypatch,
            lambda: _apply_config_defaults(None, None, cli_perms),
        )

        assert perms["bash:rm *"] == "allow"

    def test_explicit_mcp_flag_not_overridden(self, tmp_path, monkeypatch):
        from praisonai.cli.commands.run import _apply_config_defaults

        _write_project_config(
            tmp_path,
            {
                "mcp": {
                    "servers": {
                        "playwright": {"command": ["npx", "-y", "@playwright/mcp"]}
                    }
                },
            },
        )

        mcp, _, _ = self._resolve_in_dir(
            tmp_path,
            monkeypatch,
            lambda: _apply_config_defaults("custom-cmd", None, None),
        )

        assert mcp == "custom-cmd"
