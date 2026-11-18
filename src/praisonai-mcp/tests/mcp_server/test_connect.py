"""``praisonai connect``: catalog, config writers, verify, ledger and CLI.

Every config path lives under ``tmp_path`` (a fake HOME); nothing here reads
or writes a real editor config, and no test calls an LLM.
"""

from __future__ import annotations

import base64
import json
import sys
import textwrap
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import pytest
from typer.testing import CliRunner

from praisonai_mcp.connect import catalog as cat
from praisonai_mcp.connect import config_io, probe

SECRET = "sk-live-THIS-MUST-NEVER-BE-WRITTEN-123456"


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.setenv("PRAISONAI_HOME", str(h / ".praisonai"))
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    monkeypatch.setenv("PATH", str(tmp_path / "nobin"))
    from praisonai_mcp.cli.commands import connect as cmd

    monkeypatch.setattr(cmd, "APPS_DIRS", (tmp_path / "Applications",))
    return h


SPEC = cat.ServerSpec(command="/opt/bin/praisonai-mcp", args=("serve", "--transport", "stdio"), env=("OPENAI_API_KEY",))


# --------------------------------------------------------------------------- catalog


def test_catalog_ids_are_unique_and_grouped():
    assert len(cat.BY_ID) == len(cat.CLIENTS)
    assert {c.group for c in cat.CLIENTS} == {"editor", "terminal", "other"}


