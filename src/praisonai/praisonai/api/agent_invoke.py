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

_LOCALHOST_HOSTS = frozenset({'127.0.0.1', 'localhost', '::1'})


def _call_server_token() -> Optional[str]:
    """Live-read the shared server token from the environment.

    The environment is the single source of truth; capturing it at import time
    broke any host that mounts this router without going through
    ``praisonai.api.call.main()`` (AgentOS, ``serve``, tests, embedders) and
    made a late-loaded ``.env`` or runtime rotation impossible. Reading here —
    like ``_call_auth_disabled`` / ``_configured_bind_host`` already do — makes
    every request observe the current value.
    """
    return os.getenv('CALL_SERVER_TOKEN')


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
    expected = _call_server_token()
    if not expected:
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
    
    # Constant-time comparison to avoid a token-recovery timing side channel.
    import hmac
    if not token or not hmac.compare_digest(token, expected):
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
import threading


class AgentRegistry:
    """Thread-safe registry of agents scoped to an embedding/tenant.

    Encapsulates the previously module-global dict so multiple ``AgentOS`` /
    ``praisonai serve`` gateways sharing one interpreter can each hold an
    isolated registry, and so concurrent unregisters are race-free.
    """

    def __init__(self) -> None:
        self._agents: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def register(self, agent_id: str, agent: Any) -> None:
        with self._lock:
            self._agents[agent_id] = agent
        logger.debug(f"Registered agent: {agent_id}")

    def unregister(self, agent_id: str) -> bool:
        # Atomic under the lock: test membership and pop together so a concurrent
        # unregister can't race between the check and the delete, while still
        # reporting removal correctly even when the stored value is falsy/None.
        _MISSING = object()
        with self._lock:
            removed = self._agents.pop(agent_id, _MISSING) is not _MISSING
        if removed:
            logger.debug(f"Unregistered agent: {agent_id}")
        return removed

    def get(self, agent_id: str) -> Optional[Any]:
        with self._lock:
            return self._agents.get(agent_id)

    def list(self) -> list:
        with self._lock:
            return list(self._agents.keys())


_default_registry = AgentRegistry()


def _registry_dependency() -> AgentRegistry:
    """Which ``AgentRegistry`` serves this request?

    Returns the process-default registry by default, but is overridable via
    ``app.dependency_overrides[_registry_dependency] = ...`` so an ``AgentOS`` /
    ``serve`` host can bind its own registry per app instance and get real
    per-tenant isolation through the router (not just the free functions).
    """
    return _default_registry


def register_agent(agent_id: str, agent: Any,
                   *, registry: Optional[AgentRegistry] = None) -> None:
    """Register an agent for invocation via API."""
    (registry or _default_registry).register(agent_id, agent)


def unregister_agent(agent_id: str,
                     *, registry: Optional[AgentRegistry] = None) -> bool:
    """Unregister an agent."""
    return (registry or _default_registry).unregister(agent_id)


def get_agent(agent_id: str,
              *, registry: Optional[AgentRegistry] = None) -> Optional[Any]:
    """Get a registered agent by ID."""
    return (registry or _default_registry).get(agent_id)


def list_registered_agents(*, registry: Optional[AgentRegistry] = None) -> list:
    """List all registered agent IDs."""
    return (registry or _default_registry).list()


def _is_real_agent(agent: Any) -> bool:
    """Return True when ``agent`` is a genuine ``praisonaiagents`` ``Agent``.

    Uses ``isinstance`` against the real ``Agent`` class so **subclasses defined
    in application code** are recognised too (they inherit the per-session
    machinery and ``clone_for_channel``). Plain mocks / lightweight callables are
    not ``Agent`` instances, so they fall back to the shared instance for
    backward compatibility. If ``praisonaiagents`` cannot be imported we treat
    the object as non-isolatable.
    """
    try:
        from praisonaiagents import Agent
    except Exception:
        return False
    return isinstance(agent, Agent)


def _supports_session_isolation(agent: Any) -> bool:
    """Return True when ``agent`` can be safely cloned per session.

    A real ``Agent`` (or any subclass) exposes the per-session machinery
    (``_session_id`` binding, ``chat_history`` and a safe clone path). Plain
    mocks / lightweight callables do not, so they stay on the shared instance to
    preserve backward compatibility.
    """
    if not _is_real_agent(agent):
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


