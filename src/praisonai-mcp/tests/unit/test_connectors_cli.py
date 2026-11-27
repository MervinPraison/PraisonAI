"""TDD unit tests for official remote MCP connector catalog and `praisonai connectors` CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner


runner = CliRunner()


class TestConnectorsCatalog:
    """Built-in official remote MCP connector catalog invariants."""

    def test_catalog_entries_have_https_urls_and_case_insensitive_lookup(self):
        from praisonai_mcp.connect.connectors_catalog import (
            CONNECTOR_CATALOG,
            ConnectorEntry,
            get_connector,
            list_connectors,
        )

        entries = list_connectors()
        assert len(entries) >= 6
        assert len(entries) == len(CONNECTOR_CATALOG)
        for entry in entries:
            assert isinstance(entry, ConnectorEntry)
            assert entry.id == entry.id.lower()
            assert entry.url.startswith("https://")
            assert entry.label
            assert get_connector(entry.id) == entry
            assert get_connector(entry.id.upper()) == entry

        assert get_connector("linear").url == "https://mcp.linear.app/mcp"
        assert get_connector("linear").oauth is True
        assert get_connector("notion").url == "https://mcp.notion.com/mcp"
        assert get_connector("github").url == "https://api.githubcopilot.com/mcp/"
        assert get_connector("nonexistent-connector-xyz") is None


class TestConnectorsCli:
    """`praisonai connectors` CLI subcommands and delegation to `praisonai mcp`."""

    def test_catalog_text_and_json_output(self):
        from praisonai_mcp.cli.commands.connectors import app

        res_text = runner.invoke(app, ["catalog"])
        assert res_text.exit_code == 0, res_text.output
        assert "linear" in res_text.output
        assert "https://mcp.linear.app/mcp" in res_text.output
        assert "github" in res_text.output

        res_json = runner.invoke(app, ["catalog", "--json"])
        assert res_json.exit_code == 0, res_json.output
        payload = json.loads(res_json.output)
        assert "connectors" in payload
        ids = {c["id"] for c in payload["connectors"]}
        assert {"github", "linear", "notion"}.issubset(ids)
        assert all(c["url"].startswith("https://") for c in payload["connectors"])

    def test_add_catalog_entry_resolves_url_and_oauth_and_writes_config(self, tmp_path, monkeypatch):
        from praisonai_code.cli.configuration import loader as cfg_loader
        from praisonai_mcp.cli.commands.connectors import app

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("PRAISONAI_HOME", str(home / ".praisonai"))
        monkeypatch.setattr(cfg_loader, "_config_loader", None, raising=False)

        res = runner.invoke(app, ["add", "linear"])
        assert res.exit_code == 0, res.output

        raw = cfg_loader._load_toml(home / ".praisonai" / "config.toml")
        srv = raw["mcp"]["servers"]["linear"]
        assert srv["url"] == "https://mcp.linear.app/mcp"
        assert srv["oauth"] is True

    def test_add_custom_url_forwards_options(self, tmp_path, monkeypatch):
        from praisonai_code.cli.configuration import loader as cfg_loader
        from praisonai_mcp.cli.commands.connectors import app

        home = tmp_path / "home"
        home.mkdir()
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("PRAISONAI_HOME", str(home / ".praisonai"))
        monkeypatch.setattr(cfg_loader, "_config_loader", None, raising=False)

        res = runner.invoke(
            app,
            [
                "add",
                "custom",
                "--url",
                "https://example.com/mcp",
                "--header",
                "X-Team=core",
                "--allow",
                "read_item,list_items",
            ],
        )
        assert res.exit_code == 0, res.output

        raw = cfg_loader._load_toml(home / ".praisonai" / "config.toml")
        srv = raw["mcp"]["servers"]["custom"]
        assert srv["url"] == "https://example.com/mcp"
        assert srv["headers"] == {"X-Team": "core"}
        assert srv["allowed_tools"] == ["read_item", "list_items"]

    def test_add_unknown_name_without_url_exits_1_listing_catalog(self):
        from praisonai_mcp.cli.commands.connectors import app

        res = runner.invoke(app, ["add", "unknown_xyz"])
        assert res.exit_code == 1
        assert "unknown_xyz" in res.output
        assert "linear" in res.output
        assert "--url" in res.output

    def test_list_remove_test_delegate_to_mcp_commands(self):
        from praisonai_mcp.cli.commands import connectors as mod

        with (
            patch.object(mod, "mcp_list") as p_list,
            patch.object(mod, "mcp_remove") as p_remove,
            patch.object(mod, "mcp_test") as p_test,
        ):
            r1 = runner.invoke(mod.app, ["list", "--json"])
            assert r1.exit_code == 0, r1.output
            p_list.assert_called_once_with(json_output=True)

            r2 = runner.invoke(mod.app, ["remove", "linear", "--yes"])
            assert r2.exit_code == 0, r2.output
            p_remove.assert_called_once_with(name="linear", confirm=True)

            r3 = runner.invoke(mod.app, ["test", "linear", "--timeout", "5"])
            assert r3.exit_code == 0, r3.output
            p_test.assert_called_once_with(name="linear", timeout=5.0)

    def test_cli_entrypoints_connectors_help_and_distinction_from_connect(self, tmp_path):
        repo = Path(__file__).resolve().parents[4]
        env = os.environ.copy()
        env["HOME"] = str(tmp_path)
        env["PRAISONAI_HOME"] = str(tmp_path / ".praisonai")
        env["PYTHONPATH"] = os.pathsep.join(
            [
                str(repo / "src" / "praisonai-agents"),
                str(repo / "src" / "praisonai-code"),
                str(repo / "src" / "praisonai-mcp"),
                str(repo / "src" / "praisonai"),
            ]
        )

        for module in ("praisonai", "praisonai_code"):
            proc = subprocess.run(
                [sys.executable, "-m", module, "connectors", "--help"],
                capture_output=True,
                text=True,
                env=env,
                timeout=30,
            )
            assert proc.returncode == 0, f"{module}: {proc.stdout}\n{proc.stderr}"
            out = proc.stdout.lower()
            assert "catalog" in out
            assert "connect" in out  # distinguishes from `praisonai connect`
