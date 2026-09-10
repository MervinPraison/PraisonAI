"""
AgentOS implementation for production deployment.

This module provides the AgentOS class which implements the AgentOSProtocol.
It creates a FastAPI-based web service for deploying agents.
"""

from typing import Any, Dict, List, Optional, Union

import asyncio
import os

from praisonaiagents import AgentOSConfig, AgentOSProtocol


def _run_to_dict(record: Any) -> Dict[str, Any]:
    """A RunRecord as JSON. Uses whatever the record exposes rather than
    assuming a shape, so a ledger with extra fields is not silently truncated."""
    if hasattr(record, "as_dict"):
        return record.as_dict()
    if hasattr(record, "__dict__"):
        return {k: v for k, v in vars(record).items() if not k.startswith("_")}
    return {"run": str(record)}


class AgentOS:
    """
    Production platform for deploying AI agents as web services.
    
    AgentOS wraps agents, teams, and flows into a unified FastAPI
    application with REST and WebSocket endpoints.
    
    Example:
        from praisonai import AgentOS
        from praisonaiagents import Agent, AgentTeam, AgentFlow
        
        assistant = Agent(name="assistant", instructions="Be helpful")
        
        # Simple usage
        app = AgentOS(agents=[assistant])
        app.serve(port=8000)
        
        # With teams and flows
        app = AgentOS(
            name="My AI App",
            agents=[assistant],
            teams=[my_team],
            flows=[my_flow],
            config=AgentOSConfig(port=9000, reload=True)
        )
        app.serve()
    
    Attributes:
        name: Name of the application
        agents: List of Agent instances
        teams: List of AgentTeam instances (alias: managers)
        flows: List of AgentFlow instances (alias: workflows)
        config: AgentOSConfig instance
    """
    
    def __init__(
        self,
        name: str = "PraisonAI App",
        agents: Optional[List[Any]] = None,
        teams: Optional[List[Any]] = None,
        flows: Optional[List[Any]] = None,
        config: Optional[AgentOSConfig] = None,
        # Backward compatibility aliases
        managers: Optional[List[Any]] = None,  # Deprecated: use teams
        workflows: Optional[List[Any]] = None,  # Deprecated: use flows
        **kwargs: Any
    ):
        """
        Initialize AgentOS.
        
        Args:
            name: Name of the application
            agents: List of Agent instances to serve
            teams: List of AgentTeam instances to serve (alias: managers)
            flows: List of AgentFlow instances to serve (alias: workflows)
            config: AgentOSConfig for server configuration
            **kwargs: Additional configuration passed to AgentOSConfig
        """
        self.name = name
        self.agents = agents or []
        # Support both new names and legacy aliases
        self.teams = teams or managers or []
        self.flows = flows or workflows or []
        
        # Merge kwargs into config
        if config is None:
            config = AgentOSConfig(name=name, **kwargs)
        self.config = config
        
        # FastAPI app instance (lazy initialized)
        self._app = None
    
    def _create_app(self) -> Any:
        """Create the FastAPI application."""
        try:
            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware
        except ImportError:
            raise ImportError(
                "FastAPI is required for AgentOS. "
                "Install with: pip install praisonai[api]"
            )
        
        app = FastAPI(
            title=self.name,
            description="PraisonAI Agent Application",
            version="1.0.0",
            docs_url=self.config.docs_url,
            openapi_url=self.config.openapi_url,
        )
        
        # Add CORS middleware
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.config.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Register routes
        self._register_routes(app)

        launch_token = self.config.api_key or os.environ.get("PRAISONAI_AGENTOS_API_KEY")
        if launch_token:
            from starlette.middleware.base import BaseHTTPMiddleware
            from starlette.responses import JSONResponse

            expected = launch_token

            class _AgentOSAuthMiddleware(BaseHTTPMiddleware):
                async def dispatch(self, request, call_next):
                    if request.url.path in ("/health", "/"):
                        return await call_next(request)
                    auth = request.headers.get("Authorization", "")
                    token = auth[7:] if auth.startswith("Bearer ") else request.headers.get("X-API-Key", "")
                    if token != expected:
                        return JSONResponse({"error": "Unauthorized"}, status_code=401)
                    return await call_next(request)

            app.add_middleware(_AgentOSAuthMiddleware)
        
        return app
    
    def _register_routes(self, app: Any) -> None:
        """Register API routes."""
        from fastapi import HTTPException, Query
        from pydantic import BaseModel
        
        class ChatRequest(BaseModel):
            message: str
            agent_name: Optional[str] = None
            session_id: Optional[str] = None
        
        class ChatResponse(BaseModel):
            response: str
            agent_name: str
            session_id: Optional[str] = None
        
        @app.get("/")
        async def root():
            return {
                "name": self.name,
                "status": "running",
                "agents": [getattr(a, 'name', str(a)) for a in self.agents],
                "teams": len(self.teams),
                "flows": len(self.flows),
            }
        
        @app.get("/health")
        async def health():
            return {"status": "healthy"}
        
        # ── Read endpoints ────────────────────────────────────────────────
        # AgentOS could list agents and take a chat turn, and nothing else. A
        # session could not be replayed, a run inspected, or a pending approval
        # seen over HTTP, even though the protocols to expose all three already
        # existed. These are READ-only on purpose: mutating a run over HTTP is a
        # much larger design question than surfacing one.
        #
        # Each returns 503 with what to configure when its store is absent.
        # Returning an empty list would be indistinguishable from "no runs yet",
        # which is the failure this codebase keeps finding.

        def _unavailable(what: str, how: str):
            raise HTTPException(
                status_code=503,
                detail=f"{what} is not available: {how}",
            )

        @app.get(f"{self.config.api_prefix}/runs")
        async def list_runs(limit: int = Query(50, ge=1, le=500)):
            ledger = getattr(self, "run_ledger", None)
            if ledger is None:
                _unavailable(
                    "Run history",
                    "no run ledger is configured on this AgentOS instance. "
                    "Attach a praisonaiagents.runs.SQLiteRunLedger as `run_ledger`.",
                )
            records = ledger.list_all(limit=limit)
            return {"runs": [_run_to_dict(r) for r in records], "count": len(records)}

        @app.get(f"{self.config.api_prefix}/runs/{{run_id}}")
        async def get_run(run_id: str):
            ledger = getattr(self, "run_ledger", None)
            if ledger is None:
                _unavailable(
                    "Run history",
                    "no run ledger is configured on this AgentOS instance.",
                )
            record = ledger.get(run_id)
            if record is None:
                raise HTTPException(status_code=404, detail=f"No run {run_id!r}")
            return _run_to_dict(record)

        @app.get(f"{self.config.api_prefix}/sessions")
        async def list_sessions(limit: int = Query(20, ge=1, le=200)):
            store = getattr(self, "session_store", None)
            if store is None or not hasattr(store, "recent"):
                _unavailable(
                    "Session history",
                    "no session store is configured on this AgentOS instance. "
                    "Attach a praisonaiagents.session store as `session_store`.",
                )
            summaries = store.recent(limit=limit)
            return {
                "sessions": [
                    s.as_dict() if hasattr(s, "as_dict") else dict(s) for s in summaries
                ],
                "count": len(summaries),
            }

        @app.get(f"{self.config.api_prefix}/sessions/{{session_id}}")
        async def get_session(session_id: str, limit: int = Query(100, ge=1, le=500)):
            store = getattr(self, "session_store", None)
            if store is None:
                _unavailable(
                    "Session history",
                    "no session store is configured on this AgentOS instance.",
                )
            if hasattr(store, "session_exists"):
                if not store.session_exists(session_id):
                    raise HTTPException(status_code=404, detail=f"No session {session_id!r}")
            elif not store.get_chat_history(session_id, limit):
                # Stores without session_exists cannot distinguish an unknown
                # session from an empty one; treat an empty transcript as absent
                # rather than returning a healthy-looking 200 for a bad id.
                raise HTTPException(status_code=404, detail=f"No session {session_id!r}")
            return {
                "session_id": session_id,
                "messages": store.get_chat_history(session_id, limit),
            }

        @app.get(f"{self.config.api_prefix}/approvals")
        async def list_approvals():
            try:
                from praisonaiagents.approval import get_approval_registry
            except ImportError:
                _unavailable("Approvals", "praisonaiagents.approval is not installed.")
            registry = get_approval_registry()

            # The registry stores approval requirements across four fields --
            # global tools plus per-agent overrides -- rather than a single
            # dict. Reading the public accessors (is_required/get_risk_level)
            # keeps this decoupled from that private shape. Fall back to the
            # attributes only to enumerate which (agent, tool) pairs exist.
            global_tools = getattr(registry, "_required_tools", None)
            agent_tools = getattr(registry, "_agent_required_tools", None)
            if global_tools is None and agent_tools is None:
                _unavailable(
                    "Approvals",
                    "this build's approval registry exposes no requirement listing.",
                )

            requirements = []
            for tool in sorted(global_tools or ()):
                requirements.append({
                    "tool": tool,
                    "agent": None,
                    "risk_level": registry.get_risk_level(tool),
                })
            for agent, tools in (agent_tools or {}).items():
                for tool in sorted(tools):
                    requirements.append({
                        "tool": tool,
                        "agent": agent,
                        "risk_level": registry.get_risk_level(tool, agent),
                    })
            return {"requirements": requirements}

        @app.get(f"{self.config.api_prefix}/agents")
        async def list_agents():
            return {
                "agents": [
                    {
                        "name": getattr(a, 'name', f'agent_{i}'),
                        "role": getattr(a, 'role', None),
                        "instructions": getattr(a, 'instructions', None)[:100] + "..." 
                            if getattr(a, 'instructions', None) and len(getattr(a, 'instructions', '')) > 100 
                            else getattr(a, 'instructions', None),
                    }
                    for i, a in enumerate(self.agents)
                ]
            }
        
        @app.post(f"{self.config.api_prefix}/chat", response_model=ChatResponse)
        async def chat(request: ChatRequest):
            # Find the agent template (shared instance in self.agents).
            template = None
            if request.agent_name:
                for a in self.agents:
                    if getattr(a, 'name', None) == request.agent_name:
                        template = a
                        break
                if template is None:
                    raise HTTPException(status_code=404, detail=f"Agent '{request.agent_name}' not found")
            elif self.agents:
                template = self.agents[0]
            else:
                raise HTTPException(status_code=400, detail="No agents available")

            # Isolate a per-request/session agent so concurrent callers never
            # share mutable chat_history. Reuse the wrapper's existing helpers
            # (api/agent_invoke.py) rather than reinventing cloning here. Plain
            # mocks / lightweight callables fall back to the shared template.
            from praisonai.api.agent_invoke import (
                _supports_session_isolation,
                _clone_agent,
            )
            # ``clone_for_channel`` intentionally drops handoffs (nested Agents
            # can't be safely deep-copied and would share RLocks). To avoid
            # silently losing configured delegation, agents with handoffs stay
            # on the shared template rather than being cloned.
            has_handoffs = bool(getattr(template, "handoffs", None))
            if _supports_session_isolation(template) and not has_handoffs:
                try:
                    agent = _clone_agent(template)
                except Exception as e:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to isolate agent for session: {e}",
                    )
                agent.chat_history = []
                if hasattr(agent, "_session_store_initialized"):
                    agent._session_store_initialized = False
                if request.session_id:
                    agent._session_id = request.session_id
                    if hasattr(agent, "_history_session_id"):
                        agent._history_session_id = request.session_id
                else:
                    agent._session_id = None
                    if hasattr(agent, "_history_session_id"):
                        agent._history_session_id = None
            else:
                agent = template

            # Call the agent without blocking the event loop: prefer the async
            # twin, otherwise offload the sync call to a worker thread.
            try:
                if hasattr(agent, "achat") and callable(getattr(agent, "achat")):
                    response = await agent.achat(request.message)
                else:
                    response = await asyncio.to_thread(agent.chat, request.message)
                return ChatResponse(
                    response=str(response),
                    agent_name=getattr(agent, 'name', 'unknown'),
                    session_id=request.session_id,
                )
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
    
    def get_app(self) -> Any:
        """
        Get the FastAPI application instance.
        
        Returns:
            The FastAPI application instance for custom mounting or configuration.
        """
        if self._app is None:
            self._app = self._create_app()
        return self._app
    
    def serve(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        reload: bool = False,
        **kwargs: Any
    ) -> None:
        """
        Start the AgentOS server.
        
        Args:
            host: Host address to bind to (default from config)
            port: Port number to listen on (default from config)
            reload: Enable auto-reload for development
            **kwargs: Additional uvicorn configuration
        """
        try:
            import uvicorn
        except ImportError:
            raise ImportError(
                "Uvicorn is required for AgentOS. "
                "Install with: pip install praisonai[api]"
            )
        
        app = self.get_app()
        
        uvicorn.run(
            app,
            host=host or self.config.host,
            port=port or self.config.port,
            reload=reload or self.config.reload,
            log_level=self.config.log_level,
            **kwargs
        )


# Verify protocol compliance
def _verify_protocol():
    """Verify that AgentOS implements AgentOSProtocol."""
    assert isinstance(AgentOS(agents=[]), AgentOSProtocol), \
        "AgentOS must implement AgentOSProtocol"

# Run verification at import time (only in debug mode)
# _verify_protocol()
