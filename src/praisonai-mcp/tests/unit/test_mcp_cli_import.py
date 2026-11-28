"""Unit tests for C-7: ``praisonai mcp import <editor> [--file] [--dry-run] [--overwrite]``."""

from __future__ import annotations

import os
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from praisonai_mcp.cli.commands import mcp as mcp_cli


class _FakeOutput:
    def __init__(self, json_mode: bool = False):
        self.is_json_mode = json_mode
        self.messages: list[tuple[str, object]] = []

    def print(self, msg): self.messages.append(("print", msg))
    def print_info(self, msg): self.messages.append(("info", msg))
    def print_warning(self, msg): self.messages.append(("warning", msg))
    def print_success(self, msg): self.messages.append(("success", msg))
    def print_error(self, msg): self.messages.append(("error", msg))
    def print_json(self, data): self.messages.append(("json", data))


def _invoke_cli(args: list[str], *, servers: dict | None = None, json_mode: bool = False):
    output = _FakeOutput(json_mode=json_mode)
    loader = MagicMock()
    loader.load.return_value = types.SimpleNamespace(mcp=types.SimpleNamespace(servers=servers or {}))
    with patch.object(mcp_cli, "_require_code", lambda: None), \
         patch.object(mcp_cli, "get_config_loader", return_value=loader), \
         patch.object(mcp_cli, "get_output_controller", return_value=output):
        result = CliRunner().invoke(mcp_cli.app, args)
    return result, loader, output


def test_mcp_import_cursor_json_preserves_placeholders_and_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LINEAR_API_KEY", "super-secret-live-value")
    monkeypatch.setenv("GH_TOKEN", "ghp_live_secret_value")

    cursor_cfg = tmp_path / ".cursor" / "mcp.json"
    cursor_cfg.parent.mkdir(parents=True)
    original_text = (
        '{\n'
        '  "mcpServers": {\n'
        '    "linear": {\n'
        '      "url": "https://mcp.linear.app/mcp",\n'
        '      "headers": {"Authorization": "Bearer ${LINEAR_API_KEY}"}\n'
        '    },\n'
        '    "github": {\n'
        '      "command": "npx",\n'
        '      "args": ["-y", "@modelcontextprotocol/server-github"],\n'
        '      "env": {"GITHUB_TOKEN": "${GH_TOKEN}"}\n'
        '    }\n'
        '  }\n'
        '}\n'
    )
    cursor_cfg.write_text(original_text, encoding="utf-8")
    before_mtime = cursor_cfg.stat().st_mtime_ns

    res, loader, output = _invoke_cli(["import", "cursor"])
    assert res.exit_code == 0, res.output

    # Strictly read-only on the editor's file
    assert cursor_cfg.read_text(encoding="utf-8") == original_text
    assert cursor_cfg.stat().st_mtime_ns == before_mtime

    saved = {call.args[0]: call.args[1] for call in loader.set.call_args_list}
    assert set(saved) == {"mcp.servers.linear", "mcp.servers.github"}

    # Placeholders stay unexpanded — live env secrets are NEVER written back to disk
    assert saved["mcp.servers.linear"]["type"] == "remote"
    assert saved["mcp.servers.linear"]["url"] == "https://mcp.linear.app/mcp"
    assert saved["mcp.servers.linear"]["headers"] == {"Authorization": "Bearer ${LINEAR_API_KEY}"}
    assert "super-secret-live-value" not in str(saved)

    assert saved["mcp.servers.github"]["type"] == "local"
    assert saved["mcp.servers.github"]["command"] == "npx"
    assert saved["mcp.servers.github"]["env"] == {"GITHUB_TOKEN": "${GH_TOKEN}"}
    assert "ghp_live_secret_value" not in str(saved)

    # Round-trips cleanly through praisonai-code ConfigSchema
    from praisonai_code.cli.configuration.schema import ConfigSchema, MCPLocalConfig, MCPRemoteConfig

    cfg = ConfigSchema.from_dict({"mcp": {"servers": {
        "linear": saved["mcp.servers.linear"],
        "github": saved["mcp.servers.github"],
    }}})
    assert isinstance(cfg.mcp.servers["linear"], MCPRemoteConfig)
    assert isinstance(cfg.mcp.servers["github"], MCPLocalConfig)


def test_mcp_import_zed_jsonc_with_comments_and_other_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    zed_cfg = tmp_path / ".config" / "zed" / "settings.json"
    zed_cfg.parent.mkdir(parents=True)
    zed_cfg.write_text(
        '{\n'
        '  // User theme setting — not an MCP server\n'
        '  "theme": "One Dark",\n'
        '  /* MCP servers container for Zed */\n'
        '  "context_servers": {\n'
        '    "docs": {\n'
        '      "url": "https://docs.example.com/mcp",\n'
        '    },\n'
        '  },\n'
        '}\n',
        encoding="utf-8",
    )

    res, loader, _ = _invoke_cli(["import", "zed"])
    assert res.exit_code == 0, res.output
    saved = {call.args[0]: call.args[1] for call in loader.set.call_args_list}
    assert list(saved) == ["mcp.servers.docs"]
    assert saved["mcp.servers.docs"]["url"] == "https://docs.example.com/mcp"
    assert saved["mcp.servers.docs"]["type"] == "remote"


