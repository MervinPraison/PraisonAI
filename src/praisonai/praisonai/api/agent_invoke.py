"""
Agent Invoke API for n8n Integration

Provides an endpoint for n8n workflows to invoke PraisonAI agents,
enabling bidirectional n8n ↔ PraisonAI integration.
"""

from typing import Any, Dict, Optional, Union
import inspect
import logging

try:
    from fastapi import APIRouter, HTTPException, Depends, Header, Request
    from pydantic import BaseModel, Field
    FASTAPI_AVAILABLE = True
except ImportError:
    # Fallback for environments without FastAPI
    APIRouter = None
    HTTPException = None
    BaseModel = object
    Field = lambda *args, **kwargs: None
    Depends = lambda x: x
    Header = lambda *args, **kwargs: None
    Request = object
    FASTAPI_AVAILABLE = False

logger = logging.getLogger(__name__)

# Authentication
import os
import warnings

CALL_SERVER_TOKEN = os.getenv('CALL_SERVER_TOKEN')
_LOCALHOST_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})


def _call_auth_disabled() -> bool:
    return os.getenv('PRAISONAI_CALL_AUTH', '').lower() == 'disabled'


def _configured_bind_host() -> Optional[str]:
    """Server bind address from env only — never trust client Host headers."""
    return os.getenv('PRAISONAI_CALL_BIND_HOST')


async def verify_token(
    request: Request, 
    authorization: Optional[str] = Header(None)
) -> None:
    """Verify API token for authentication."""
    if not FASTAPI_AVAILABLE:
        return
    if _call_auth_disabled():
        bind_host = _configured_bind_host()
        if bind_host is None or bind_host not in _LOCALHOST_HOSTS:
            raise HTTPException(
                status_code=503,
                detail=(
                    "PRAISONAI_CALL_AUTH=disabled is only permitted for localhost binding; "
                    "set PRAISONAI_CALL_BIND_HOST to 127.0.0.1 when binding locally"
                ),
            )
        warnings.warn(
            "PRAISONAI_CALL_AUTH=disabled bypasses authentication; "
            "set CALL_SERVER_TOKEN for production use",
            DeprecationWarning,
            stacklevel=2,
        )
        return
    if not CALL_SERVER_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="CALL_SERVER_TOKEN is not configured. Set CALL_SERVER_TOKEN to enable authentication.",
        )
        
    token = None
    
    # Check Authorization header first (Bearer or Basic)
    if authorization:
        if authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
        elif authorization.startswith("Basic "):
            try:
                import base64
                decoded = base64.b64decode(authorization[6:]).decode("utf-8")
                if ":" in decoded:
                    token = decoded.split(":", 1)[1]  # Use password as token
                else:
                    token = decoded
            except Exception:
                pass
    
    # Check query param as fallback
    if not token:
        token = request.query_params.get("token")
    
    if token != CALL_SERVER_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

# Request/Response Models
if FASTAPI_AVAILABLE:
    class AgentInvokeRequest(BaseModel):
        """Request model for agent invocation."""
        message: str = Field(..., description="Message to send to the agent")
        session_id: Optional[str] = Field(None, description="Optional session ID for conversation continuity")
        agent_config: Optional[Dict[str, Any]] = Field(None, description="Optional agent configuration overrides")

    class AgentInvokeResponse(BaseModel):
        """Response model for agent invocation."""
        result: str = Field(..., description="Agent response")
        session_id: str = Field(..., description="Session ID used for this conversation")
        status: str = Field(default="success", description="Response status")
        metadata: Optional[Dict[str, Any]] = Field(None, description="Optional response metadata")

    class ErrorResponse(BaseModel):
        """Error response model."""
        error: str = Field(..., description="Error message")
        status: str = Field(default="error", description="Error status")
        code: Optional[str] = Field(None, description="Error code")