@pytest.mark.parametrize("client", cat.CLIENTS, ids=lambda c: c.id)
def test_every_client_renders_without_secret_values(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    spec = cat.local_spec(env=["OPENAI_API_KEY"])
    blob = json.dumps(cat.export_catalog(spec, Path("/h")))
    assert SECRET not in blob
    assert cat.snippet(client, spec)


def test_env_references_use_each_clients_syntax():
    refs = {c.id: cat.env_values(c, SPEC).get("OPENAI_API_KEY") for c in cat.CLIENTS}
    assert refs["cursor"] == "${env:OPENAI_API_KEY}"
    assert refs["vscode"] == "${OPENAI_API_KEY}"
    assert refs["claude-code"] == "${OPENAI_API_KEY}"
    assert refs["opencode"] == "{env:OPENAI_API_KEY}"
    assert refs["claude-desktop"] is None  # no interpolation: nothing written
    assert cat.entry(cat.get_client("codex"), SPEC)["env_vars"] == ["OPENAI_API_KEY"]


def test_cursor_deeplink_carries_base64_entry_and_scope():
    spec = cat.ServerSpec(command="/x", args=("serve", "--tools", "ask_*"))
    link = cat.deeplink(cat.get_client("cursor"), spec)
    q = parse_qs(urlparse(link).query)
    assert link.startswith("cursor://anysphere.cursor-deeplink/mcp/install?")
    assert q["name"] == ["praisonai"]
    assert json.loads(base64.b64decode(q["config"][0])) == {"command": "/x", "args": ["serve", "--tools", "ask_*"]}


def test_vscode_kiro_lmstudio_links():
    vs = cat.deeplink(cat.get_client("vscode"), SPEC)
    assert vs.startswith("vscode:mcp/install?")
    body = json.loads(unquote(vs.split("?", 1)[1]))
    # The link writes VS Code's editor-format config: ${env:NAME}, no Copilot "tools" key.
    assert body["name"] == "praisonai" and body["type"] == "stdio" and "tools" not in body
    assert body["env"] == {"OPENAI_API_KEY": "${env:OPENAI_API_KEY}"}
    assert cat.deeplink(cat.get_client("vscode-insiders"), SPEC).startswith("vscode-insiders:mcp/install?")
    kiro = parse_qs(urlparse(cat.deeplink(cat.get_client("kiro"), SPEC)).query)
    assert json.loads(kiro["config"][0])["command"] == "/opt/bin/praisonai-mcp"
    lm = parse_qs(urlparse(cat.deeplink(cat.get_client("lm-studio"), SPEC)).query)
    assert json.loads(base64.b64decode(lm["config"][0]))["args"][0] == "serve"
    trae = parse_qs(urlparse(cat.deeplink(cat.get_client("trae"), SPEC)).query)
    assert trae["type"] == ["stdio"] and json.loads(base64.b64decode(trae["config"][0]))["command"]


def test_cursor_link_survives_plus_and_respects_the_length_cap():
    plus = cat.ServerSpec(command="/x", args=(">>>",))  # base64 of this JSON contains "+"
    link = cat.deeplink(cat.get_client("cursor"), plus)
    raw = link.split("config=", 1)[1]
    assert "%2B" in raw and "+" not in raw and json.loads(base64.b64decode(parse_qs(urlparse(link).query)["config"][0]))
    huge = cat.ServerSpec(command="/x", args=("a" * 9000,))
    assert cat.deeplink(cat.get_client("cursor"), huge) is None


def test_commands_quote_env_references_not_values():
    cmd = cat.command(cat.get_client("claude-code"), SPEC)
    assert cmd.startswith("claude mcp add --env 'OPENAI_API_KEY=${OPENAI_API_KEY}' --transport stdio --scope user praisonai -- ")
    assert cat.command(cat.get_client("codex"), SPEC).startswith("codex mcp add praisonai -- /opt/bin/praisonai-mcp")


def test_remote_url_entries_and_local_only_clients():
    spec = cat.ServerSpec(url="https://agents.example.com/mcp")
    assert cat.entry(cat.get_client("cursor"), spec) == {"url": spec.url}
    assert cat.entry(cat.get_client("windsurf"), spec) == {"url": spec.url, "transport": "http"}
    assert cat.entry(cat.get_client("antigravity"), spec) == {"serverUrl": spec.url}
    assert cat.entry(cat.get_client("zed"), spec) == {"url": spec.url}
    assert cat.entry(cat.get_client("vscode"), spec) == {"type": "http", "url": spec.url}
    with pytest.raises(ValueError):
        cat.entry(cat.get_client("claude-desktop"), spec)
    rows = {r["id"]: r for r in cat.export_catalog(spec, Path("/h"))}
    assert rows["claude-desktop"]["deeplink"] is None and "local" in rows["claude-desktop"]["snippet"]


def test_local_spec_scopes_through_server_args(tmp_path):
    agents = tmp_path / "agents.yaml"
    agents.write_text("agents: {}\n")
    spec = cat.local_spec(tools=["ask_*", "list_agents"], agents=str(agents), env=[])
    assert spec.args[-4:] == ("--tools", "ask_*,list_agents", "--agents", str(agents.resolve()))


def test_client_for_maps_client_info_names():
    assert cat.client_for("claude-code") == "claude-code"
    assert cat.client_for("claude-ai") == "claude-desktop"
    assert cat.client_for("Visual Studio Code") == "vscode"
    assert cat.client_for("cursor-vscode") == "cursor"
    assert cat.client_for("something-else") is None


# --------------------------------------------------------------------------- config_io


def test_json_merge_keeps_other_servers_is_idempotent_and_backs_up(home):
    c = cat.get_client("cursor")
    path = cat.config_path(c, home)
    path.parent.mkdir(parents=True)
    path.write_text('{"mcpServers": {"other": {"command": "x"}}, "theme": 1}')
    plan = config_io.plan_write(c, SPEC, home)
    assert plan.changed and "+    \"praisonai\"" in plan.diff
    backup = config_io.apply(plan)
    assert backup.read_text() == '{"mcpServers": {"other": {"command": "x"}}, "theme": 1}'
    data = json.loads(path.read_text())
    assert data["theme"] == 1 and set(data["mcpServers"]) == {"other", "praisonai"}
    assert not config_io.plan_write(c, SPEC, home).changed
    removed = config_io.plan_remove(c, home, "praisonai")
    config_io.apply(removed)
    assert json.loads(path.read_text()) == {"mcpServers": {"other": {"command": "x"}}, "theme": 1}
    assert config_io.plan_remove(c, home, "praisonai") is None


def test_new_file_is_private(home):
    c = cat.get_client("claude-code")
    config_io.apply(config_io.plan_write(c, SPEC, home))
    path = cat.config_path(c, home)
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text())["mcpServers"]["praisonai"]["type"] == "stdio"


