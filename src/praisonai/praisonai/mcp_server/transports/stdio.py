"""
STDIO Transport for MCP Server

Implements the MCP STDIO transport protocol:
- JSON-RPC 2.0 messages over stdin/stdout
- Messages delimited by newlines
- Logs go to stderr only
"""

import asyncio
import json
import logging
import sys
from typing import TYPE_CHECKING

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
        
        # Use asyncio streams for non-blocking I/O
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        
        # Create writer for stdout
        write_transport, write_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(write_transport, write_protocol, reader, loop)
        
        try:
            while self._running:
                try:
                    # Read a line (JSON-RPC message)
                    line = await reader.readline()
                    if not line:
                        # EOF reached
                        break
                    
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue
                    
                    # Parse JSON-RPC message
                    try:
                        message = json.loads(line)
                    except json.JSONDecodeError as e:
                        logger.error(f"JSON parse error: {e}")
                        error_response = {
                            "jsonrpc": "2.0",
                            "id": None,
                            "error": {
                                "code": -32700,
                                "message": f"Parse error: {e}",
                            },
                        }
                        await self._write_message(writer, error_response)
                        continue
                    
                    # Handle message
                    response = await self.server.handle_message(message)
                    
                    # Write response if not a notification
                    if response is not None:
                        await self._write_message(writer, response)
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.exception(f"Error processing message: {e}")
                    
        finally:
            self._running = False
            writer.close()
            logger.info("MCP server stopped")
    
    async def _write_message(self, writer: asyncio.StreamWriter, message: dict) -> None:
        """Write a JSON-RPC message to stdout."""
        try:
            data = json.dumps(message) + "\n"
            writer.write(data.encode("utf-8"))
            await writer.drain()
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
