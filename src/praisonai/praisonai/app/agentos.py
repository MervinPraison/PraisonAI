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
            from .._api_auth import build_api_key_middleware
            app.add_middleware(build_api_key_middleware(launch_token, {"/health", "/"}))
        
        return app
    
    def _register_routes(self, app: Any) -> None:
        """Register API routes."""
        from fastapi import HTTPException, Query, WebSocket, WebSocketDisconnect
        from pydantic import BaseModel
        
        class ChatRequest(BaseModel):
            message: str
            agent_name: Optional[str] = None
            session_id: Optional[str] = None
        
        class ChatResponse(BaseModel):
            response: str
            agent_name: str
            session_id: Optional[str] = None

        class RunRequest(BaseModel):
            message: str
            session_id: Optional[str] = None

        # Per-instance locks serialising invocations of a single team/flow.
        # Teams and flows carry mutable run state on the stored instance, so two
        # overlapping requests for the *same* object would corrupt each other
        # (e.g. AgentFlow.run rejects a re-entrant run). Agents are cloned per
        # request (see _isolate_agent); teams/flows aren't safely deep-copyable,
        # so the safe-by-default behaviour is to run one at a time per instance.
        # Different teams/flows still run concurrently; only same-instance calls
        # queue. The lock is created lazily on the serving loop.
        _target_locks: Dict[int, "asyncio.Lock"] = {}

        async def _invoke(target: Any, message: str) -> Any:
            """Invoke a team/flow without blocking the loop: prefer its async
            entry point, else offload the sync call to a worker thread. Calls on
            the same instance are serialised so concurrent requests can't trample
            its shared run state."""
            lock = _target_locks.get(id(target))
            if lock is None:
                lock = _target_locks.setdefault(id(target), asyncio.Lock())
            async with lock:
                for attr in ("arun", "astart"):
                    fn = getattr(target, attr, None)
                    if callable(fn):
                        return await fn(message)
                for attr in ("run", "start"):
                    fn = getattr(target, attr, None)
                    if callable(fn):
                        return await asyncio.to_thread(fn, message)
            raise HTTPException(
                status_code=501,
                detail="target exposes no run/start entry point",
            )

        def _isolate_agent(template: Any, session_id: Optional[str]) -> Any:
            """Return a per-request agent so concurrent callers never share one
            agent's mutable chat_history.

            Reuses the wrapper's existing clone/bind helpers (api/agent_invoke.py)
            rather than reinventing cloning. ``clone_for_channel`` intentionally
            drops handoffs (nested Agents can't be safely deep-copied and would
            share RLocks), so agents with handoffs stay on the shared template to
            avoid silently losing configured delegation. Plain mocks / lightweight
            callables that don't support isolation also fall back to the template.
            Shared by both POST /chat and the WebSocket endpoint so they can never
            drift apart on this safety property.
            """
            from praisonai.api.agent_invoke import (
                _supports_session_isolation,
                _clone_agent,
                bind_session,
            )
            has_handoffs = bool(getattr(template, "handoffs", None))
            if _supports_session_isolation(template) and not has_handoffs:
                agent = _clone_agent(template)
                return bind_session(agent, session_id)
            return template
        
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

            # Prefer the registry's public requirement listing so a core-SDK
            # refactor of its internal storage can never silently 503 this
            # production surface. Fall back to the private fields only on older
            # cores that predate list_requirements().
            if hasattr(registry, "list_requirements"):
                return {"requirements": registry.list_requirements()}

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
            # share mutable chat_history (shared helper, see _isolate_agent).
            try:
                agent = _isolate_agent(template, request.session_id)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to isolate agent for session: {e}",
                )

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

        # ── Teams & flows ─────────────────────────────────────────────────
        # The constructor accepts teams/flows and `/` reports their counts, so
        # a POST to invoke them must exist or those collections silently do
        # nothing. Routed by name; 404 when the name is unknown.

        @app.post(f"{self.config.api_prefix}/teams/{{team_name}}/run")
        async def run_team(team_name: str, request: RunRequest):
            team = next(
                (t for t in self.teams if getattr(t, "name", None) == team_name),
                None,
            )
            if team is None:
                raise HTTPException(status_code=404, detail=f"Team '{team_name}' not found")
            try:
                result = await _invoke(team, request.message)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
            return {"team": team_name, "result": str(result), "session_id": request.session_id}

        @app.post(f"{self.config.api_prefix}/flows/{{flow_name}}/run")
        async def run_flow(flow_name: str, request: RunRequest):
            flow = next(
                (f for f in self.flows if getattr(f, "name", None) == flow_name),
                None,
            )
            if flow is None:
                raise HTTPException(status_code=404, detail=f"Flow '{flow_name}' not found")
            try:
                result = await _invoke(flow, request.message)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))
            return {"flow": flow_name, "result": str(result), "session_id": request.session_id}

        # ── WebSocket chat ────────────────────────────────────────────────
        # The docstring advertises WebSocket endpoints. Deliver one that speaks
        # the same agent surface as POST /chat (achat/chat) rather than a
        # fabricated streaming API the core Agent does not expose. The whole
        # response is sent as one frame followed by a terminal {"done": true}.
        #
        # Two invariants this endpoint must share with POST /chat:
        #   1. Authentication — the HTTP api-key middleware does not run on the
        #      WebSocket handshake, so when a launch token is configured the
        #      socket must validate it itself or it would be an unauthenticated
        #      back door to the same agents the REST surface guards.
        #   2. Session isolation — resolve a per-request agent (clone + bind the
        #      session) exactly like /chat so concurrent sockets never share one
        #      agent's mutable chat_history.

        launch_token = self.config.api_key or os.environ.get("PRAISONAI_AGENTOS_API_KEY")

        def _ws_token(ws: WebSocket) -> str:
            # Accept the key via the same surfaces as the HTTP middleware
            # (Bearer / X-API-Key header) plus an ``?api_key=`` query param,
            # since browser WebSocket clients cannot set arbitrary headers.
            auth = ws.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                return auth[7:]
            return ws.headers.get("X-API-Key", "") or ws.query_params.get("api_key", "")

        def _resolve_ws_agent(agent_name: Optional[str], session_id: Optional[str]):
            template = None
            if agent_name:
                template = next(
                    (a for a in self.agents if getattr(a, "name", None) == agent_name),
                    None,
                )
                if template is None:
                    return None
            elif self.agents:
                template = self.agents[0]
            else:
                return None
            return _isolate_agent(template, session_id)

        @app.websocket(f"{self.config.api_prefix}/chat/stream")
        async def chat_stream(ws: WebSocket):
            if launch_token:
                import hmac
                token = _ws_token(ws)
                if not token or not hmac.compare_digest(token, launch_token):
                    # 1008 = policy violation; reject before accepting the socket.
                    await ws.close(code=1008)
                    return
            await ws.accept()
            try:
                while True:
                    payload = await ws.receive_json()
                    message = payload.get("message")
                    if not message:
                        await ws.send_json({"error": "message is required"})
                        continue
                    agent_name = payload.get("agent_name")
                    session_id = payload.get("session_id")
                    if agent_name and not any(
                        getattr(a, "name", None) == agent_name for a in self.agents
                    ):
                        await ws.send_json({"error": f"Agent '{agent_name}' not found"})
                        continue
                    agent = _resolve_ws_agent(agent_name, session_id)
                    if agent is None:
                        await ws.send_json({"error": "no agents available"})
                        continue
                    try:
                        if hasattr(agent, "achat") and callable(getattr(agent, "achat")):
                            response = await agent.achat(message)
                        else:
                            response = await asyncio.to_thread(agent.chat, message)
                        await ws.send_json({"response": str(response)})
                        await ws.send_json({"done": True})
                    except Exception as e:
                        await ws.send_json({"error": str(e)})
            except WebSocketDisconnect:
                return
    
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

        resolved_host = host or self.config.host
        resolved_port = port or self.config.port
        enable_reload = reload or self.config.reload

        if enable_reload:
            # Uvicorn's reload spawns a fresh worker *process* that re-imports
            # the target module; it cannot see this parent process's in-memory
            # state. Because an AgentOS is built programmatically from live
            # Agent/Team/Flow objects (not an importable module-level app), a
            # reload worker has no way to reconstruct it — the app factory would
            # start with no instance and fail. So reload is unsupported for a
            # programmatically-built AgentOS: warn and serve without it rather
            # than crash. To get reload, run uvicorn against your own module
            # that exposes the app, e.g.
            # ``uvicorn "mymodule:create_app" --factory --reload``.
            import warnings
            warnings.warn(
                "AgentOS.serve(reload=True) is not supported for a "
                "programmatically-built AgentOS: uvicorn's reload worker runs in "
                "a separate process and cannot access this instance's live "
                "agents. Serving without reload. For auto-reload, run uvicorn "
                "against an importable app factory in your own module "
                "(e.g. `uvicorn \"mymodule:create_app\" --factory --reload`).",
                stacklevel=2,
            )

        uvicorn.run(
            self.get_app(),
            host=resolved_host,
            port=resolved_port,
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