else:
    # Simple dict-based fallbacks
    class AgentInvokeRequest:
        def __init__(self, message: str, session_id: Optional[str] = None, agent_config: Optional[Dict[str, Any]] = None):
            self.message = message
            self.session_id = session_id
            self.agent_config = agent_config
    
    class AgentInvokeResponse:
        def __init__(self, result: str, session_id: str, status: str = "success", metadata: Optional[Dict[str, Any]] = None):
            self.result = result
            self.session_id = session_id
            self.status = status
            self.metadata = metadata
            
    class ErrorResponse:
        def __init__(self, error: str, status: str = "error", code: Optional[str] = None):
            self.error = error
            self.status = status
            self.code = code


# Agent Registry
_agent_registry: Dict[str, Any] = {}


def register_agent(agent_id: str, agent: Any) -> None:
    """Register an agent for invocation via API."""
    _agent_registry[agent_id] = agent
    logger.debug(f"Registered agent: {agent_id}")


def unregister_agent(agent_id: str) -> bool:
    """Unregister an agent."""
    if agent_id in _agent_registry:
        del _agent_registry[agent_id]
        logger.debug(f"Unregistered agent: {agent_id}")
        return True
    return False


def get_agent(agent_id: str) -> Optional[Any]:
    """Get a registered agent by ID."""
    return _agent_registry.get(agent_id)


def list_registered_agents() -> list:
    """List all registered agent IDs."""
    return list(_agent_registry.keys())


def _supports_session_isolation(agent: Any) -> bool:
    """Return True when ``agent`` can be safely cloned per session.

    Only real ``praisonaiagents`` ``Agent`` instances expose the per-session
    machinery (``_session_id`` binding, ``chat_history`` and a safe clone path).
    Plain mocks / lightweight callables do not (a bare ``Mock`` auto-vivifies
    every attribute), so we gate on the concrete class living in the
    ``praisonaiagents`` package and leave everything else on the shared
    instance to preserve backward compatibility.
    """
    module = type(agent).__module__ or ""
    if not module.startswith("praisonaiagents"):
        return False
    if not hasattr(agent, "_session_id"):
        return False
    if not hasattr(agent, "chat_history"):
        return False
    return callable(getattr(agent, "clone_for_channel", None))


def _clone_agent(agent: Any) -> Any:
    """Create an independent copy of a real ``Agent``.

    Prefers ``clone_for_channel`` (purpose-built for multi-channel isolation
    with fresh locks), falling back to ``deepcopy``.
    """
    clone_for_channel = getattr(agent, "clone_for_channel", None)
    if callable(clone_for_channel):
        return clone_for_channel()
    import copy as _copy

    return _copy.deepcopy(agent)


def resolve_session_agent(agent_id: str, session_id: Optional[str]) -> Any:
    """Resolve an isolated, session-scoped agent for a single request.

    The registry holds a *template* agent, not a live conversation. Every
    request gets its own clone so concurrent callers never share mutable
    ``chat_history``:

    - With a ``session_id``: the clone is bound to that session so its history
      is loaded from (and persisted to) the shared, file-locked session store —
      giving continuity across requests and isolation between sessions.
    - Without a ``session_id``: the clone is ephemeral (no session binding), so
      no global state is mutated.

    Agents that don't support cloning/session binding (e.g. plain mocks) fall
    back to the shared registry instance for backward compatibility.
    """
    template = get_agent(agent_id)
    if template is None:
        return None

    if not _supports_session_isolation(template):
        return template

    try:
        agent = _clone_agent(template)
    except Exception as e:  # pragma: no cover - defensive fallback
        logger.warning(
            f"Failed to clone agent '{agent_id}' for session isolation: {e}; "
            "falling back to shared instance"
        )
        return template

    # Reset per-request conversation state so the clone starts clean and
    # (re)loads the requested session's history lazily on first chat.
    try:
        agent.chat_history = []
    except Exception:
        pass
    if hasattr(agent, "_session_store_initialized"):
        agent._session_store_initialized = False
    if session_id:
        agent._session_id = session_id
        if hasattr(agent, "_history_session_id"):
            agent._history_session_id = session_id
    else:
        agent._session_id = None
        if hasattr(agent, "_history_session_id"):
            agent._history_session_id = None
    return agent


