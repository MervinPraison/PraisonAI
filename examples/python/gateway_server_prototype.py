"""
Prototype implementation of Gateway Server with backpressure and flow control.

This demonstrates how the bounded queues and slow consumer detection would be
implemented in the wrapper layer (praisonai package) using the configuration
from the core SDK (praisonaiagents).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# For the prototype, we'll define minimal config inline
# from praisonaiagents.gateway import GatewayConfig

@dataclass 
class SessionConfig:
    max_inbox: int = 256
    
@dataclass
class GatewayConfig:
    session_config: SessionConfig = field(default_factory=SessionConfig)
    max_buffered_bytes: int = 1024 * 1024  # 1MB default

logger = logging.getLogger(__name__)


@dataclass
class GatewaySession:
    """Gateway session with bounded inbox for backpressure."""
    
    _session_id: str
    _agent_id: str
    _client_id: Optional[str] = None
    _inbox: asyncio.Queue = field(default_factory=asyncio.Queue)
    _max_inbox: int = 256
    _is_executing: bool = False
    
    def setup_inbox(self, max_inbox: int = 256) -> None:
        """Set up the inbox with proper bounds."""
        self._max_inbox = max_inbox
        if max_inbox > 0:
            self._inbox = asyncio.Queue(maxsize=max_inbox)
        else:
            self._inbox = asyncio.Queue()  # Unbounded for backward compat if 0
    
    async def queue_message(self, message: str) -> bool:
        """Queue a user message with backpressure handling.
        
        Returns:
            True if message was queued, False if inbox is full.
        """
        if self._max_inbox > 0:
            # Bounded queue - check if full
            try:
                self._inbox.put_nowait(message)
                return True
            except asyncio.QueueFull:
                return False
        else:
            # Unbounded queue for backward compatibility
            await self._inbox.put(message)
            return True


class GatewayServer:
    """Gateway server with flow control."""
    
    def __init__(self, config: GatewayConfig):
        self.config = config
        self._sessions: Dict[str, GatewaySession] = {}
        self._clients: Dict[str, Any] = {}  # client_id -> WebSocket
        
    def create_session(self, session_id: str, agent_id: str, client_id: str) -> GatewaySession:
        """Create a new session with bounded inbox."""
        session = GatewaySession(
            _session_id=session_id,
            _agent_id=agent_id,
            _client_id=client_id,
        )
        # Set up inbox with configured bounds
        session.setup_inbox(self.config.session_config.max_inbox)
        self._sessions[session_id] = session
        return session
        
    async def handle_message(self, session: GatewaySession, message: str, client_id: str) -> str:
        """Handle incoming message with inbox overflow protection."""
        # Try to queue the message
        queued = await session.queue_message(message)
        if not queued:
            # Inbox is full, send error response
            await self._send_to_client(
                client_id,
                {
                    "type": "error",
                    "code": "inbox_full",
                    "message": "Message queue is full. Please wait for current messages to be processed."
                }
            )
            return "Inbox full - message rejected."
        
        # Start processing if not already running
        if not session._is_executing:
            session._is_executing = True
            asyncio.create_task(self._drain_session_queue(session, client_id))
            return "Processing started."
        
        return "Message queued."
    
    async def _drain_session_queue(self, session: GatewaySession, client_id: str) -> None:
        """Process all messages from the session's inbox queue."""
        try:
            while not session._inbox.empty():
                msg = await session._inbox.get()
                # Process message here (simplified for prototype)
                logger.info(f"Processing message for session {session._session_id}: {msg}")
                
                # Simulate processing delay
                await asyncio.sleep(0.1)
                
                # Send response to client (simplified)
                await self._send_to_client(
                    client_id,
                    {
                        "type": "response",
                        "message": f"Processed: {msg}"
                    }
                )
        except Exception as e:
            logger.error(f"Error processing queue for session {session._session_id}: {e}")
        finally:
            session._is_executing = False
    
    async def _send_to_client(self, client_id: str, data: Dict[str, Any]) -> None:
        """Send data to client with slow consumer detection."""
        ws = self._clients.get(client_id)
        if ws:
            try:
                # Check for slow consumer (buffered bytes)
                if self.config.max_buffered_bytes > 0:
                    # Try to get transport buffer size
                    transport = getattr(ws, 'transport', None) or getattr(ws, '_transport', None)
                    if transport and hasattr(transport, 'get_write_buffer_size'):
                        buffered_bytes = transport.get_write_buffer_size()
                        if buffered_bytes > self.config.max_buffered_bytes:
                            # Check if this is a droppable event type
                            event_type = data.get("type", "")
                            droppable_types = {"presence", "typing", "status"}
                            
                            if event_type in droppable_types:
                                # Drop the message for slow consumers
                                logger.warning(f"Dropping {event_type} event for slow consumer {client_id} (buffered: {buffered_bytes} bytes)")
                                return
                            else:
                                # Critical event - close the connection
                                logger.warning(f"Closing slow consumer {client_id} (buffered: {buffered_bytes} bytes > {self.config.max_buffered_bytes})")
                                await ws.close(code=1013, reason="slow consumer")
                                return
                
                # Send the message
                await ws.send_json(data)
            except Exception as e:
                logger.error(f"Error sending to client {client_id}: {e}", exc_info=True)


# Example usage demonstrating the flow control
async def demo():
    """Demonstrate the flow control implementation."""
    
    # Create config with bounded inbox and slow consumer detection
    config = GatewayConfig()
    config.session_config.max_inbox = 10  # Small inbox for demo
    config.max_buffered_bytes = 1024  # 1KB for demo
    
    # Create server and session
    server = GatewayServer(config)
    session = server.create_session("sess1", "agent1", "client1")
    
    # Simulate filling up the inbox
    print(f"Inbox max size: {session._inbox.maxsize}")
    
    # Fill the inbox
    for i in range(10):
        success = await session.queue_message(f"Message {i}")
        print(f"Queued message {i}: {success}")
    
    # Try to add one more - should fail
    success = await session.queue_message("Overflow message")
    print(f"Overflow message queued: {success}")
    
    # Process messages
    while not session._inbox.empty():
        msg = await session._inbox.get()
        print(f"Processing: {msg}")


if __name__ == "__main__":
    asyncio.run(demo())