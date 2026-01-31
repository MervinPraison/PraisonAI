"""
AgentOS protocol definitions.

This module defines the protocol (interface) for AgentOS implementations.
The protocol is lightweight and lives in the core SDK.
Implementations live in the praisonai wrapper.

AgentOSProtocol is the primary name (v1.0+).
AgentAppProtocol is a silent alias for backward compatibility.
"""

from typing import TYPE_CHECKING, Any, List, Optional, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..agent.agent import Agent
    from ..agents.agents import AgentTeam
    from ..workflows.workflows import AgentFlow


@runtime_checkable
class AgentOSProtocol(Protocol):
    """
    Protocol for AgentOS implementations.
    
    AgentOS is a production platform for deploying agents as web services.
    It wraps agents, teams, and flows into a unified API server.
    
    Implementations should:
    - Provide FastAPI-based HTTP endpoints
    - Support WebSocket connections for real-time communication
    - Handle agent lifecycle management
    - Provide health checks and monitoring endpoints
    
    Example implementation (in praisonai wrapper):
        class AgentOS:
            def __init__(
                self,
                name: str = "PraisonAI App",
                agents: List[Agent] = None,
                teams: List[AgentTeam] = None,
                flows: List[AgentFlow] = None,
            ):
                ...
            
            def serve(self, host: str = "0.0.0.0", port: int = 8000):
                '''Start the FastAPI server.'''
                ...
            
            def get_app(self):
                '''Get the FastAPI app instance for custom mounting.'''
                ...
    
    Note:
        The protocol was renamed from `AgentAppProtocol` to `AgentOSProtocol` in v1.0.
        `AgentAppProtocol` remains as a silent alias for backward compatibility.
    """
    
    def serve(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        reload: bool = False,
        **kwargs: Any
    ) -> None:
        """
        Start the AgentApp server.
        
        Args:
            host: Host address to bind to (default: "0.0.0.0")
            port: Port number to listen on (default: 8000)
            reload: Enable auto-reload for development (default: False)
            **kwargs: Additional server configuration
        """
        ...
    
    def get_app(self) -> Any:
        """
        Get the underlying web application instance.
        
        Returns:
            The FastAPI application instance for custom mounting or configuration.
        """
        ...


# Backward compatibility alias (silent - no deprecation warning)
AgentAppProtocol = AgentOSProtocol
