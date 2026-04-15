"""
A2A Client — lightweight client for calling A2A-compliant servers.

Uses aiohttp (core dependency) for HTTP.  Provides both async and sync APIs.
"""

import json
import uuid
from typing import Any, AsyncIterator, Dict, Optional

import aiohttp

from praisonaiagents.ui.a2a.types import AgentCard


class A2AClient:
    """
    Client for communicating with an A2A-compliant server.
    
    Usage::
    
        client = A2AClient("http://localhost:8000")
        card = await client.get_agent_card()
        result = await client.send_message("Hello!")
        await client.close()
    
    Or as an async context manager::
    
        async with A2AClient("http://localhost:8000") as client:
            card = await client.get_agent_card()
    """
    
    def __init__(
        self,
        base_url: str,
        auth_token: Optional[str] = None,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers: Dict[str, str] = {}
            if self.auth_token:
                headers["Authorization"] = f"Bearer {self.auth_token}"
            self._session = aiohttp.ClientSession(
                headers=headers, timeout=self.timeout,
            )
        return self._session
    
    async def close(self):
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, *exc):
        await self.close()
    
    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    
    async def get_agent_card(self) -> AgentCard:
        """Fetch the agent card from ``/.well-known/agent.json``."""
        session = await self._get_session()
        async with session.get(f"{self.base_url}/.well-known/agent.json") as resp:
            resp.raise_for_status()
            data = await resp.json()
            return AgentCard(**data)
    
    # ------------------------------------------------------------------
    # JSON-RPC helpers
    # ------------------------------------------------------------------
    
    async def _jsonrpc_call(
        self, method: str, params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a JSON-RPC 2.0 request and return the parsed response."""
        session = await self._get_session()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "id": str(uuid.uuid4()),
            "params": params or {},
        }
        async with session.post(
            f"{self.base_url}/a2a",
            json=payload,
            headers={"Content-Type": "application/json"},
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
    
    # ------------------------------------------------------------------
    # Message methods
    # ------------------------------------------------------------------
    
    async def send_message(
        self,
        text: str,
        context_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send a text message via ``message/send``.
        
        Returns the full JSON-RPC result (task dict).
        """
        msg_id = message_id or str(uuid.uuid4())
        message: Dict[str, Any] = {
            "messageId": msg_id,
            "role": "user",
            "parts": [{"text": text}],
        }
        if context_id:
            message["contextId"] = context_id
        
        return await self._jsonrpc_call("message/send", {"message": message})
    
    async def send_message_streaming(
        self,
        text: str,
        context_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Send a message via ``message/stream`` and yield SSE events.
        
        Yields parsed JSON dicts for each SSE ``data:`` line.
        """
        session = await self._get_session()
        msg_id = message_id or str(uuid.uuid4())
        message: Dict[str, Any] = {
            "messageId": msg_id,
            "role": "user",
            "parts": [{"text": text}],
        }
        if context_id:
            message["contextId"] = context_id
        
        payload = {
            "jsonrpc": "2.0",
            "method": "message/stream",
            "id": str(uuid.uuid4()),
            "params": {"message": message},
        }
        
        async with session.post(
            f"{self.base_url}/a2a",
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.content:
                decoded = line.decode("utf-8").strip()
                if decoded.startswith("data:"):
                    data_str = decoded[5:].strip()
                    if data_str:
                        try:
                            yield json.loads(data_str)
                        except json.JSONDecodeError:
                            pass
    
    # ------------------------------------------------------------------
    # Task methods
    # ------------------------------------------------------------------
    
    async def get_task(self, task_id: str) -> Dict[str, Any]:
        """Get a task by ID via ``tasks/get``."""
        return await self._jsonrpc_call("tasks/get", {"id": task_id})
    
    async def list_tasks(
        self, context_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """List tasks, optionally filtered by contextId."""
        params: Dict[str, Any] = {}
        if context_id:
            params["contextId"] = context_id
        return await self._jsonrpc_call("tasks/list", params)
    
    async def cancel_task(self, task_id: str) -> Dict[str, Any]:
        """Cancel a task by ID via ``tasks/cancel``."""
        return await self._jsonrpc_call("tasks/cancel", {"id": task_id})
    
    async def get_extended_card(self) -> Dict[str, Any]:
        """Fetch extended agent card via ``agent/getExtendedCard``."""
        return await self._jsonrpc_call("agent/getExtendedCard", {})
