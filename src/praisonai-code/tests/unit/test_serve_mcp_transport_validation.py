"""`praisonai serve mcp --transport <x>` must never fall through to SSE.

Before the fix, any value that was not exactly "stdio" hit the `else:` branch
and started an SSE listener, so a typo (`stido`) or an advertised-but-
unimplemented value (`http-stream`) silently changed the process from
"pipe only" to "listening socket". These tests monkeypatch both runners and
assert which one was reached; no server is ever started.
"""

import sys
import types

import pytest
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def transport_calls(monkeypatch):
    """Stub praisonaiagents.mcp so no real MCP server can be started."""
    calls = []

    class FakeToolsMCPServer:
        def __init__(self, name=None, tools=None):
            self.name = name

        def run(self, transport="stdio"):
            calls.append("stdio")

        def run_sse(self, host=None, port=8080, security=None):
            calls.append("sse")

    fake = types.ModuleType("praisonaiagents.mcp")
    fake.ToolsMCPServer = FakeToolsMCPServer
    fake.MCP = object
    monkeypatch.setitem(sys.modules, "praisonaiagents.mcp", fake)
    return calls


def _invoke(transport):
    from praisonai_code.cli.commands.serve import app

    return runner.invoke(app, ["mcp", "--transport", transport, "--port", "8080"])


def test_stdio_stays_on_the_pipe(transport_calls):
    result = _invoke("stdio")
    assert result.exit_code == 0
    assert transport_calls == ["stdio"]


def test_sse_starts_sse(transport_calls):
    result = _invoke("sse")
    assert result.exit_code == 0
    assert transport_calls == ["sse"]


@pytest.mark.parametrize("typo", ["stido", "studio", "STDIO", "bogus", ""])
def test_typo_does_not_open_a_listening_socket(transport_calls, typo):
    """A misspelling must be an error, not a silent switch to SSE."""
    result = _invoke(typo)
    assert transport_calls == [], (
        f"--transport {typo!r} started the {transport_calls} transport"
    )
    assert result.exit_code == 2
    # The error names the values the user could have meant.
    assert "stdio" in result.output and "sse" in result.output


def test_http_stream_is_rejected_not_aliased_to_sse(transport_calls):
    """http-stream is advertised but unimplemented here; reject it loudly."""
    result = _invoke("http-stream")
    assert transport_calls == [], "http-stream silently ran the SSE transport"
    assert result.exit_code == 2
    assert "http-stream" in result.output
    assert "praisonai mcp serve --transport http-stream" in result.output


def test_help_does_not_advertise_an_unsupported_transport():
    from praisonai_code.cli.commands.serve import app

    result = runner.invoke(app, ["mcp", "--help"])
    assert result.exit_code == 0
    # Strip Rich's line wrapping before matching.
    flat = " ".join(result.output.split())
    assert "http-stream" not in flat
    assert "stdio, sse" in flat
