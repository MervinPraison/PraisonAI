"""Unit tests for C-2: remote ``praisonai mcp add --url`` and real-probe ``praisonai mcp test``."""

from __future__ import annotations

import json
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from praisonai_mcp.cli.commands import mcp as mcp_cli
from praisonai_mcp.connect import probe
from praisonai_mcp.connect.catalog import ServerSpec


class _FakeOutput:
    def __init__(self, json_mode: bool = False):
        self.is_json_mode = json_mode
        self.messages: list[tuple[str, object]] = []

    def print(self, msg): self.messages.append(("print", msg))
    def print_info(self, msg): self.messages.append(("info", msg))
    def print_success(self, msg): self.messages.append(("success", msg))
    def print_error(self, msg): self.messages.append(("error", msg))
    def print_json(self, data): self.messages.append(("json", data))


def _invoke_cli(args: list[str], *, servers: dict | None = None, json_mode: bool = False):
    from praisonai_code.cli.configuration import schema as schema_mod

    output = _FakeOutput(json_mode=json_mode)
    loader = MagicMock()
    loader.load.return_value = types.SimpleNamespace(mcp=types.SimpleNamespace(servers=servers or {}))
    with patch.object(mcp_cli, "_require_code", lambda: None), \
         patch.object(mcp_cli, "get_config_loader", return_value=loader), \
         patch.object(mcp_cli, "get_output_controller", return_value=output), \
         patch.object(mcp_cli, "configuration_schema", return_value=schema_mod):
        result = CliRunner().invoke(mcp_cli.app, args)
    return result, loader, output


def test_mcp_add_remote_writes_headers_oauth_and_allowed_tools():
    res, loader, output = _invoke_cli([
        "add", "linear",
        "--url", "https://mcp.linear.app/mcp",
        "--header", "X-Team=eng",
        "--header", "Authorization=Bearer secret-tok",
        "--oauth",
        "--allow", "list_issues,create_issue",
    ])
    assert res.exit_code == 0, res.output
    loader.set.assert_called_once_with(
        "mcp.servers.linear",
        {
            "type": "remote",
            "url": "https://mcp.linear.app/mcp",
            "enabled": True,
            "headers": {"X-Team": "eng", "Authorization": "Bearer secret-tok"},
            "oauth": True,
            "allowed_tools": ["list_issues", "create_issue"],
        },
    )
    rendered = " ".join(str(m) for _, m in output.messages)
    assert "secret-tok" not in rendered


def test_mcp_add_stdio_remains_unchanged():
    res, loader, _ = _invoke_cli(["add", "docs", "npx", "--args", "-y pkg", "--env", "K=V"])
    assert res.exit_code == 0, res.output
    loader.set.assert_called_once_with(
        "mcp.servers.docs",
        {"command": "npx", "args": ["-y", "pkg"], "env": {"K": "V"}, "enabled": True},
    )


@pytest.mark.parametrize(
    "cli_args",
    [
        ["add", "bad", "--url", "ftp://example.com/mcp"],
        ["add", "bad", "--url", "npx"],
        ["add", "bad", "npx", "--url", "https://mcp.linear.app/mcp"],
        ["add", "bad"],
    ],
)
def test_mcp_add_rejects_invalid_url_or_conflicting_args(cli_args):
    res, loader, _ = _invoke_cli(cli_args)
    assert res.exit_code == 1
    loader.set.assert_not_called()


def test_mcp_test_remote_calls_probe_verify_with_url_and_headers():
    from praisonai_code.cli.configuration.schema import MCPRemoteConfig

    seen: list[tuple[ServerSpec, float]] = []

    def fake_verify(spec: ServerSpec, timeout: float = 30.0, **kw):
        seen.append((spec, timeout))
        return probe.ProbeResult(True, tools=5, server="linear", names=["a", "b", "c", "d", "e"])

    srv = MCPRemoteConfig(url="https://mcp.linear.app/mcp", headers={"X-Team": "eng"})
    with patch.object(probe, "verify", side_effect=fake_verify):
        res, _, output = _invoke_cli(["test", "linear", "--timeout", "15"], servers={"linear": srv})

    assert res.exit_code == 0
    assert len(seen) == 1
    spec, timeout = seen[0]
    assert spec.url == "https://mcp.linear.app/mcp"
    assert spec.headers == {"X-Team": "eng"}
    assert timeout == 15.0
    assert any(kind == "success" and "5" in str(msg) for kind, msg in output.messages)


def test_mcp_test_exits_1_with_clean_error_on_probe_failure():
    from praisonai_code.cli.configuration.schema import MCPRemoteConfig

    srv = MCPRemoteConfig(url="https://mcp.linear.app/mcp")
    with patch.object(probe, "verify", return_value=probe.ProbeResult(False, error="HTTP Error 401")):
        res, _, output = _invoke_cli(["test", "linear"], servers={"linear": srv})

    assert res.exit_code == 1
    assert any(kind == "error" and "401" in str(msg) for kind, msg in output.messages)


def test_probe_verify_url_forwards_headers_over_real_handshake():
    seen_headers: list[dict[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen_headers.append({k.lower(): v for k, v in self.headers.items()})
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            method = body.get("method")
            if method == "initialize":
                reply = {"jsonrpc": "2.0", "id": body["id"], "result": {"serverInfo": {"name": "mock-mcp"}}}
            elif method == "tools/list":
                reply = {"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "a"}, {"name": "b"}]}}
            else:
                reply = {}
            raw = json.dumps(reply).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        spec = ServerSpec(
            name="mock",
            url=f"http://127.0.0.1:{port}/mcp",
            headers={"X-Team": "eng", "Authorization": "Bearer s3cr3t"},
        )
        result = probe.verify(spec, timeout=5.0)
    finally:
        server.shutdown()
        server.server_close()

    assert result.ok and result.tools == 2 and result.server == "mock-mcp" and result.names == ["a", "b"]
    assert seen_headers and all(h.get("x-team") == "eng" for h in seen_headers)
    assert all(h.get("authorization") == "Bearer s3cr3t" for h in seen_headers)
