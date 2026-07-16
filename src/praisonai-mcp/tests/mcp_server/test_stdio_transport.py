"""
Tests for the STDIO transport.

Verifies the transport reads stdin via a thread (no
``loop.connect_read_pipe``) so it works on Windows ProactorEventLoop +
Python 3.13. See issue #3110.
"""

import asyncio
import io
import json


class _FakeStdin:
    """Minimal stdin stub exposing a ``buffer`` that yields byte lines."""

    def __init__(self, data: bytes):
        self.buffer = io.BytesIO(data)


class _FakeServer:
    def __init__(self):
        self.name = "test"
        self.received = []

    async def handle_message(self, message):
        self.received.append(message)
        return {"jsonrpc": "2.0", "id": message.get("id"), "result": {"ok": True}}


def test_stdio_transport_processes_message(monkeypatch):
    """A JSON-RPC line on stdin produces a response on stdout."""
    from praisonai_mcp.mcp_server.transports.stdio import StdioTransport

    init = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {},
        }
    )

    monkeypatch.setattr("sys.stdin", _FakeStdin((init + "\n").encode("utf-8")))
    out_buffer = io.BytesIO()

    class _FakeStdout:
        buffer = out_buffer

    monkeypatch.setattr("sys.stdout", _FakeStdout())

    server = _FakeServer()
    transport = StdioTransport(server)

    asyncio.run(asyncio.wait_for(transport.run(), timeout=5))

    assert server.received and server.received[0]["method"] == "initialize"
    out_buffer.seek(0)
    line = out_buffer.read().decode("utf-8").strip()
    response = json.loads(line)
    assert response["id"] == 1
    assert response["result"] == {"ok": True}


def test_stdio_transport_reports_parse_error(monkeypatch):
    """Invalid JSON yields a -32700 parse error on stdout."""
    from praisonai_mcp.mcp_server.transports.stdio import StdioTransport

    monkeypatch.setattr("sys.stdin", _FakeStdin(b"not-json\n"))
    out_buffer = io.BytesIO()

    class _FakeStdout:
        buffer = out_buffer

    monkeypatch.setattr("sys.stdout", _FakeStdout())

    transport = StdioTransport(_FakeServer())
    asyncio.run(asyncio.wait_for(transport.run(), timeout=5))

    out_buffer.seek(0)
    response = json.loads(out_buffer.read().decode("utf-8").strip())
    assert response["error"]["code"] == -32700


def test_stdio_transport_reports_invalid_utf8(monkeypatch):
    """Malformed UTF-8 yields a -32700 parse error instead of crashing."""
    from praisonai_mcp.mcp_server.transports.stdio import StdioTransport

    # 0xff is not a valid UTF-8 start byte.
    monkeypatch.setattr("sys.stdin", _FakeStdin(b"\xff\xfe\n"))
    out_buffer = io.BytesIO()

    class _FakeStdout:
        buffer = out_buffer

    monkeypatch.setattr("sys.stdout", _FakeStdout())

    transport = StdioTransport(_FakeServer())
    asyncio.run(asyncio.wait_for(transport.run(), timeout=5))

    out_buffer.seek(0)
    response = json.loads(out_buffer.read().decode("utf-8").strip())
    assert response["error"]["code"] == -32700
