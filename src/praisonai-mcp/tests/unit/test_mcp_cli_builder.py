"""Unit tests for praisonai-mcp CLI callers using the shared MCP config builder.

Verifies ``mcp sync`` and ``mcp run --transport sse`` delegate client creation
to ``MCP.from_config`` with ``expand_env=False`` (default), preserving
arguments with spaces, remote headers, legacy SSE header validation, URL
validation, disabled-server handling, and project trust boundaries.
"""

from __future__ import annotations

import types
from unittest.mock import MagicMock, patch

import pytest

from praisonai_mcp.cli.commands import mcp as mcp_cli


class _FakeOutput:
    def __init__(self, json_mode: bool = False):
        self.is_json_mode = json_mode
        self.messages: list[tuple[str, object]] = []

    def print(self, msg):
        self.messages.append(("print", msg))

    def print_info(self, msg):
        self.messages.append(("info", msg))

    def print_success(self, msg):
        self.messages.append(("success", msg))

    def print_error(self, msg):
        self.messages.append(("error", msg))

    def print_json(self, data):
        self.messages.append(("json", data))


def _record_mcp_init():
    """Patch MCP.__init__ (plus get_tools/to_openai_tool/shutdown) without spawning."""
    from praisonaiagents.mcp import MCP

    calls: list[tuple[object, object, dict]] = []

    def fake_init(self, target=None, args=None, **kw):
        calls.append((target, args, kw))

    stack = (
        patch.object(MCP, "__init__", fake_init),
        patch.object(MCP, "get_tools", return_value=[]),
        patch.object(MCP, "to_openai_tool", return_value=[]),
        patch.object(MCP, "shutdown", return_value=None),
    )
    return calls, stack


def _invoke_sync(servers: dict, *, server=None, timeout: float = 30.0, json_mode: bool = False):
    from praisonai_code.cli.configuration import schema as schema_mod

    output = _FakeOutput(json_mode=json_mode)
    loader = MagicMock()
    loader.load.return_value = types.SimpleNamespace(mcp=types.SimpleNamespace(servers=servers))

    calls, patches = _record_mcp_init()
    with patch.object(mcp_cli, "_require_code", lambda: None), \
         patch.object(mcp_cli, "get_config_loader", return_value=loader), \
         patch.object(mcp_cli, "get_output_controller", return_value=output), \
         patch.object(mcp_cli, "configuration_schema", return_value=schema_mod), \
         patches[0], patches[1], patches[2], patches[3]:
        mcp_cli.mcp_sync(server=server, timeout=timeout)
    return calls, output


def _json_result(output: _FakeOutput) -> dict:
    for kind, payload in output.messages:
        if kind == "json":
            return payload  # type: ignore[return-value]
    raise AssertionError(f"No json output captured: {output.messages}")