def test_toml_keeps_comments_and_other_tables(home):
    c = cat.get_client("codex")
    path = cat.config_path(c, home)
    path.parent.mkdir(parents=True)
    original = '# mine\nmodel = "o3"\n\n[mcp_servers.other]\ncommand = "y"\n'
    path.write_text(original)
    config_io.apply(config_io.plan_write(c, SPEC, home))
    text = path.read_text()
    assert text.startswith(original) and '[mcp_servers.praisonai]\ncommand = "/opt/bin/praisonai-mcp"' in text
    assert not config_io.plan_write(c, SPEC, home).changed
    config_io.apply(config_io.plan_remove(c, home, "praisonai"))
    assert path.read_text() == original


def test_yaml_clients(home):
    for cid in ("continue", "goose"):
        c = cat.get_client(cid)
        config_io.apply(config_io.plan_write(c, SPEC, home))
        assert config_io.read_entry(c, home, "praisonai")
        assert not config_io.plan_write(c, SPEC, home).changed


def test_zed_comments_are_never_dropped(home):
    c = cat.get_client("zed")
    path = cat.config_path(c, home)
    path.parent.mkdir(parents=True)
    path.write_text('{\n  // my font\n  "buffer_font_size": 15,\n}\n')
    with pytest.raises(config_io.ConfigError, match="comments"):
        config_io.plan_write(c, SPEC, home)
    assert config_io.read_entry(c, home, "praisonai") is None


def test_plaintext_secret_detection():
    assert config_io.plaintext_secrets({"env": {"OPENAI_API_KEY": SECRET, "X": "${env:X}"}}) == ["OPENAI_API_KEY"]
    assert config_io.plaintext_secrets({"env": {"MODE": "debug"}}) == []


# --------------------------------------------------------------------------- probe


FAKE_SERVER = textwrap.dedent(
    """
    import json, sys
    for line in sys.stdin:
        msg = json.loads(line)
        if "id" not in msg:
            continue
        if msg["method"] == "initialize":
            out = {"serverInfo": {"name": "fake"}}
        else:
            cursor = (msg.get("params") or {}).get("cursor")
            out = {"tools": [{"name": "b"}]} if cursor else {"tools": [{"name": "a"}, {"name": "x"}], "nextCursor": "p2"}
        print("noise on stdout")
        print(json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": out}), flush=True)
    """
)


def test_verify_stdio_handshake_counts_paginated_tools(tmp_path):
    script = tmp_path / "fake.py"
    script.write_text(FAKE_SERVER)
    result = probe.verify(cat.ServerSpec(command=sys.executable, args=(str(script),)), timeout=20)
    assert result.ok and result.tools == 3 and result.server == "fake"
    assert result.names == ["a", "x", "b"]


def test_verify_reports_a_dead_server(tmp_path):
    script = tmp_path / "dead.py"
    script.write_text("import sys; sys.stderr.write('boom: bad flag\\n')")
    result = probe.verify(cat.ServerSpec(command=sys.executable, args=(str(script),)), timeout=20)
    assert not result.ok and "boom: bad flag" in result.error


def test_ledger_records_clients_and_skips_the_probe(tmp_path, monkeypatch):
    monkeypatch.delenv("PRAISONAI_MCP_PROBE", raising=False)
    path = tmp_path / "connections.json"
    probe.record({"name": "cursor-vscode", "version": "2"}, path=path, now=100)
    probe.record({"name": "cursor-vscode", "version": "2"}, path=path, now=200)
    probe.record({"name": probe.PROBE_CLIENT}, path=path, now=300)
    probe.record(None, path=path)
    rows = probe.connections(path)
    assert [(r["name"], r["first_seen"], r["last_active"], r["sessions"]) for r in rows] == [("cursor-vscode", 100, 200, 2)]