def _supports_async_start(agent: Any) -> bool:
    """Return True if agent.astart is a coroutine function."""
    astart = getattr(agent, "astart", None)
    return inspect.iscoroutinefunction(astart)


def _supports_sync_start(agent: Any) -> bool:
    """Return True when agent exposes a callable sync start method."""
    start = getattr(agent, "start", None)
    return callable(start)


# FastAPI Router (if FastAPI is available)
if FASTAPI_AVAILABLE and APIRouter is not None:
    router = APIRouter(prefix="/api/v1", tags=["agents"])

    @router.post("/agents/{agent_id}/invoke")
    async def invoke_agent(
        agent_id: str,
        request: AgentInvokeRequest,
        _: None = Depends(verify_token)
    ) -> Union[AgentInvokeResponse, ErrorResponse]:
        """
        Invoke a PraisonAI agent with a message.
        
        This endpoint is designed for n8n workflows to call PraisonAI agents,
        enabling bidirectional integration between n8n and PraisonAI.
        
        Args:
            agent_id: The ID of the agent to invoke
            request: The invocation request containing message and optional session_id
            
        Returns:
            Agent response with result and session information
            
        Raises:
            HTTPException: If agent not found or execution fails
            
        Example n8n HTTP Request Node configuration:
        ```json
        {
          "method": "POST",
          "url": "http://praisonai:8000/api/v1/agents/my-agent/invoke",
          "body": {
            "message": "{{ $json.user_input }}",
            "session_id": "{{ $json.session_id }}"
          }
        }
        ```
        """
        # Resolve a per-session isolated agent view so concurrent callers never
        # share mutable chat_history. A provided session_id gives continuity via
        # the shared session store; its absence yields an ephemeral conversation.
        agent = resolve_session_agent(agent_id, request.session_id)
        if not agent:
            logger.error(f"Agent not found: {agent_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_id}' not found"
            )
        
        try:
            # Session ID echoed back to the caller
            session_id = request.session_id or "default"
            
            # Apply agent config overrides if provided
            if request.agent_config:
                # This would depend on the specific agent implementation
                # For now, we'll just log it
                logger.debug(f"Agent config overrides provided: {request.agent_config}")
            
            # Invoke agent (handle both sync and async agents)
            if _supports_async_start(agent):
                # Async agent
                result = await agent.astart(request.message)
            elif _supports_sync_start(agent):
                # Sync agent - run in thread pool to avoid blocking the event loop
                import asyncio
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, agent.start, request.message)
            else:
                raise AttributeError(f"Agent {agent_id} must provide start() or async astart()")
            
            logger.info(f"Agent {agent_id} invoked successfully")
            
            return AgentInvokeResponse(
                result=str(result),
                session_id=session_id,
                status="success",
                metadata={
                    "agent_id": agent_id,
                    "message_length": len(request.message),
                    "response_length": len(str(result))
                }
            )
            
        except Exception as e:
            logger.error(f"Agent {agent_id} invocation failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Agent execution failed: {str(e)}"
            )

    @router.get("/agents")
    async def list_agents(_: None = Depends(verify_token)) -> Dict[str, Any]:
        """
        List all registered agents.
        
        Returns:
            Dictionary containing list of available agents
        """
        agents = list_registered_agents()
        return {
            "agents": agents,
            "count": len(agents),
            "status": "success"
        }

    @router.post("/agents/{agent_id}/register")
    async def register_agent_endpoint(agent_id: str, _: None = Depends(verify_token)) -> Dict[str, Any]:
        """
        Register an agent for API access.
        
        Note: This is a placeholder endpoint. In practice, agents would be
        registered programmatically when they are created.
        """
        # In a real implementation, this might load an agent from a configuration
        # or database. For now, return information about registration.
        return {
            "message": f"Agent registration endpoint for '{agent_id}'",
            "note": "Agents are typically registered programmatically",
            "status": "info"
        }

    @router.delete("/agents/{agent_id}")
    async def unregister_agent_endpoint(agent_id: str, _: None = Depends(verify_token)) -> Dict[str, Any]:
        """
        Unregister an agent from API access.
        """
        success = unregister_agent(agent_id)
        if success:
            return {
                "message": f"Agent '{agent_id}' unregistered successfully",
                "status": "success"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_id}' not found"
            )

    @router.get("/agents/{agent_id}")
    async def get_agent_info(agent_id: str, _: None = Depends(verify_token)) -> Dict[str, Any]:
        """
        Get information about a registered agent.
        """
        agent = get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_id}' not found"
            )
        
        # Extract basic agent information
        info = {
            "agent_id": agent_id,
            "status": "registered",
            "type": type(agent).__name__,
        }
        
        # Add agent-specific information if available
        if hasattr(agent, 'name'):
            info["name"] = agent.name
        if hasattr(agent, 'instructions'):
            info["instructions"] = agent.instructions[:200] + "..." if len(agent.instructions) > 200 else agent.instructions
        if hasattr(agent, 'tools') and agent.tools:
            info["tools"] = [getattr(tool, 'name', str(tool)) for tool in agent.tools[:5]]  # First 5 tools
            if len(agent.tools) > 5:
                info["tools"].append(f"... and {len(agent.tools) - 5} more")
        
        return info


