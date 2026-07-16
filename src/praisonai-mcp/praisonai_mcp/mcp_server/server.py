"""
MCP Server Implementation

Core MCP server that handles JSON-RPC messages and routes them to appropriate handlers.
Supports both STDIO and HTTP Stream transports.
"""

import asyncio
import json
import logging
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional

from .registry import (
    get_tool_registry,
    get_resource_registry,
    get_prompt_registry,
    MCPToolRegistry,
    MCPResourceRegistry,
    MCPPromptRegistry,
)

logger = logging.getLogger(__name__)

# MCP Protocol Constants (Updated to 2025-11-25 spec)
PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_VERSIONS = ["2025-11-25", "2025-03-26", "2024-11-05"]

# JSON-RPC Error Codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# MCP-specific: insufficient scope (least-privilege enforcement)
INSUFFICIENT_SCOPE = -32001

# Sentinel used when scope enforcement should be skipped entirely (no auth
# configured). Distinct from an empty granted-scope list, which means
# "authenticated but granted nothing".
SCOPE_ENFORCEMENT_DISABLED = None


class MCPServer:
    """
    MCP Server that exposes PraisonAI capabilities.
    
    Supports:
    - STDIO transport (for Claude Desktop, Cursor, etc.)
    - HTTP Stream transport (MCP 2025-11-25 spec)
    
    Example:
        server = MCPServer(name="praisonai")
        server.run(transport="stdio")
    """
    
    def __init__(
        self,
        name: str = "praisonai",
        version: str = "1.0.0",
        tool_registry: Optional[MCPToolRegistry] = None,
        resource_registry: Optional[MCPResourceRegistry] = None,
        prompt_registry: Optional[MCPPromptRegistry] = None,
        instructions: Optional[str] = None,
    ):
        """
        Initialize MCP server.
        
        Args:
            name: Server name
            version: Server version
            tool_registry: Custom tool registry (uses global if None)
            resource_registry: Custom resource registry (uses global if None)
            prompt_registry: Custom prompt registry (uses global if None)
            instructions: Optional instructions for clients
        """
        self.name = name
        self.version = version
        self.instructions = instructions
        
        self._tool_registry = tool_registry or get_tool_registry()
        self._resource_registry = resource_registry or get_resource_registry()
        self._prompt_registry = prompt_registry or get_prompt_registry()
        
        self._initialized = False
        self._client_info: Optional[Dict[str, Any]] = None
        self._protocol_version: str = PROTOCOL_VERSION
        
        # Cancellation support
        self._active_requests: Dict[str, asyncio.Task] = {}
        # Ordered so overflow eviction drops the *oldest* id (FIFO), never the
        # id that was just added (a plain set.pop() removes an arbitrary element
        # and could silently forget a cancellation that had just arrived).
        self._cancelled_requests: "OrderedDict[str, None]" = OrderedDict()
        self._max_cancelled_requests = 10000
        
        # Progress notification callback
        self._progress_callback: Optional[Callable] = None

        # Scope enforcement (least-privilege). Lazily created on first use so
        # servers that never enforce scopes pay no import cost.
        self._scope_manager = None
        
        # Method handlers
        self._handlers: Dict[str, Callable] = {
            "initialize": self._handle_initialize,
            "ping": self._handle_ping,
            "tools/list": self._handle_tools_list,
            "tools/call": self._handle_tools_call,
            "tools/search": self._handle_tools_search,  # Extension method
            "resources/list": self._handle_resources_list,
            "resources/read": self._handle_resources_read,
            "prompts/list": self._handle_prompts_list,
            "prompts/get": self._handle_prompts_get,
            "logging/setLevel": self._handle_set_log_level,
        }
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get server capabilities per MCP 2025-11-25 spec."""
        return {
            "tools": {
                "listChanged": True,
            },
            "resources": {
                "subscribe": False,
                "listChanged": True,
            },
            "prompts": {
                "listChanged": True,
            },
            "logging": {},
        }
    
    def set_progress_callback(self, callback: Callable) -> None:
        """Set callback for progress notifications."""
        self._progress_callback = callback
    
    async def send_progress(self, progress_token: str, progress: float, total: Optional[float] = None) -> None:
        """Send progress notification for long-running operations."""
        if self._progress_callback:
            notification = {
                "jsonrpc": "2.0",
                "method": "notifications/progress",
                "params": {
                    "progressToken": progress_token,
                    "progress": progress,
                }
            }
            if total is not None:
                notification["params"]["total"] = total
            await self._progress_callback(notification)
    
    def is_cancelled(self, request_id: str) -> bool:
        """Check if a request has been cancelled."""
        return request_id in self._cancelled_requests
    
    def _enforce_scopes(
        self,
        method: str,
        granted_scopes: Optional[list],
    ) -> Optional[Dict[str, Any]]:
        """Check per-method scope requirements against the caller's grants.

        Args:
            method: JSON-RPC method being invoked
            granted_scopes: Scopes granted to the caller, or None to disable
                enforcement entirely (no auth configured).

        Returns:
            A JSON-RPC error dict (without id) if the requirement is not met,
            otherwise None. The returned error's ``data`` carries the scope
            challenge, including a ``www_authenticate`` string the transport can
            surface as a WWW-Authenticate header.
        """
        if granted_scopes is SCOPE_ENFORCEMENT_DISABLED:
            return None

        # Wildcard grant satisfies every requirement (admin / single-key mode).
        if "*" in granted_scopes:
            return None

        from .auth.scopes import get_operation_scopes, ScopeManager

        requirement = get_operation_scopes(method)
        if requirement is None:
            return None

        if self._scope_manager is None:
            self._scope_manager = ScopeManager()

        ok, challenge = requirement.check(granted_scopes or [], self._scope_manager)
        if ok:
            return None

        data = challenge.to_dict()
        data["www_authenticate"] = challenge.to_www_authenticate(realm=self.name)
        return {"code": INSUFFICIENT_SCOPE, "message": "insufficient_scope", "data": data}

    async def handle_message(
        self,
        message: Dict[str, Any],
        granted_scopes: Optional[list] = SCOPE_ENFORCEMENT_DISABLED,
    ) -> Optional[Dict[str, Any]]:
        """
        Handle an incoming JSON-RPC message.
        
        Args:
            message: JSON-RPC message
            granted_scopes: Scopes granted to the caller. ``None`` (default)
                disables scope enforcement for backward compatibility; a list
                (possibly empty) enables per-method enforcement via
                ``OPERATION_SCOPES``.
            
        Returns:
            Response message or None for notifications
        """
        # Validate JSON-RPC format
        if message.get("jsonrpc") != "2.0":
            return self._error_response(None, INVALID_REQUEST, "Invalid JSON-RPC version")
        
        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")
        
        # Notifications don't have an id
        is_notification = msg_id is None
        
        # Handle initialized notification
        if method == "notifications/initialized":
            self._initialized = True
            logger.debug("Client sent initialized notification")
            return None
        
        # Handle cancellation notification
        if method == "notifications/cancelled":
            request_id = params.get("requestId")
            if request_id:
                rid = str(request_id)
                self._cancelled_requests[rid] = None
                while len(self._cancelled_requests) > self._max_cancelled_requests:
                    self._cancelled_requests.popitem(last=False)  # drop oldest
                # Cancel the in-flight task if one is registered. Once we have
                # acted on the cancellation we drop the marker so a later request
                # that reuses the same JSON-RPC id is not spuriously cancelled by
                # this stale entry.
                task = self._active_requests.get(rid)
                if task is not None:
                    task.cancel()
                    self._cancelled_requests.pop(rid, None)
                    logger.debug(f"Cancelled request: {request_id}")
            return None
        
        # Check if method exists
        handler = self._handlers.get(method)
        if handler is None:
            if is_notification:
                return None
            return self._error_response(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")
        
        # Enforce per-method scopes (least-privilege). No-op when enforcement is
        # disabled (granted_scopes is None) or the method has no scope mapping.
        scope_error = self._enforce_scopes(method, granted_scopes)
        if scope_error is not None:
            if is_notification:
                return None
            return self._error_response(
                msg_id, scope_error["code"], scope_error["message"], data=scope_error["data"]
            )
        
        # Execute handler. Id-bearing requests run as a registered task so an
        # incoming ``notifications/cancelled`` can actually cancel the in-flight
        # work (a plain ``await handler(...)`` leaves nothing to cancel).
        try:
            if not is_notification:
                rid = str(msg_id)
                task = asyncio.ensure_future(handler(params))
                self._active_requests[rid] = task
                try:
                    # Honour a cancellation that arrived before we registered,
                    # then consume the marker so it cannot cancel a *future*
                    # request that reuses this id. (Stored values are ``None``,
                    # so test membership rather than the popped value.)
                    if rid in self._cancelled_requests:
                        self._cancelled_requests.pop(rid, None)
                        task.cancel()
                    result = await task
                finally:
                    # Only remove *our* registration: a concurrent client that
                    # reused this id may have already replaced the entry with its
                    # own task, which must not be evicted by our cleanup.
                    if self._active_requests.get(rid) is task:
                        self._active_requests.pop(rid, None)
                return self._success_response(msg_id, result)
            await handler(params)
            return None
        except asyncio.CancelledError:
            logger.debug(f"Request cancelled: {method}")
            if is_notification:
                return None
            return self._error_response(msg_id, INTERNAL_ERROR, "Request cancelled")
        except Exception as e:
            logger.exception(f"Error handling {method}")
            if is_notification:
                return None
            return self._error_response(msg_id, INTERNAL_ERROR, str(e))
    
    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        self._client_info = params.get("clientInfo")
        client_version = params.get("protocolVersion", PROTOCOL_VERSION)
        
        # Negotiate protocol version
        if client_version in SUPPORTED_VERSIONS:
            self._protocol_version = client_version
        else:
            self._protocol_version = PROTOCOL_VERSION
        
        logger.info(f"Client initialized: {self._client_info}, protocol: {self._protocol_version}")
        
        result = {
            "protocolVersion": self._protocol_version,
            "capabilities": self.get_capabilities(),
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
        }
        
        if self.instructions:
            result["instructions"] = self.instructions
        
        return result
    
    async def _handle_ping(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle ping request."""
        return {}
    
    async def _handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request with pagination per MCP 2025-11-25 spec."""
        cursor = params.get("cursor")
        
        try:
            tools, next_cursor = self._tool_registry.list_paginated(cursor=cursor)
            result = {"tools": tools}
            if next_cursor:
                result["nextCursor"] = next_cursor
            return result
        except ValueError as e:
            # Invalid cursor - return JSON-RPC error
            raise ValueError(f"Invalid cursor: {e}")
    
    async def _handle_tools_search(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle tools/search request (extension method, not in MCP spec).
        
        Provides server-side search/filtering of tools.
        
        Args in params:
            query: Text to search in name, description, tags
            category: Filter by category
            tags: Filter by tags (any match)
            readOnly: Filter by readOnlyHint
            cursor: Pagination cursor
        """
        query = params.get("query")
        category = params.get("category")
        tags = params.get("tags")
        read_only = params.get("readOnly")
        cursor = params.get("cursor")
        
        try:
            tools, next_cursor, total = self._tool_registry.search(
                query=query,
                category=category,
                tags=tags,
                read_only=read_only,
                cursor=cursor,
            )
            result = {
                "tools": tools,
                "total": total,
            }
            if next_cursor:
                result["nextCursor"] = next_cursor
            return result
        except ValueError as e:
            raise ValueError(f"Search error: {e}")
    
    async def _handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            raise ValueError("Tool name required")
        
        tool = self._tool_registry.get(tool_name)
        if tool is None:
            raise ValueError(f"Tool not found: {tool_name}")
        
        # Execute tool
        try:
            if asyncio.iscoroutinefunction(tool.handler):
                result = await tool.handler(**arguments)
            else:
                result = tool.handler(**arguments)
            
            # Format result as MCP content
            if isinstance(result, str):
                content = [{"type": "text", "text": result}]
            elif isinstance(result, dict):
                content = [{"type": "text", "text": json.dumps(result, indent=2)}]
            elif isinstance(result, list):
                content = [{"type": "text", "text": json.dumps(result, indent=2)}]
            else:
                content = [{"type": "text", "text": str(result)}]
            
            return {"content": content, "isError": False}
        except Exception as e:
            logger.exception(f"Tool execution error: {tool_name}")
            return {
                "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                "isError": True,
            }
    
    async def _handle_resources_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/list request with pagination per MCP 2025-11-25 spec."""
        cursor = params.get("cursor")
        
        try:
            resources, next_cursor = self._resource_registry.list_paginated(cursor=cursor)
            result = {"resources": resources}
            if next_cursor:
                result["nextCursor"] = next_cursor
            return result
        except ValueError as e:
            raise ValueError(f"Invalid cursor: {e}")
    
    async def _handle_resources_read(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/read request."""
        uri = params.get("uri")
        
        if not uri:
            raise ValueError("Resource URI required")
        
        resource = self._resource_registry.get(uri)
        if resource is None:
            raise ValueError(f"Resource not found: {uri}")
        
        # Execute resource handler
        try:
            if asyncio.iscoroutinefunction(resource.handler):
                result = await resource.handler()
            else:
                result = resource.handler()
            
            # Format result
            if isinstance(result, str):
                content = [{"uri": uri, "mimeType": resource.mime_type, "text": result}]
            elif isinstance(result, dict):
                content = [{"uri": uri, "mimeType": "application/json", "text": json.dumps(result)}]
            else:
                content = [{"uri": uri, "mimeType": resource.mime_type, "text": str(result)}]
            
            return {"contents": content}
        except Exception:
            logger.exception(f"Resource read error: {uri}")
            raise
    
    async def _handle_prompts_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle prompts/list request with pagination per MCP 2025-11-25 spec."""
        cursor = params.get("cursor")
        
        try:
            prompts, next_cursor = self._prompt_registry.list_paginated(cursor=cursor)
            result = {"prompts": prompts}
            if next_cursor:
                result["nextCursor"] = next_cursor
            return result
        except ValueError as e:
            raise ValueError(f"Invalid cursor: {e}")
    
    async def _handle_prompts_get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle prompts/get request."""
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not prompt_name:
            raise ValueError("Prompt name required")
        
        prompt = self._prompt_registry.get(prompt_name)
        if prompt is None:
            raise ValueError(f"Prompt not found: {prompt_name}")
        
        # Execute prompt handler
        try:
            if asyncio.iscoroutinefunction(prompt.handler):
                result = await prompt.handler(**arguments)
            else:
                result = prompt.handler(**arguments)
            
            # Format result as messages
            if isinstance(result, str):
                messages = [{"role": "user", "content": {"type": "text", "text": result}}]
            elif isinstance(result, list):
                messages = result
            else:
                messages = [{"role": "user", "content": {"type": "text", "text": str(result)}}]
            
            return {"messages": messages}
        except Exception:
            logger.exception(f"Prompt get error: {prompt_name}")
            raise
    
    async def _handle_set_log_level(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle logging/setLevel request per MCP spec (per-server scope only)."""
        level = params.get("level")
        if not isinstance(level, str):
            raise ValueError("`level` must be a string")
        level_map = {
            "debug": logging.DEBUG,
            "info": logging.INFO,
            "notice": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
            "alert": logging.CRITICAL,
            "emergency": logging.CRITICAL,
        }
        if level.lower() not in level_map:
            raise ValueError(f"Unknown log level: {level!r}")
        # Scope the change to the MCP-server package logger tree
        # (``praisonai_mcp.mcp_server`` — the parent of the loggers this module
        # and its siblings actually emit through), never the process root. The
        # namespace is derived from ``__name__`` so it tracks the package the
        # server is actually running under (post-C12 extraction) rather than a
        # hard-coded legacy string. This honours the client's request for the
        # server's own log output while leaving unrelated audit /
        # injection-defense telemetry in the host process untouched.
        server_logger_root = __name__.rsplit(".", 1)[0]
        logging.getLogger(server_logger_root).setLevel(level_map[level.lower()])
        return {}
    
    def _success_response(self, msg_id: Any, result: Any) -> Dict[str, Any]:
        """Create a success response."""
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result,
        }
    
    def _error_response(self, msg_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
        """Create an error response."""
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": error,
        }
    
    def run(self, transport: str = "stdio", **kwargs) -> None:
        """
        Run the MCP server.
        
        Args:
            transport: Transport type ("stdio" or "http-stream")
            **kwargs: Transport-specific options
        """
        if transport == "stdio":
            self.run_stdio()
        elif transport == "http-stream":
            self.run_http_stream(**kwargs)
        else:
            raise ValueError(f"Unknown transport: {transport}")
    
    def run_stdio(self) -> None:
        """Run server with STDIO transport."""
        from .transports.stdio import StdioTransport
        
        transport = StdioTransport(self)
        asyncio.run(transport.run())
    
    def run_http_stream(
        self,
        host: str = "127.0.0.1",
        port: int = 8080,
        endpoint: str = "/mcp",
        **kwargs,
    ) -> None:
        """
        Run server with HTTP Stream transport.
        
        Args:
            host: Server host
            port: Server port
            endpoint: MCP endpoint path
        """
        from .transports.http_stream import HTTPStreamTransport
        
        transport = HTTPStreamTransport(
            server=self,
            host=host,
            port=port,
            endpoint=endpoint,
            **kwargs,
        )
        transport.run()