def resolve_session_agent(agent_id: str, session_id: Optional[str],
                          *, registry: Optional[AgentRegistry] = None) -> Any:
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
    template = get_agent(agent_id, registry=registry)
    if template is None:
        return None

    if not _supports_session_isolation(template):
        return template

    try:
        agent = _clone_agent(template)
    except Exception as e:
        # A clone failure must never silently fall back to the shared template:
        # doing so would leak one session's chat_history into another. Fail the
        # request instead so isolation is guaranteed.
        logger.error(
            f"Failed to clone agent '{agent_id}' for session isolation: {e}"
        )
        raise RuntimeError(
            f"Failed to isolate agent '{agent_id}' for session: {e}"
        ) from e

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


# Fields whose swap requires side-effects the core SDK owns and the wrapper
# must not open-code: a bare ``setattr(agent, 'llm', value)`` leaves the cached
# ``_llm_instance`` / ``_unified_dispatcher`` / ``_llm_init_params`` bound to the
# previous model, so the request keeps running on the OLD LLM while ``agent.llm``
# (and the response metadata) reports the new one. Route through the SDK's own
# invalidator instead (praisonaiagents.Agent._apply_default_llm).
_SIDE_EFFECT_OVERRIDES = frozenset({"llm"})

_APPLYABLE_OVERRIDES = frozenset({
    "instructions", "goal", "role", "backstory",
    "max_iter",
    "verbose", "markdown",
})


class AgentConfigError(ValueError):
    """Raised when an agent_config override is unsupported or cannot be applied."""


def _swap_llm(agent: Any, model: Any) -> None:
    """Swap the agent's model, invalidating the SDK's cached LLM state.

    Prefers the SDK's own ``_apply_default_llm`` (which drops ``_llm_instance``,
    ``_unified_dispatcher`` and re-seeds ``_llm_init_params`` atomically). That
    method self-guards when the agent explicitly chose a model *or* was built
    with a panel descriptor, so both guards are temporarily cleared — an API
    override IS an explicit choice that supersedes a panel selection. Without
    clearing ``_panel_descriptor`` the SDK returns early and the request would
    silently continue on the panel model. Falls back to mirroring the SDK's
    invalidation contract when the method is absent.
    """
    apply = getattr(agent, "_apply_default_llm", None)
    if callable(apply):
        had_explicit = getattr(agent, "_llm_explicit", None)
        had_panel = getattr(agent, "_panel_descriptor", None)
        agent._llm_explicit = False
        if had_panel is not None:
            agent._panel_descriptor = None
        try:
            apply(model)
        finally:
            if had_explicit is not None:
                agent._llm_explicit = had_explicit
            # ``_panel_descriptor`` is intentionally NOT restored: the override
            # replaces the panel selection for the lifetime of this isolated
            # clone. Restoring it would let ``_ensure_llm_instance`` rebuild the
            # panel LLM and drift back to the old model.
        return
    # Fallback: mirror the SDK invalidation contract manually.
    agent.llm = model
    if getattr(agent, "_panel_descriptor", None) is not None:
        agent._panel_descriptor = None
    for attr in ("_llm_instance", "_unified_dispatcher"):
        if hasattr(agent, attr):
            setattr(agent, attr, None)
    if getattr(agent, "_llm_init_params", None):
        agent._llm_init_params = {**agent._llm_init_params, "model": model}


