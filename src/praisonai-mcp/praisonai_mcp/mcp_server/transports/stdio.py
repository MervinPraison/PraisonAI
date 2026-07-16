"""
STDIO Transport for MCP Server

Implements the MCP STDIO transport protocol:
- JSON-RPC 2.0 messages over stdin/stdout
- Messages delimited by newlines
- Logs go to stderr only

Reads stdin in a daemon thread and hands lines to the asyncio loop via
``run_in_executor``. This avoids ``loop.connect_read_pipe(sys.stdin)`` which
crashes on Windows ``ProactorEventLoop`` + Python 3.13 with
``OSError: [WinError 6] The handle is invalid`` when an MCP client (Cursor,
Claude Desktop, ...) spawns the server with redirected pipe handles.
"""

import asyncio
import json
import logging
import queue
import sys
import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..server import MCPServer

logger = logging.getLogger(__name__)


class StdioTransport:
    """
    STDIO transport for MCP server.
    
    Reads JSON-RPC messages from stdin and writes responses to stdout.
    All logging goes to stderr to avoid corrupting the protocol stream.
    """
    
    def __init__(self, server: "MCPServer"):
        """
        Initialize STDIO transport.
        
        Args:
            server: MCPServer instance to handle messages
        """
        self.server = server
        self._running = False
    
    async def run(self) -> None:
        """Run the STDIO transport loop."""
        self._running = True
        
        # Configure logging to stderr only
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)
        
        logger.info(f"MCP server '{self.server.name}' starting on STDIO transport")
        
        loop = asyncio.get_running_loop()
        line_queue: "queue.Queue[Optional[bytes]]" = queue.Queue()

        def _blocking_reader() -> None:
            """Read stdin in a dedicated thread; ``None`` signals EOF."""
            try:
                for raw in sys.stdin.buffer:
                    if not self._running:
                        break
                    line_queue.put(raw)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(f"Error reading stdin: {exc}")
            finally:
                line_queue.put(None)

        reader_thread = threading.Thread(
            target=_blocking_reader, name="mcp-stdio-reader", daemon=True
        )
        reader_thread.start()
        
        try:
            while self._running:
                raw = await loop.run_in_executor(None, line_queue.get)
                if raw is None:
                    # EOF reached
                    break

                line = raw.decode("utf-8").strip()
                if not line:
                    continue

                # Parse JSON-RPC message
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.error(f"JSON parse error: {e}")
                    self._write_message(
                        {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {
                                "code": -32700,
                                "message": f"Parse error: {e}",
                            },
                        }
                    )
                    continue

                # Handle message
                try:
                    response = await self.server.handle_message(message)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception(f"Error processing message: {e}")
                    continue

                # Write response if not a notification
                if response is not None:
                    self._write_message(response)
        finally:
            self._running = False
            logger.info("MCP server stopped")
    
    def _write_message(self, message: dict) -> None:
        """Write a JSON-RPC message to stdout."""
        try:
            data = (json.dumps(message) + "\n").encode("utf-8")
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
        except Exception as e:
            logger.error(f"Error writing message: {e}")
    
    def stop(self) -> None:
        """Stop the transport."""
        self._running = False


def run_stdio_server(server: "MCPServer") -> None:
    """
    Convenience function to run a server with STDIO transport.
    
    Args:
        server: MCPServer instance
    """
    transport = StdioTransport(server)
    asyncio.run(transport.run())