# Standalone function for non-FastAPI environments
async def invoke_agent_standalone(
    agent_id: str,
    message: str,
    session_id: Optional[str] = None,
    agent_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Standalone function to invoke an agent without FastAPI.
    
    This can be used in environments where FastAPI is not available
    or when integrating with other web frameworks.
    """
    if get_agent(agent_id) is None:
        return {
            "error": f"Agent '{agent_id}' not found",
            "status": "error",
            "available_agents": list_registered_agents()
        }

    # Per-session isolated agent view (see resolve_session_agent).
    agent = resolve_session_agent(agent_id, session_id)

    try:
        # Apply config if provided
        if agent_config:
            logger.debug(f"Agent config provided: {agent_config}")
        
        # Invoke agent
        session_id = session_id or "default"
        
        if _supports_async_start(agent):
            result = await agent.astart(message)
        elif _supports_sync_start(agent):
            # Sync agent - run in thread pool to avoid blocking the event loop
            import asyncio
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, agent.start, message)
        else:
            raise AttributeError(f"Agent {agent_id} must provide start() or async astart()")
        
        return {
            "result": str(result),
            "session_id": session_id,
            "status": "success",
            "agent_id": agent_id
        }
        
    except Exception as e:
        logger.error(f"Agent {agent_id} invocation failed: {e}")
        return {
            "error": str(e),
            "status": "error",
            "agent_id": agent_id
        }


# Example usage and helper functions
def create_example_agents():
    """Create some example agents for testing."""
    try:
        from praisonaiagents import Agent
        
        # Create a simple assistant agent
        assistant = Agent(
            name="assistant",
            instructions="You are a helpful assistant that provides concise, helpful responses."
        )
        register_agent("assistant", assistant)
        
        # Create a coding agent
        coder = Agent(
            name="coder",
            instructions="You are a coding assistant that helps with programming questions and code review."
        )
        register_agent("coder", coder)
        
        logger.info("Example agents created and registered")
        
    except ImportError:
        logger.warning("praisonaiagents not available, skipping example agents")


# Auto-registration helper
def auto_register_agents_from_config(config_file: Optional[str] = None):
    """
    Auto-register agents from a configuration file.
    
    This is a placeholder for a more complete implementation that
    could load agents from YAML, JSON, or other configuration formats.
    """
    logger.info(f"Auto-registering agents from config: {config_file or 'default'}")
    # In a real implementation, this would parse the config and create agents
    create_example_agents()


if __name__ == "__main__":
    # For testing without FastAPI
    import asyncio
    
    async def test_standalone():
        """Test the standalone functionality."""
        create_example_agents()
        
        # Test invocation
        result = await invoke_agent_standalone(
            agent_id="assistant",
            message="Hello, can you help me with n8n integration?"
        )
        print(f"Agent response: {result}")
    
    # asyncio.run(test_standalone())
    print("Agent Invoke API module loaded successfully")