class TestMcpSyncSharedBuilder:
    def test_local_server_preserves_args_with_spaces(self):
        from praisonai_code.cli.configuration.schema import MCPLocalConfig

        srv = MCPLocalConfig(command="npx", args=["-y", "pkg", "/my docs"], env={"K": "v"})
        calls, output = _invoke_sync({"docs": srv}, timeout=45.0, json_mode=True)

        assert len(calls) == 1
        target, args, kw = calls[0]
        assert target == "npx"
        assert args == ["-y", "pkg", "/my docs"]
        assert kw["env"] == {"K": "v"}
        assert kw["timeout"] == 45
        assert _json_result(output)["synced_servers"] == ["docs"]

    def test_remote_server_forwards_headers(self):
        from praisonai_code.cli.configuration.schema import MCPRemoteConfig

        srv = MCPRemoteConfig(
            url="https://mcp.example/mcp",
            headers={"Authorization": "Bearer tok", "X-Team": "core"},
        )
        calls, output = _invoke_sync({"api": srv}, timeout=20.0, json_mode=True)

        assert len(calls) == 1
        target, _args, kw = calls[0]
        assert target == "https://mcp.example/mcp"
        assert kw["headers"] == {"Authorization": "Bearer tok", "X-Team": "core"}
        assert kw["timeout"] == 20
        assert _json_result(output)["synced_servers"] == ["api"]

    def test_remote_sse_authorization_header_refused(self):
        from praisonai_code.cli.configuration.schema import MCPRemoteConfig

        srv = MCPRemoteConfig(
            url="https://mcp.example/sse",
            headers={"Authorization": "Bearer tok"},
        )
        calls, output = _invoke_sync({"legacy": srv}, json_mode=True)

        assert calls == []
        res = _json_result(output)
        assert res["synced_servers"] == []
        assert res["failed_servers"] == ["legacy"]

    def test_remote_sse_non_auth_header_dropped_with_warning(self, caplog):
        from praisonai_code.cli.configuration.schema import MCPRemoteConfig

        srv = MCPRemoteConfig(
            url="https://mcp.example/sse",
            headers={"X-Trace": "1"},
        )
        with caplog.at_level("WARNING"):
            calls, output = _invoke_sync({"legacy": srv}, json_mode=True)

        assert len(calls) == 1
        target, _args, kw = calls[0]
        assert target == "https://mcp.example/sse"
        assert "headers" not in kw
        assert "SSE" in caplog.text
        assert _json_result(output)["synced_servers"] == ["legacy"]

    def test_remote_non_url_refused(self):
        from praisonai_code.cli.configuration.schema import MCPRemoteConfig

        srv = MCPRemoteConfig(url="touch MARKER")
        calls, output = _invoke_sync({"bad": srv}, json_mode=True)

        assert calls == []
        assert _json_result(output)["failed_servers"] == ["bad"]

    def test_remote_empty_url_reported(self):
        from praisonai_code.cli.configuration.schema import MCPRemoteConfig

        srv = MCPRemoteConfig(url="")
        calls, output = _invoke_sync({"empty": srv}, json_mode=True)

        assert calls == []
        assert _json_result(output)["failed_servers"] == ["empty"]
        assert any("no URL configured" in str(m) for k, m in output.messages if k == "error")

    def test_disabled_server_is_skipped(self):
        from praisonai_code.cli.configuration.schema import MCPLocalConfig

        srv = MCPLocalConfig(command="npx", args=["-y", "pkg"], enabled=False)
        calls, output = _invoke_sync({"off": srv}, json_mode=True)

        assert calls == []
        res = _json_result(output)
        assert res["synced_servers"] == []
        assert res["failed_servers"] == []

    def test_does_not_expand_env_vars_by_default(self, monkeypatch):
        from praisonai_code.cli.configuration.schema import MCPLocalConfig, MCPRemoteConfig

        monkeypatch.setenv("SOME_SECRET", "s3cret-value")
        servers = {
            "rem": MCPRemoteConfig(
                url="https://mcp.example/mcp?k=${SOME_SECRET}",
                headers={"X": "${env:SOME_SECRET}"},
            ),
            "loc": MCPLocalConfig(
                command="npx",
                args=["${SOME_SECRET}"],
                env={"K": "${SOME_SECRET}"},
            ),
        }
        calls, _output = _invoke_sync(servers, json_mode=True)

        assert len(calls) == 2
        assert "s3cret-value" not in repr(calls)

    def test_remote_oauth_forwarded_to_shared_builder(self):
        from praisonai_code.cli.configuration.schema import MCPOAuthConfig, MCPRemoteConfig

        srv = MCPRemoteConfig(
            url="https://mcp.example/mcp",
            oauth=MCPOAuthConfig(client_id="cid", scopes=["read"]),
        )
        calls, output = _invoke_sync({"gh": srv}, json_mode=True)

        assert len(calls) == 1
        assert calls[0][0] == "https://mcp.example/mcp"
        assert calls[0][2]["oauth"] == {"client_id": "cid", "scopes": ["read"]}
        assert calls[0][2]["server_name"] == "gh"
        assert _json_result(output)["synced_servers"] == ["gh"]

    def test_project_config_loader_drops_untrusted_and_never_expands_env(self, tmp_path, monkeypatch):
        import json
        from praisonai_code.cli.configuration.loader import ConfigLoader

        home = tmp_path / "home"
        (home / ".praisonai").mkdir(parents=True)
        (home / ".praisonai" / "config.yaml").write_text(
            json.dumps({"mcp": {"trusted_servers": ["https://mcp.example/mcp"]}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.setenv("PRAISONAI_HOME", str(home / ".praisonai"))
        monkeypatch.setenv("SOME_SECRET", "s3cret-value")

        repo = tmp_path / "repo"
        (repo / ".praisonai").mkdir(parents=True)
        (repo / ".praisonai" / "config.toml").write_text(
            '[mcp.servers.evil]\n'
            'type = "local"\n'
            'command = "python3"\n'
            'args = ["-c", "print(1)"]\n'
            '\n'
            '[mcp.servers.rem]\n'
            'type = "remote"\n'
            'url = "https://mcp.example/mcp"\n'
            '[mcp.servers.rem.headers]\n'
            'X = "${SOME_SECRET}"\n',
            encoding="utf-8",
        )
        monkeypatch.chdir(repo)

        real_loader = ConfigLoader(project_root=repo)
        output = _FakeOutput(json_mode=True)
        calls, patches = _record_mcp_init()
        from praisonai_code.cli.configuration import schema as schema_mod

        with patch.object(mcp_cli, "_require_code", lambda: None), \
             patch.object(mcp_cli, "get_config_loader", return_value=real_loader), \
             patch.object(mcp_cli, "get_output_controller", return_value=output), \
             patch.object(mcp_cli, "configuration_schema", return_value=schema_mod), \
             patches[0], patches[1], patches[2], patches[3]:
            mcp_cli.mcp_sync(server=None, timeout=15.0)

        assert len(calls) == 1
        assert calls[0][0] == "https://mcp.example/mcp"
        assert calls[0][2]["headers"] == {"X": "${SOME_SECRET}"}
        assert "s3cret-value" not in repr(calls)


class TestMcpRunSharedBuilder:
    def test_sse_mode_preserves_args_with_spaces_and_does_not_expand_env(self, monkeypatch):
        from praisonai_code.cli.configuration.schema import MCPLocalConfig

        monkeypatch.setenv("SOME_SECRET", "s3cret-value")
        srv = MCPLocalConfig(
            command="npx",
            args=["-y", "pkg", "/my docs", "${SOME_SECRET}"],
            env={"K": "${SOME_SECRET}"},
        )
        loader = MagicMock()
        loader.load.return_value = types.SimpleNamespace(mcp=types.SimpleNamespace(servers={"docs": srv}))
        output = _FakeOutput()
        sse_runs: list[tuple[str, int]] = []

        class FakeToolsServer:
            def __init__(self, name, tools):
                self.name = name
                self.tools = tools

            def run_sse(self, host, port):
                sse_runs.append((host, port))

        calls, patches = _record_mcp_init()
        with patch.object(mcp_cli, "_require_code", lambda: None), \
             patch.object(mcp_cli, "get_config_loader", return_value=loader), \
             patch.object(mcp_cli, "get_output_controller", return_value=output), \
             patch("praisonaiagents.mcp.ToolsMCPServer", FakeToolsServer), \
             patches[0], patches[1], patches[2], patches[3]:
            mcp_cli.mcp_run(name="docs", port=9001, host="127.0.0.1", transport="sse")

        assert len(calls) == 1
        target, args, kw = calls[0]
        assert target == "npx"
        assert args == ["-y", "pkg", "/my docs", "${SOME_SECRET}"]
        assert kw["env"] == {"K": "${SOME_SECRET}"}
        assert kw["timeout"] == 60
        assert "s3cret-value" not in repr(calls)
        assert sse_runs == [("127.0.0.1", 9001)]

    def test_sse_mode_refuses_disabled_server(self):
        import typer
        from praisonai_code.cli.configuration.schema import MCPLocalConfig

        srv = MCPLocalConfig(command="npx", args=["-y", "pkg"], enabled=False)
        loader = MagicMock()
        loader.load.return_value = types.SimpleNamespace(mcp=types.SimpleNamespace(servers={"off": srv}))
        output = _FakeOutput()

        calls, patches = _record_mcp_init()
        with patch.object(mcp_cli, "_require_code", lambda: None), \
             patch.object(mcp_cli, "get_config_loader", return_value=loader), \
             patch.object(mcp_cli, "get_output_controller", return_value=output), \
             patches[0], patches[1], patches[2], patches[3]:
            with pytest.raises(typer.Exit) as exc:
                mcp_cli.mcp_run(name="off", port=9001, host="127.0.0.1", transport="sse")

        assert exc.value.exit_code == 1
        assert calls == []
