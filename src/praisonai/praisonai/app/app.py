"""
AgentOS implementation for production deployment.

This module provides the AgentOS class which implements the AgentOSProtocol.
It creates a FastAPI-based web service for deploying agents.
"""

from typing import Any, Dict, List, Optional, Union

from praisonaiagents import AgentOSConfig, AgentOSProtocol


class AgentOS:
    """
    Production platform for deploying AI agents as web services.
    
    AgentOS wraps agents, managers, and workflows into a unified FastAPI
    application with REST and WebSocket endpoints.
    
    Example:
        from praisonai import AgentOS
        from praisonaiagents import Agent
        
        assistant = Agent(name="assistant", instructions="Be helpful")
        
        # Simple usage
        app = AgentOS(agents=[assistant])
        app.serve(port=8000)
        
        # With configuration
        app = AgentOS(
            name="My AI App",
            agents=[assistant],
            config=AgentOSConfig(port=9000, reload=True)
        )
        app.serve()
    
    Attributes:
        name: Name of the application
        agents: List of Agent instances
        managers: List of AgentTeam instances
        workflows: List of Workflow instances
        config: AgentOSConfig instance
    """
    
    def __init__(
        self,
        name: str = "PraisonAI App",
        agents: Optional[List[Any]] = None,
        managers: Optional[List[Any]] = None,
        workflows: Optional[List[Any]] = None,
        config: Optional[AgentOSConfig] = None,
        **kwargs: Any
    ):
        """
        Initialize AgentOS.
        
        Args:
            name: Name of the application
            agents: List of Agent instances to serve
            managers: List of AgentTeam instances to serve
            workflows: List of Workflow instances to serve
            config: AgentOSConfig for server configuration
            **kwargs: Additional configuration passed to AgentOSConfig
        """
        self.name = name
        self.agents = agents or []
        self.managers = managers or []
        self.workflows = workflows or []
        
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
        
        return app
    
    def _register_routes(self, app: Any) -> None:
        """Register API routes."""
        from fastapi import HTTPException
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
                "managers": len(self.managers),
                "workflows": len(self.workflows),
            }
        
        @app.get("/health")
        async def health():
            return {"status": "healthy"}
        
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
            # Find the agent
            agent = None
            if request.agent_name:
                for a in self.agents:
                    if getattr(a, 'name', None) == request.agent_name:
                        agent = a
                        break
                if agent is None:
                    raise HTTPException(status_code=404, detail=f"Agent '{request.agent_name}' not found")
            elif self.agents:
                agent = self.agents[0]
            else:
                raise HTTPException(status_code=400, detail="No agents available")
            
            # Call the agent
            try:
                response = agent.chat(request.message)
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