def _apply_agent_config(agent: Any, agent_config: Optional[Dict[str, Any]]) -> None:
    """Apply per-request overrides to an isolated agent clone.

    Only whitelisted fields are settable. An unknown or unsettable key raises
    ``AgentConfigError`` so the caller learns their override wasn't honoured
    instead of silently drifting. Callers translate this into a 400 response.

    Refuses to mutate a shared, non-isolated agent (e.g. a plain mock that took
    the shared-instance fallback): writing overrides onto a registry-shared
    object would leak this request's config into subsequent/concurrent requests.
    In that case the override is rejected rather than silently applied globally.

    ``llm`` is a side-effecting swap routed through :func:`_swap_llm` so the
    cached LLM is invalidated — a plain ``setattr`` would leave the request
    running on the previously cached model.
    """
    if not agent_config:
        return
    if not _supports_session_isolation(agent):
        raise AgentConfigError(
            "agent_config overrides require a session-isolatable Agent; this "
            "agent is shared across requests and cannot be safely overridden "
            "per request."
        )
    allowed = _APPLYABLE_OVERRIDES | _SIDE_EFFECT_OVERRIDES
    unknown = set(agent_config) - allowed
    if unknown:
        raise AgentConfigError(
            f"Unsupported agent_config override(s): {sorted(unknown)}. "
            f"Allowed: {sorted(allowed)}"
        )
    if "llm" in agent_config:
        _swap_llm(agent, agent_config["llm"])
    for key, value in agent_config.items():
        if key in _SIDE_EFFECT_OVERRIDES:
            continue
        if not hasattr(agent, key):
            raise AgentConfigError(
                f"Agent has no attribute {key!r}; cannot override."
            )
        try:
            setattr(agent, key, value)
        except (AttributeError, TypeError) as e:
            raise AgentConfigError(
                f"Cannot override {key!r} on this agent: {e}"
            )


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
        _: None = Depends(verify_token),
        registry: AgentRegistry = Depends(_registry_dependency),
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
        try:
            agent = resolve_session_agent(agent_id, request.session_id, registry=registry)
        except Exception as e:
            logger.error(f"Failed to isolate agent {agent_id}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Agent execution failed: {str(e)}"
            )
        if not agent:
            logger.error(f"Agent not found: {agent_id}")
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_id}' not found"
            )
        
        # Apply per-request agent_config overrides to the isolated clone, or
        # reject unsupported keys with a 400 so the caller isn't silently
        # running a different config than they asked for.
        try:
            _apply_agent_config(agent, request.agent_config)
        except AgentConfigError as e:
            raise HTTPException(status_code=400, detail=str(e))

        try:
            # Session ID echoed back to the caller
            session_id = request.session_id or "default"
            
            # Invoke agent (handle both sync and async agents)
            if _supports_async_start(agent):
                # Async agent
                result = await agent.astart(request.message)
            elif _supports_sync_start(agent):
                # Sync agent - run in a worker thread to avoid blocking the event
                # loop. ``asyncio.to_thread`` is the correct primitive inside a
                # running request coroutine (``get_event_loop()`` is deprecated
                # there since Python 3.10).
                import asyncio
                result = await asyncio.to_thread(agent.start, request.message)
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
    async def list_agents(
        _: None = Depends(verify_token),
        registry: AgentRegistry = Depends(_registry_dependency),
    ) -> Dict[str, Any]:
        """
        List all registered agents.
        
        Returns:
            Dictionary containing list of available agents
        """
        agents = list_registered_agents(registry=registry)
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
    async def unregister_agent_endpoint(
        agent_id: str,
        _: None = Depends(verify_token),
        registry: AgentRegistry = Depends(_registry_dependency),
    ) -> Dict[str, Any]:
        """
        Unregister an agent from API access.
        """
        success = unregister_agent(agent_id, registry=registry)
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
    async def get_agent_info(
        agent_id: str,
        _: None = Depends(verify_token),
        registry: AgentRegistry = Depends(_registry_dependency),
    ) -> Dict[str, Any]:
        """
        Get information about a registered agent.
        """
        agent = get_agent(agent_id, registry=registry)
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

    try:
        # Per-session isolated agent view (see resolve_session_agent). Done
        # inside the try so a clone/isolation failure returns a clean error
        # rather than leaking one session's history into another.
        agent = resolve_session_agent(agent_id, session_id)

        # Apply per-request overrides, or surface a clean error dict if a key
        # isn't supported (mirrors the route's 400 without raising HTTP here).
        try:
            _apply_agent_config(agent, agent_config)
        except AgentConfigError as e:
            return {
                "error": str(e),
                "status": "error",
                "agent_id": agent_id,
            }

        # Invoke agent
        session_id = session_id or "default"
        
        if _supports_async_start(agent):
            result = await agent.astart(message)
        elif _supports_sync_start(agent):
            # Sync agent - run in a worker thread to avoid blocking the event
            # loop. ``asyncio.to_thread`` is the correct primitive inside a
            # running request coroutine (``get_event_loop()`` is deprecated
            # there since Python 3.10).
            import asyncio
            result = await asyncio.to_thread(agent.start, message)
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