def test_mcp_import_codex_toml_normalizes_bearer_token_env_var(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OPENAI_MCP_TOKEN", "live-bearer-secret")
    codex_cfg = tmp_path / ".codex" / "config.toml"
    codex_cfg.parent.mkdir(parents=True)
    codex_cfg.write_text(
        '[mcp_servers.sentry]\n'
        'url = "https://mcp.sentry.dev/mcp"\n'
        'bearer_token_env_var = "OPENAI_MCP_TOKEN"\n'
        'enabled_tools = ["list_issues"]\n',
        encoding="utf-8",
    )

    res, loader, _ = _invoke_cli(["import", "codex"])
    assert res.exit_code == 0, res.output
    saved = {call.args[0]: call.args[1] for call in loader.set.call_args_list}
    assert list(saved) == ["mcp.servers.sentry"]
    entry = saved["mcp.servers.sentry"]
    assert entry["type"] == "remote"
    assert entry["url"] == "https://mcp.sentry.dev/mcp"
    assert entry["headers"] == {"Authorization": "Bearer ${OPENAI_MCP_TOKEN}"}
    assert entry["allowed_tools"] == ["list_issues"]
    assert "live-bearer-secret" not in str(entry)


def test_mcp_import_dry_run_makes_no_writes(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".cursor" / "mcp.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"mcpServers": {"linear": {"url": "https://mcp.linear.app/mcp"}}}', encoding="utf-8")

    res, loader, output = _invoke_cli(["import", "cursor", "--dry-run"])
    assert res.exit_code == 0, res.output
    loader.set.assert_not_called()
    rendered = " ".join(str(m) for _, m in output.messages)
    assert "linear" in rendered


def test_mcp_import_skips_existing_unless_overwrite(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".cursor" / "mcp.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '{"mcpServers": {'
        '"existing": {"url": "https://new.example.com/mcp"},'
        '"fresh": {"url": "https://fresh.example.com/mcp"}'
        '}}',
        encoding="utf-8",
    )

    res, loader, output = _invoke_cli(["import", "cursor"], servers={"existing": object()})
    assert res.exit_code == 0, res.output
    saved = {call.args[0]: call.args[1] for call in loader.set.call_args_list}
    assert list(saved) == ["mcp.servers.fresh"]
    assert any("Skipped" in str(m) and "existing" in str(m) for _, m in output.messages)

    res2, loader2, _ = _invoke_cli(["import", "cursor", "--overwrite"], servers={"existing": object()})
    assert res2.exit_code == 0, res2.output
    saved2 = {call.args[0]: call.args[1] for call in loader2.set.call_args_list}
    assert set(saved2) == {"mcp.servers.existing", "mcp.servers.fresh"}


def test_mcp_import_project_file_filters_untrusted_local_servers(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    repo = tmp_path / "repo"
    proj_cfg = repo / ".cursor" / "mcp.json"
    proj_cfg.parent.mkdir(parents=True)
    proj_cfg.write_text(
        '{"mcpServers": {'
        '"evil_local": {"command": "sh", "args": ["-c", "id"]},'
        '"safe_remote": {"url": "https://mcp.example.com/mcp", "headers": {"X-Key": "${MY_SECRET}"}}'
        '}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PRAISONAI_HOME", str(home / ".praisonai"))
    monkeypatch.setenv("MY_SECRET", "do-not-leak")
    monkeypatch.chdir(repo)

    res, loader, output = _invoke_cli(["import", "--file", ".cursor/mcp.json"])
    assert res.exit_code == 0, res.output
    saved = {call.args[0]: call.args[1] for call in loader.set.call_args_list}
    assert list(saved) == ["mcp.servers.safe_remote"]
    assert saved["mcp.servers.safe_remote"]["headers"] == {"X-Key": "${MY_SECRET}"}
    assert "do-not-leak" not in str(saved)
    assert any("evil_local" in str(m) for _, m in output.messages)


def test_mcp_import_json_output_redacts_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".cursor" / "mcp.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '{"mcpServers": {'
        '"linear": {"url": "https://mcp.linear.app/mcp", "headers": {"Authorization": "Bearer secret-tok"}},'
        '"local": {"command": "npx", "args": ["srv"], "env": {"API_KEY": "env-secret-val"}}'
        '}}',
        encoding="utf-8",
    )

    res, _, output = _invoke_cli(["import", "cursor"], json_mode=True)
    assert res.exit_code == 0, res.output
    json_payloads = [m for k, m in output.messages if k == "json"]
    assert len(json_payloads) == 1
    payload = json_payloads[0]
    assert set(payload["imported"]) == {"linear", "local"}
    assert "secret-tok" not in str(payload)
    assert "env-secret-val" not in str(payload)


def test_mcp_import_errors_cleanly_on_unknown_editor_or_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    res_bad, loader_bad, output_bad = _invoke_cli(["import", "not-an-editor"])
    assert res_bad.exit_code == 1
    loader_bad.set.assert_not_called()
    assert any(k == "error" and "Unknown client" in str(m) for k, m in output_bad.messages)

    res_missing, loader_missing, output_missing = _invoke_cli(["import", "cursor"])
    assert res_missing.exit_code == 1
    loader_missing.set.assert_not_called()
    assert any(k == "error" and "not found" in str(m).lower() for k, m in output_missing.messages)

    res_none, loader_none, _ = _invoke_cli(["import"])
    assert res_none.exit_code == 1
    loader_none.set.assert_not_called()
