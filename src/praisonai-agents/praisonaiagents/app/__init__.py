"""
App module for production deployment of AI agents.

This module provides the protocol and configuration for AgentOS,
a production platform for deploying agents as web services.

The protocol is defined here in the core SDK (lightweight).
The implementation lives in the praisonai wrapper (heavy deps like FastAPI).

AgentOSProtocol and AgentOSConfig are the primary names (v1.0+).
AgentAppProtocol and AgentAppConfig are silent aliases for backward compatibility.

Example:
    # Protocol is importable from core SDK
    from praisonaiagents import AgentOSProtocol, AgentOSConfig
    
    # Implementation is in wrapper
    from praisonai import AgentOS
    
    app = AgentOS(
        name="My App",
        agents=[researcher, writer],
    )
    app.serve(port=8000)
"""

from .protocols import AgentOSProtocol, AgentAppProtocol
from .config import AgentAppConfig

# AgentOSConfig is an alias for AgentAppConfig (config name unchanged for now)
AgentOSConfig = AgentAppConfig

__all__ = [
    'AgentOSProtocol',  # Primary protocol (v1.0+)
    'AgentOSConfig',  # Primary config (v1.0+)
    'AgentAppProtocol',  # Silent alias
    'AgentAppConfig',  # Silent alias
]