def test_server_initialize_records_the_client(monkeypatch):
    import asyncio

    from praisonai_mcp.mcp_server.server import MCPServer

    seen = []
    monkeypatch.setattr(probe, "record", lambda info, transport="stdio": seen.append((info, transport)))
    asyncio.run(MCPServer()._handle_initialize({"clientInfo": {"name": "Zed", "version": "1"}}))
    assert seen == [({"name": "Zed", "version": "1"}, "stdio")]


# --------------------------------------------------------------------------- serve scope


def test_keep_only_and_agents_file(tmp_path):
    from praisonai_mcp.mcp_server.agent_adapter import load_agents_file, register_agents
    from praisonai_mcp.mcp_server.registry import MCPToolRegistry

    f = tmp_path / "agents.yaml"
    f.write_text("agents:\n  support:\n    role: Support\n    instructions: Help\n  billing:\n    role: Billing\n")
    reg = MCPToolRegistry()
    register_agents(reg, load_agents_file(str(f)))
    assert {t.name for t in reg.list_all()} == {"ask_support", "ask_billing", "list_agents"}
    assert reg.keep_only(["ask_s*"]) == 1


# --------------------------------------------------------------------------- CLI


@pytest.fixture
def run(home, monkeypatch):
    from praisonai_mcp.cli.commands import connect as cmd

    monkeypatch.setattr(probe, "verify", lambda spec, timeout=30: probe.ProbeResult(True, 42, "praisonai"))
    runner = CliRunner()
    return lambda *args: runner.invoke(cmd.app, list(args))


def test_status_lists_installed_and_connected(run, home):
    (home / ".cursor").mkdir()
    out = run("--json")
    rows = {r["id"]: r["status"] for r in json.loads(out.stdout)["clients"]}
    assert rows["cursor"] == "installed" and rows["zed"] == "not installed"
    assert run("cursor").exit_code == 0
    rows = {r["id"]: r["status"] for r in json.loads(run("--json").stdout)["clients"]}
    assert rows["cursor"] == "connected"


def test_connect_writes_verifies_and_never_writes_a_secret(run, home):
    res = run("cursor", "codex", "--tools", "ask_*")
    assert res.exit_code == 0, res.output
    assert "42 tools ready" in res.output
    cursor = (home / ".cursor/mcp.json").read_text()
    assert "${env:OPENAI_API_KEY}" in cursor and SECRET not in cursor and "ask_*" in cursor
    assert SECRET not in (home / ".codex/config.toml").read_text()


def test_tool_cap_warning(run, home):
    res = run("trae")
    assert res.exit_code == 0 and "TRAE uses at most 40 tools" in res.output


def test_dry_run_and_print_write_nothing(run, home):
    assert "praisonai" in run("cursor", "--dry-run").output
    assert "cursor://anysphere.cursor-deeplink" in run("cursor", "--print").output
    assert json.loads(run("--print", "--json").stdout)
    assert not (home / ".cursor").exists()


def test_all_and_remove_everywhere(run, home):
    (home / ".cursor").mkdir()
    (home / ".gemini").mkdir()
    assert run("--all").exit_code == 0
    assert (home / ".gemini/settings.json").exists()
    res = run("--remove")
    assert res.exit_code == 0
    assert json.loads((home / ".cursor/mcp.json").read_text()) == {"mcpServers": {}}
    assert "Nothing to remove" in run("--remove").output


def test_unknown_client_and_bad_scope(run):
    assert run("notepad").exit_code != 0
    assert run("cursor", "--url", "https://x/mcp", "--tools", "a").exit_code != 0
